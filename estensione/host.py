"""Host Native Messaging dell'estensione (versione ripulita del PoC del 02/10/2026).

Protocollo (stdin/stdout, 4 byte di lunghezza little-endian + JSON UTF-8):
  {"cmd": "config"}  -> {"ok": true, "raccolta": bool, "siti": {id: [domini]}, "esclusi": [domini]}
  {"cmd": "fascia", "ts": <epoch s, multiplo di 900>, "sito": <id>, "campioni": <int>}
                     -> {"ok": true|false, "raccolta": bool, ...}  (raccolta sempre presente)

Scrive solo righe {"tipo": "web", "ts": <inizio fascia o primo istante di raccolta attiva in essa>, "sito": <id>, "fonte": "estensione"} in
raw/estensione-<giorno>.jsonl, e solo se:
  - l'impostazione «estensione_browser» è attiva (predefinito: no);
  - la fascia si sovrappone a un periodo di raccolta attiva della giornata (dopo «Avvia», escluse le pause);
  - l'id è un sito della mappatura del CED (mai «web_generico»: fuori elenco = url_non_visibile, non scritto; quindi nemmeno un'estensione compromessa
    può far scrivere un indirizzo, un titolo o testo libero);
  - la fascia è allineata ai 15 minuti, già conclusa e non più vecchia di 48 ore.
Nessun log dei contenuti: il registro diagnostico riporta solo l'esito e il motivo dei rifiuti."""
from __future__ import annotations

import datetime as dt
import json
import os
import struct
import sys

from aggregatore.mappa import Mappa
from collector.percorsi import Percorsi
from collector.registro import RE_SITO
from collector.stato import FUSO, Stato, intervalli_attivi  # noqa: F401 (riesportata per compatibilità)

from . import FASCIA_S, GENERICO

MAX_MESSAGGIO = 4096
MAX_ETA_S = 48 * 3600


def leggi_messaggio(flusso) -> dict | None:
    testa = flusso.read(4)
    if len(testa) < 4:
        return None
    n = struct.unpack("<I", testa)[0]
    if n > MAX_MESSAGGIO:
        raise ValueError("messaggio troppo lungo")
    corpo = flusso.read(n)
    if len(corpo) < n:
        return None
    m = json.loads(corpo.decode("utf-8"))
    if not isinstance(m, dict):
        raise ValueError("messaggio non valido")
    return m


def scrivi_messaggio(flusso, obj: dict):
    b = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    flusso.write(struct.pack("<I", len(b)) + b)
    flusso.flush()


class Host:
    def __init__(self, p: Percorsi, impostazioni: dict, mappa: Mappa, adesso=None):
        self.p, self.imp, self.mappa = p, impostazioni, mappa
        self._adesso = adesso or (lambda: dt.datetime.now(FUSO()))

    def attivo(self) -> bool:
        return self.imp.get("estensione_browser") is True

    def raccolta(self) -> bool:
        """True solo con estensione attiva e giornata in corso (mai in pausa / non avviata)."""
        g = Stato(self.p).giornata() or {}
        return self.attivo() and g.get("fase") == "in_corso"

    def config(self) -> dict:
        siti: dict[str, list[str]] = {}
        for dominio, sid in sorted(self.mappa.per_dominio.items()):
            siti.setdefault(sid, []).append(dominio)
        return {"ok": True, "raccolta": self.raccolta(),
                "siti": siti, "esclusi": sorted(self.mappa.esclusi)}

    def fascia(self, m: dict) -> dict:
        def no(motivo):
            self._log(f"rifiutata: {motivo}")
            return {"ok": False, "rifiutato": motivo}
        if not self.attivo():
            return no("estensione_disattivata")
        ts, sito, n = m.get("ts"), m.get("sito"), m.get("campioni", 0)
        if type(ts) is not int or ts % FASCIA_S:
            return no("fascia_non_allineata")
        # L'estensione non scrive più «web_generico» (URL non visibile ≠ sito generico). Solo id in mappatura.
        if not isinstance(sito, str) or not RE_SITO.match(sito) or sito not in self.mappa.siti or sito == GENERICO:
            return no("sito_non_in_elenco")
        if type(n) is not int or n < 1:
            return no("campioni_non_validi")
        ora = self._adesso()
        inizio = dt.datetime.fromtimestamp(ts, FUSO())
        fine = inizio + dt.timedelta(seconds=FASCIA_S)
        parziale = m.get("parziale") is True          # flush a Chiudi/Pausa: fascia ancora aperta
        if (ora - inizio).total_seconds() > MAX_ETA_S:
            return no("fascia_fuori_periodo")
        # Fascia futura (oltre 60 s) rifiutata; una fascia in corso è ammessa solo se «parziale» (flush)
        if fine > ora + dt.timedelta(seconds=60) and not parziale:
            return no("fascia_fuori_periodo")
        if parziale and inizio > ora:
            return no("fascia_fuori_periodo")
        g = Stato(self.p).giornata() or {}
        # A Chiudi la fase è già «chiusa»: intervalli_attivi usa la chiusura; in corso usa adesso
        sovr = [max(a, inizio) for a, b in intervalli_attivi(g, ora) if a < fine and inizio < b]
        if not sovr:
            return no("raccolta_non_attiva")
        # ts = primo istante di raccolta attiva nella fascia (l'aggregatore conta il sito solo a sessione attiva)
        riga = {"tipo": "web", "ts": min(sovr).replace(microsecond=0).isoformat(), "sito": sito, "fonte": "estensione"}
        path = os.path.join(self.p.raw, f"estensione-{inizio.date().isoformat()}.jsonl")
        testo = json.dumps(riga, ensure_ascii=False, sort_keys=True)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                if any(r.strip() == testo for r in f):
                    return {"ok": True, "duplicata": True}
        with open(path, "a", encoding="utf-8") as f:
            f.write(testo + "\n")
        return {"ok": True}

    def gestisci(self, m: dict) -> dict:
        cmd = m.get("cmd")
        if cmd == "config":
            return self.config()
        if cmd == "fascia":
            r = self.fascia(m)
        else:
            r = {"ok": False, "rifiutato": "comando_sconosciuto"}
        # Ogni risposta porta lo stato raccolta: l'estensione ferma subito i campioni dopo Pausa/Chiudi
        # (senza aspettare la scadenza della cache della configurazione).
        r["raccolta"] = self.raccolta()
        return r

    def _log(self, testo: str):
        try:
            with open(os.path.join(self.p.diagnostica, "estensione-host.log"), "a", encoding="utf-8") as f:
                f.write(f"{self._adesso().replace(microsecond=0).isoformat()} {testo}\n")
        except OSError:
            pass


def main(argv=None) -> int:
    """Avviato dal browser (argomento: origine dell'estensione). Gestisce i messaggi fino alla chiusura di stdin."""
    from applicazione.servizio import carica_impostazioni
    p = Percorsi.predefiniti()
    imp = carica_impostazioni(p.base)
    h = Host(p, imp, Mappa.predefinita(imp.get("profili_siti") or []))
    ingresso, uscita = sys.stdin.buffer, sys.stdout.buffer
    while True:
        try:
            m = leggi_messaggio(ingresso)
        except (ValueError, UnicodeDecodeError):
            scrivi_messaggio(uscita, {"ok": False, "rifiutato": "messaggio_non_valido"})
            return 1
        if m is None:
            return 0
        scrivi_messaggio(uscita, h.gestisci(m))


if __name__ == "__main__":
    sys.exit(main())
