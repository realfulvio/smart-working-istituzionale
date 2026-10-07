"""Lettura, alla chiusura della giornata, delle fasce scritte dall'host dell'estensione."""
from __future__ import annotations

import datetime as dt
import json
import os

from aggregatore.mappa import Mappa
from collector.registro import RE_SITO

from . import GENERICO


def eventi(raw_dir: str, giorno: dt.date, mappa: Mappa, intervalli=None) -> list[tuple[str, dt.datetime, dict]]:
    """Eventi «web» (solo id del sito) del giorno. Le righe non valide, di altri giorni o fuori dai periodi di
    raccolta attiva (se indicati) si scartano; i duplicati si uniscono."""
    path = os.path.join(raw_dir, f"estensione-{giorno.isoformat()}.jsonl")
    out, visti = [], set()
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for riga in f:
            try:
                r = json.loads(riga)
                ts = dt.datetime.fromisoformat(r["ts"])
                sito = r["sito"]
            except (ValueError, KeyError, TypeError):
                continue
            if r.get("tipo") != "web" or ts.tzinfo is None or ts.date() != giorno:
                continue
            if not isinstance(sito, str) or not RE_SITO.match(sito) or (sito != GENERICO and sito not in mappa.siti):
                continue
            if intervalli is not None and not any(a <= ts < b for a, b in intervalli):
                continue
            if (ts, sito) in visti:
                continue
            visti.add((ts, sito))
            out.append(("web", ts, {"sito": sito}))
    return sorted(out, key=lambda e: (e[1], e[2]["sito"]))
