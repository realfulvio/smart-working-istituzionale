"""CONGELATO (ADR-T6): etichette dell'impaginatore 4.0.0, solo per resoconto/storico/pdf_400.py. Non modificare.

Etichette e formati condivisi da PDF e interfaccia (nessuna logica sui dati: solo presentazione)."""
from __future__ import annotations

import datetime as dt

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
        "novembre", "dicembre"]
STATI = [  # chiave, etichetta, etichetta breve
    ("attivita_rilevata", "Attività al computer rilevata", "Attività"),
    ("nessuna_attivita_informatica_rilevata", "Nessuna attività al computer rilevata", "Nessuna attività"),
    ("sessione_bloccata", "Computer bloccato", "Bloccato"),
    ("sessione_disconnessa", "Sessione disconnessa (VDI/desktop remoto)", "Disconnessa"),
    ("raccolta_sospesa", "Raccolta sospesa dal dipendente", "Raccolta sospesa"),
    ("dato_non_disponibile", "Dato non disponibile", "Non disponibile"),
    ("sessione_chiusa", "Sessione chiusa", "Sessione chiusa"),
]
ST_LAB = {k: l for k, l, _ in STATI}
ST_BREVE = {k: b for k, _, b in STATI}
COLORI_STATO = {"attivita_rilevata": "#005e8e", "nessuna_attivita_informatica_rilevata": "#c9dbe8",
                "sessione_bloccata": "#7d8b96", "sessione_disconnessa": "#a3b0ba", "raccolta_sospesa": "#e9dfc6",
                "dato_non_disponibile": "#f1f4f6", "sessione_chiusa": "#e9edf1"}
TESTO_SU_STATO = {"attivita_rilevata": "#ffffff", "sessione_bloccata": "#ffffff"}
MANUALI = {"riunione": "Riunione", "telefonata": "Telefonata", "cartaceo": "Lavoro su carta",
           "sopralluogo": "Sopralluogo", "formazione": "Formazione", "altro": "Altro"}
EVENTI = {"accesso": "Accesso al computer", "blocco": "Blocco del computer", "sblocco": "Sblocco del computer",
          "chiusura": "Chiusura della sessione", "spegnimento": "Spegnimento", "disconnessione": "Disconnessione",
          "riconnessione": "Riconnessione", "sospensione": "Sospensione", "ripresa": "Ripresa dalla sospensione",
          "avvio_raccolta": "Avvio della giornata", "fine_raccolta": "Chiusura della giornata"}
COPERTURA = {"completa": "completa", "parziale": "parziale", "non_installato": "lettore non installato",
             "non_disponibile": "non disponibile"}
FONTI = {"sessione": "Sessione di Windows", "app": "Programmi in primo piano", "attivita": "Attività di input (conteggio)",
         "browser": "Siti dell'elenco dell'Ente", "posta": "Posta (Outlook, solo conteggi)", "rete": "Risorse di rete"}
CAMPI_SEGNALAZIONE = {"stato": "stato della fascia", "applicazioni": "programmi indicati", "categorie": "categorie",
                      "rete": "risorse di rete", "sessione": "eventi della sessione", "posta": "posta",
                      "totali": "totali", "altro": "altro"}
ORIGINE_SINTESI = {"ai": "scritta dall'assistente locale", "testo_standard": "testo standard (senza assistente)",
                   "dichiarata": "modificata dal dipendente – dichiarata"}


_RE_IDS = __import__("re").compile(r"\s*nei fatti citati\s*\[[^\]]*\]")


def avviso_leggibile(problema: str) -> str:
    """Avviso del controllo per il dipendente: senza l'elenco interno degli identificativi dei fatti."""
    return _RE_IDS.sub(" nei dati della giornata", problema).replace("frase ", "frase n. ", 1)


def data_lunga(giorno: str) -> str:
    g = dt.date.fromisoformat(giorno)
    return f"{GIORNI[g.weekday()]} {g.day} {MESI[g.month - 1]} {g.year}"


def data_breve(giorno: str) -> str:
    return dt.date.fromisoformat(giorno).strftime("%d/%m/%Y")


def ts_breve(ts: str | None) -> str:
    """'2026-10-05T14:30:00+02:00' -> '05/10/2026 alle 14:30'."""
    if not ts:
        return "—"
    t = dt.datetime.fromisoformat(ts)
    return f"{t:%d/%m/%Y} alle {t:%H:%M}"


def hm(minuti, lungo: bool = False) -> str:
    """255 -> '4 h 15' (lungo: '4 h 15 min'); 45 -> '45 min'; 60 -> '1 h'."""
    minuti = int(minuti or 0)
    h, m = divmod(minuti, 60)
    if h and m:
        return f"{h} h {m:02d}" + (" min" if lungo else "")
    if h:
        return f"{h} h"
    return f"{m} min"


