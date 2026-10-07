"""Solo verifica dello schema /3: non usato per nuove giornate."""
import datetime as dt
from zoneinfo import ZoneInfo
from .aggrega import day_bounds, _fine_label, merge, minutes, intersect, STATI_FASCIA
FASCIA_MIN = 15

def compute_rilevati(fasce: list, giorno, fuso: str) -> dict:
    """Totali tecnici ricalcolabili dalle sole fasce (usato anche dalla verifica di coerenza)."""
    tz = ZoneInfo(fuso)
    if isinstance(giorno, str):
        giorno = dt.date.fromisoformat(giorno)
    _, end = day_bounds(giorno, fuso)
    conta = {s: 0 for s in STATI_FASCIA}
    per_app: dict[str, int] = {}
    per_cat: dict[str, int] = {}
    per_sito: dict[str, int] = {}
    for f in fasce:
        for x in f.get("siti", []):
            per_sito[x] = per_sito.get(x, 0) + 1
        conta[f["stato"]] += 1
        for ap in f["app"]:
            per_app[ap] = per_app.get(ap, 0) + 1
        for c in f["categorie"]:
            per_cat[c] = per_cat.get(c, 0) + 1
    attive = [f for f in fasce if f["stato"] == "attivita_rilevata"]
    ordina = lambda d: sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))  # noqa: E731
    return {
        "durata_fascia_min": FASCIA_MIN,
        "numero_fasce": len(fasce),
        "fasce_per_stato": conta,
        "minuti_per_stato": {s: c * FASCIA_MIN for s, c in conta.items()},
        "minuti_attivita_rilevata": conta["attivita_rilevata"] * FASCIA_MIN,
        "prima_attivita": attive[0]["ora"] if attive else None,
        "ultima_attivita": _fine_label(attive[-1]["fine"], end, tz) if attive else None,
        "per_applicazione": [{"app": k, "fasce": v, "minuti": v * FASCIA_MIN} for k, v in ordina(per_app)],
        "per_categoria": [{"categoria": k, "fasce": v, "minuti": v * FASCIA_MIN} for k, v in ordina(per_cat)],
        "per_sito": [{"sito": k, "fasce": v, "minuti": v * FASCIA_MIN} for k, v in ordina(per_sito)],
        "fasce_con_rete": sum(1 for f in fasce if f["rete"]),
        "operazioni_rete": sum(f["rete"] for f in fasce),
        "fasce_con_note_tecniche": sum(1 for f in fasce if f["note_tecniche"]),
    }


def _manual_intervals(doc: dict) -> list:
    return [(dt.datetime.fromisoformat(x["inizio"]), dt.datetime.fromisoformat(x["fine"])) for x in doc["manuali"]]


def _active_intervals(doc: dict) -> list:
    return [(dt.datetime.fromisoformat(f["inizio"]), dt.datetime.fromisoformat(f["fine"]))
            for f in doc["fasce"] if f["stato"] == "attivita_rilevata"]


def compute_con_manuali(doc: dict) -> dict:
    att, man = merge(_active_intervals(doc)), merge(_manual_intervals(doc))
    return {"minuti_manuali": minutes(man),
            "minuti_manuali_sovrapposti": minutes(intersect(att, man)),
            "minuti_complessivi": minutes(merge(att + man))}


