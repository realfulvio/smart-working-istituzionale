"""Estrazione deterministica dei fatti dal JSON giornaliero (rivisto).

Ogni fatto è una frase breve e autosufficiente con un numero progressivo (id) e l'origine:
  automatico  – dati raccolti dalla postazione;
  dichiarato  – attività, osservazioni e segnalazioni inserite dal dipendente;
  combinato   – totali che sommano dati automatici e dichiarati.
Il modello riceve solo questo elenco, mai il JSON intero. La rete non entra nella sintesi (come nella pagina 1 del PDF).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
        "novembre", "dicembre"]
CATEGORIE_MANUALI = {"videoconferenza": "videoconferenza", "amministrativa_offline": "attività amministrativa offline", "riunione": "riunione", "telefonata": "telefonata", "cartaceo": "lavoro su documenti cartacei",
                     "sopralluogo": "sopralluogo", "formazione": "formazione", "altro": "altra attività"}
STATI_FINESTRA = [("nessuna_attivita_informatica_rilevata", "sessione attiva senza attività informatica rilevata"),
                  ("sessione_bloccata", "sessione bloccata"), ("sessione_disconnessa", "sessione disconnessa"),
                  ("sessione_chiusa", "sessione chiusa o PC spento"), ("raccolta_sospesa", "raccolta sospesa dal dipendente"),
                  ("dato_non_disponibile", "dato non disponibile")]
FONTI = {"sessione": "eventi di sessione", "app": "applicazioni",
         "attivita": "interazione con la postazione", "browser": "siti web"}


def durata(minuti: int) -> str:
    """255 -> «255 minuti (4 ore e 15 minuti)»; 45 -> «45 minuti»."""
    if minuti < 60:
        return f"{minuti} minuti" if minuti != 1 else "1 minuto"
    h, m = divmod(minuti, 60)
    hh = "1 ora" if h == 1 else f"{h} ore"
    return f"{minuti} minuti ({hh}" + (f" e {m} minuti)" if m else ")")


def _ora(ts: str) -> str:
    return ts[11:16]


def _etichetta(doc, tipo, chiave):
    c = doc.get("classificazione", {})
    if tipo == "app":
        return (c.get("applicazioni", {}).get(chiave) or {}).get("etichetta", chiave)
    if tipo == "sito":
        return (c.get("siti", {}).get(chiave) or {}).get("etichetta", chiave)
    return c.get("categorie", {}).get(chiave, chiave)


def _pulisci(s: str, n: int) -> str:
    s = " ".join((s or "").replace("«", "'").replace("»", "'").replace('"', "'").split()).rstrip(" .")
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _n(k: int, sing: str, plur: str) -> str:
    return f"{k} {sing if k == 1 else plur}"


PRIORITA = ["giorno", "totale_rilevato", "orari", "categorie", "manuale", "nessuna_dichiarata",
            "segnalazione", "osservazioni", "pausa", "finestra", "sessione", "applicazioni", "siti", "fonti"]


def estrai(doc: dict) -> list[dict]:
    """Elenco numerato dei fatti (deterministico: stesso JSON, stessi fatti), in ordine di importanza."""
    out = _estrai(doc)
    out.sort(key=lambda f: PRIORITA.index(f["tipo"]))     # sort stabile: l'ordine interno di ogni tipo resta
    for i, f in enumerate(out, 1):
        f["id"] = i
    return out


def _estrai(doc: dict) -> list[dict]:
    out: list[dict] = []

    def add(testo, origine="automatico", tipo="altro"):
        out.append({"id": len(out) + 1, "testo": testo, "origine": origine, "tipo": tipo})

    g = dt.date.fromisoformat(doc["giorno"])
    add(f"Giornata del resoconto: {GIORNI[g.weekday()]} {g.day} {MESI[g.month - 1]} {g.year}.", tipo="giorno")
    ril = doc["totali"]["rilevati"]
    fasce = doc["fasce"]
    attive = [f for f in fasce if f["stato"] == "attivita_rilevata"]
    if attive:
        add(f"Attività informatica rilevata in {_n(len(attive), 'fascia', 'fasce')} da {ril['durata_fascia_min']} minuti.", tipo="totale_rilevato")
        add(f"La prima fascia con attività informatica rilevata inizia alle {ril['prima_attivita']}; l'ultima termina "
            f"alle {ril['ultima_attivita']}.", tipo="orari")
        i0, i1 = attive[0]["n"], attive[-1]["n"]
        finestra = fasce[i0:i1 + 1]
        parti = []
        for st, et in STATI_FINESTRA:
            k = sum(1 for f in finestra if f["stato"] == st)
            if k:
                parti.append(f"{et} in {_n(k, 'fascia', 'fasce')}")
        if parti:
            add(f"Tra le {ril['prima_attivita']} e le {ril['ultima_attivita']}, oltre all'attività rilevata: "
                + "; ".join(parti) + ".", tipo="finestra")
    else:
        add("Nessuna fascia con attività informatica rilevata dalla postazione in questa giornata.", tipo="totale_rilevato")
    ses = doc.get("sessione", {})
    if ses.get("primo_evento") and ses.get("ultimo_evento") and ses["primo_evento"] != ses["ultimo_evento"]:
        add(f"Primo evento di sessione registrato alle {ses['primo_evento']}, ultimo alle {ses['ultimo_evento']}.",
            tipo="sessione")
    for p in (doc.get("raccolta") or {}).get("pause", [])[:3]:
        add(f"Raccolta dei dati sospesa dal dipendente dalle {p['dalle']} alle {p['alle']}.",
            tipo="pausa")
    pause = (doc.get("raccolta") or {}).get("pause", [])
    if len(pause) > 3:
        add(f"Altre {len(pause) - 3} sospensioni della raccolta.", tipo="pausa")
    # Bonifica B4: solo i nomi, in ordine alfabetico (niente minuti per strumento né classifiche)
    cats = sorted({_etichetta(doc, 'cat', c['categoria']) for c in ril.get("per_categoria", []) if c["categoria"] != "rete"})
    if cats:
        add("Categorie di attività rilevate: " + ", ".join(cats) + ".", tipo="categorie")
    apps = sorted({_etichetta(doc, 'app', a['app']) for a in ril.get("per_applicazione", [])})
    if apps:
        add("Applicazioni rilevate: " + ", ".join(apps) + ".", tipo="applicazioni")
    siti = sorted({_etichetta(doc, 'sito', s['sito']) for s in ril.get("per_sito", [])})
    if siti:
        add("Siti di lavoro riconosciuti: " + ", ".join(siti) + ".", tipo="siti")
    cop = doc.get("copertura_fonti", {})
    nd = [FONTI[k] for k in FONTI if cop.get(k) == "non_disponibile"]
    if nd:
        add("Fonti non disponibili per questa giornata: " + ", ".join(nd) + ".", tipo="fonti")
    for m in doc.get("manuali", []):
        add(f"Attività dichiarata dal dipendente ({CATEGORIE_MANUALI.get(m['categoria'], m['categoria'])}) dalle "
            f"{_ora(m['inizio'])} alle {_ora(m['fine'])}, {durata(m['minuti'])}: \"{_pulisci(m['descrizione'], 200)}\".",
            origine="dichiarato", tipo="manuale")
    if not doc.get("manuali"):
        add("Attività dichiarate dal dipendente: nessuna.", origine="dichiarato", tipo="nessuna_dichiarata")
    for s in doc.get("segnalazioni_dipendente", []):
        rif = f" per la fascia {s['dalle']}–{s['alle']}" if s.get("dalle") else ", senza fascia oraria"
        add(f"Segnalazione del dipendente su un dato tecnico ({s['campo']}){rif}: \"{_pulisci(s['nota'], 200)}\".",
            origine="osservazione" if doc.get("schema", "").endswith(("/4", "/5")) else "dichiarato", tipo="segnalazione")
    oss = (doc.get("osservazioni_dipendente") or "").strip()
    if oss:
        add(f"Osservazioni dichiarate dal dipendente: \"{_pulisci(oss, 500)}\".", origine="osservazione" if doc.get("schema", "").endswith(("/4", "/5")) else "dichiarato",
            tipo="osservazioni")
    return out


def impronta(fatti: list[dict]) -> str:
    return hashlib.sha256(json.dumps(fatti, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def elenco(fatti: list[dict]) -> str:
    """Testo per il prompt: «[3] (dichiarato) …»."""
    return "\n".join(f"[{f['id']}] ({f['origine']}) {f['testo']}" for f in fatti)