def ora(ts: str) -> str:
    return ts[11:16]


def minuti_da(ts: str) -> int:
    return int(ts[11:13]) * 60 + int(ts[14:16])


class Giornata:
    """Lettura comoda del JSON giornaliero per la presentazione."""

    def __init__(self, d: dict):
        self.d = d
        self.fasce = d["fasce"]
        self.cl = d.get("classificazione", {})
        self.t = d["totali"]["rilevati"]
        self.cm = d["totali"].get("con_manuali") or {"minuti_manuali": 0, "minuti_complessivi": self.t["minuti_attivita_rilevata"],
                                                       "minuti_manuali_sovrapposti": 0}

    def app(self, a):
        return (self.cl.get("applicazioni", {}).get(a) or {}).get("etichetta", a.replace("_", " ").capitalize())

    def cat_app(self, a):
        return (self.cl.get("applicazioni", {}).get(a) or {}).get("categoria", "")

    def sito(self, s):
        return (self.cl.get("siti", {}).get(s) or {}).get("etichetta", s)

    def cat_sito(self, s):
        return (self.cl.get("siti", {}).get(s) or {}).get("categoria", "")

    def cat(self, c):
        return self.cl.get("categorie", {}).get(c, c)

    def intervalli(self, ns) -> str:
        ns = sorted(set(ns))
        out, i = [], 0
        while i < len(ns):
            j = i
            while j + 1 < len(ns) and ns[j + 1] == ns[j] + 1:
                j += 1
            out.append(f"{self.fasce[ns[i]]['ora']}–{self._fine(ns[j])}")
            i = j + 1
        return ", ".join(out)

    def _fine(self, n):
        f = self.fasce[n]["fine"][11:16]
        return "24:00" if f == "00:00" and n == len(self.fasce) - 1 else f

    def fasce_di(self, chiave, valore):
        return [f["n"] for f in self.fasce if valore in f.get(chiave, [])]

    def fasce_manuale(self, m):
        a, b = minuti_da(m["inizio"]), minuti_da(m["fine"]) or 24 * 60
        return [f["n"] for f in self.fasce if minuti_da(f["inizio"]) < b and minuti_da(f["inizio"]) + 15 > a]

    def orario_sessione(self) -> tuple[str, str]:
        ev = [e for e in self.d.get("sessione", {}).get("eventi", []) if not e.get("implicito")]
        inizio = next((e["ora"] for e in ev if e["evento"] in ("accesso", "avvio_raccolta", "sblocco")), None)
        fine = next((e["ora"] for e in reversed(ev) if e["evento"] in ("chiusura", "spegnimento", "fine_raccolta")), None)
        return inizio or (self.t.get("prima_attivita") or "—"), fine or (self.t.get("ultima_attivita") or "—")

    def ore_estremi(self) -> tuple[int, int]:
        """Prima e ultima ora da mostrare (fasce osservate o con dichiarazioni), almeno 8 ore."""
        oss = [f["n"] for f in self.fasce if f["stato"] not in ("sessione_chiusa", "dato_non_disponibile")]
        oss += [n for m in self.d.get("manuali", []) for n in self.fasce_manuale(m)]
        if not oss:
            return 8, 16
        h0 = minuti_da(self.fasce[min(oss)]["inizio"]) // 60
        h1 = (minuti_da(self.fasce[max(oss)]["inizio"]) + 15 + 59) // 60
        h1 = max(h1, h0 + 1)
        if h1 - h0 < 8:
            h1 = min(24, h0 + 8)
            h0 = max(0, h1 - 8)
        return h0, h1

    def segnalate(self) -> set:
        return {n for s in self.d.get("segnalazioni_dipendente", []) if s.get("fascia_da") is not None
                for n in range(s["fascia_da"], s["fascia_a"] + 1)}

    def righe_revisione(self):
        """Fasce raggruppate per la revisione: [(n0, n1, stato, app, siti)] dalla prima all'ultima fascia osservata."""
        oss = [f["n"] for f in self.fasce if f["stato"] not in ("sessione_chiusa", "dato_non_disponibile")]
        if not oss:
            return []
        out = []
        for f in self.fasce[min(oss):max(oss) + 1]:
            k = (f["stato"], tuple(f["app"]), tuple(f["siti"]))
            if out and out[-1][2:] == k and out[-1][1] == f["n"] - 1:
                out[-1] = (out[-1][0], f["n"]) + k
            else:
                out.append((f["n"], f["n"]) + k)
        return out
