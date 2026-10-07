"""Scrittura degli eventi grezzi (raw.jsonl, formato M1) con un elenco chiuso di campi per tipo.

Il registro rifiuta qualunque campo non previsto: non può finire nel file un titolo di finestra, un percorso, un URL,
un oggetto o un indirizzo di posta, nemmeno per errore di programmazione. Il tipo «posta» non esiste più (bonifica B2)."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import threading

CAMPI = {
    "sessione": {"evento"},
    "attivita": set(),
    "app": {"exe"},
    "rete": {"operazioni"},
    "raccolta": {"evento"},
    "orologio": {"delta_s"},
    "web": {"sito"},          # solo l'identificativo del sito della mappatura (lettore «a consuntivo»), mai il dominio
}
RE_SITO = re.compile(r"^[a-z0-9_]{1,40}\Z")      # \Z, non $: «$» accetta anche un a-capo finale
RE_EXE = re.compile(r"^[A-Z0-9 _.\-()+&]{1,80}\.EXE\Z")     # solo il nome: mai «\\» o «/» (percorsi)


class ErroreRegistro(ValueError):
    pass


def iso(t: dt.datetime) -> str:
    if t.tzinfo is None:
        raise ErroreRegistro("istante senza fuso")
    return t.replace(microsecond=0).isoformat()


def controlla(tipo: str, campi: dict) -> dict:
    if tipo not in CAMPI:
        raise ErroreRegistro(f"tipo non ammesso: {tipo}")
    extra = set(campi) - CAMPI[tipo]
    if extra:
        raise ErroreRegistro(f"campi non ammessi per {tipo}: {sorted(extra)}")
    if tipo == "app" and not RE_EXE.match(campi.get("exe", "")):
        raise ErroreRegistro("exe: solo il nome dell'eseguibile, senza percorso")
    if tipo == "web" and not RE_SITO.match(str(campi.get("sito", ""))):
        raise ErroreRegistro("web: solo l'identificativo del sito (a-z0-9_), mai dominio o indirizzo")
    if tipo == "rete" and not (isinstance(campi.get("operazioni"), int) and campi["operazioni"] >= 1):
        raise ErroreRegistro("rete: operazioni intero ≥ 1")
    return campi


class Registro:
    """Accoda gli eventi al file raw del giorno dell'evento (una riga JSON per evento, scritta subito su disco)."""

    def __init__(self, percorsi):
        self.p = percorsi
        self._lock = threading.Lock()

    def scrivi(self, tipo: str, ts: dt.datetime, **campi) -> dict:
        controlla(tipo, campi)
        rec = {"tipo": tipo, "ts": iso(ts), **campi}
        path = self.p.raw_giorno(ts.date().isoformat())
        line = json.dumps(rec, ensure_ascii=False, separators=(", ", ": "))
        with self._lock, open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        return rec
