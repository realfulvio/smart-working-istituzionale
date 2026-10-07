"""Riga di comando del collector (in M7 la stessa logica sarà dietro i pulsanti dell'interfaccia).

    python -m collector avvia [--presa-visione]   «Avvia giornata»
    python -m collector pausa                     «Pausa raccolta»
    python -m collector riprendi                  «Riprendi raccolta»
    python -m collector chiudi [--profilo sistemi_informativi]   «Chiudi giornata»
    python -m collector stato                     fase della giornata e consumo del processo di raccolta
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .giornata import ErroreGiornata, avvia, chiudi, pausa, riprendi
from .percorsi import Percorsi
from .stato import Stato


def riepilogo_diagnostica(p: Percorsi, giorno: str) -> dict:
    f = os.path.join(p.diagnostica, f"{giorno}.jsonl")
    if not os.path.exists(f):
        return {}
    righe = [json.loads(r) for r in open(f, encoding="utf-8") if r.strip()]
    if not righe:
        return {}
    # più esecuzioni (pause): ogni esecuzione riparte da secondi=0
    sec = cpu = 0.0
    prec = None
    for r in righe:
        if prec is not None and r["secondi"] < prec["secondi"]:
            sec += prec["secondi"]; cpu += prec["cpu_s"]
        prec = r
    sec += prec["secondi"]; cpu += prec["cpu_s"]
    return {"secondi": round(sec), "cpu_s": round(cpu, 2), "cpu_percento": round(100 * cpu / sec, 3) if sec else None,
            "ws_mb_max": max(r["ws_mb"] for r in righe), "picco_ws_mb": max(r["picco_ws_mb"] for r in righe),
            "privata_mb_max": max(r["privata_mb"] for r in righe), "campioni": len(righe)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="collector")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("avvia"); a.add_argument("--presa-visione", action="store_true")
    sub.add_parser("pausa"); sub.add_parser("riprendi")
    c = sub.add_parser("chiudi")
    c.add_argument("--senza-sigillo", action="store_true"); c.add_argument("--profilo", action="append", default=[])
    sub.add_parser("stato"); sub.add_parser("_esegui")
    a = ap.parse_args(argv)
    p = Percorsi.predefiniti()
    try:
        if a.cmd == "_esegui":
            from .demone import esegui
            esegui(p)
            return 0
        if a.cmd == "avvia":
            g = avvia(p, presa_visione=a.presa_visione)
            print(f"Giornata {g} in corso – raccolta attività attiva")
        elif a.cmd == "pausa":
            pausa(p); print("Raccolta in pausa")
        elif a.cmd == "riprendi":
            riprendi(p); print("Raccolta ripresa")
        elif a.cmd == "chiudi":
            r = chiudi(p, sigillo=not a.senza_sigillo, profili=a.profilo)
            print(json.dumps({**r, "consumo": riepilogo_diagnostica(p, r["giorno"])}, ensure_ascii=False, indent=1))
        elif a.cmd == "stato":
            st = Stato(p); g = st.giornata()
            print(json.dumps({"giornata": g, "raccolta_attiva": st.demone_attivo(), "processo": st.demone(),
                              "consumo": riepilogo_diagnostica(p, g.get("giorno", ""))}, ensure_ascii=False, indent=1))
        return 0
    except ErroreGiornata as e:
        print(f"errore: {e}", file=sys.stderr)
        return 2
