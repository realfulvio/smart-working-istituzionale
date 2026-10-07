"""Giornate inventate per test, demo e benchmark. Nessun sensore né dato reale.

Uso: py tools/simula_edizione.py --output <cartella-nuova>
Non scrive nei percorsi operativi e non sovrascrive cartelle esistenti.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aggregatore import aggrega, modelli
from aggregatore.mappa import Mappa
from redattore import fatti, sintesi

GIORNO = "2026-10-05"


def mappa_sintetica():
    return Mappa.da_dict({"versione": "edizione-sintetica-1", "categorie": {
        "office": "Strumenti d'ufficio", "posta": "Applicazione di posta elettronica",
        "web_generico": "Web", "halley": "Gestionale Halley",
        "interazione_postazione": "Interazione tecnica"}, "applicazioni": {
        "WINWORD.EXE": {"id": "word", "etichetta": "Microsoft Word", "categoria": "office"},
        "OUTLOOK.EXE": {"id": "outlook", "etichetta": "Microsoft Outlook", "categoria": "posta"},
        "MSEDGE.EXE": {"id": "browser", "etichetta": "Web", "categoria": "web_generico"}},
        "siti": {"halley": {"etichetta": "Halley", "categoria": "halley", "domini": ["gestionale.esempio.test"]}}})


def righe(giorno=GIORNO, scenario="ordinaria"):
    def ts(ora):
        return f"{giorno}T{ora}:00+02:00"
    def s(ora, evento):
        return {"tipo": "sessione", "ts": ts(ora), "evento": evento}
    def a(ora, exe):
        return {"tipo": "app", "ts": ts(ora), "exe": exe}
    meta = {"tipo": "meta", "giorno": giorno, "fuso": "Europe/Rome", "modalita": "collector",
            "dipendente": {"nome": "Rossi Maria (ESEMPIO)", "ufficio": "Ufficio dimostrativo"},
            "copertura_fonti": {"sessione": "completa", "app": "parziale", "attivita": "parziale",
                                 "rete": "non_installato", "browser": "non_installato"}}
    if scenario == "senza_segnali":
        return [meta, s("08:00", "avvio_raccolta"), s("14:00", "fine_raccolta")]
    eventi = [meta, s("08:00", "avvio_raccolta"), a("08:01", "WINWORD.EXE"), a("08:04", "OUTLOOK.EXE"),
              a("08:15", "OUTLOOK.EXE"), a("08:30", "WINWORD.EXE"),
              s("09:00", "blocco"), s("09:30", "sblocco"), a("09:31", "WINWORD.EXE"),
              s("11:00", "disconnessione"), s("11:30", "riconnessione"),
              a("12:00", "WINWORD.EXE"), s("14:00", "fine_raccolta")]
    if scenario == "halley_poc":
        # Evento inventato in formato normalizzato esistente. Non abilita l'estensione.
        eventi.insert(-1, {"tipo": "web", "ts": ts("10:02"), "sito": "halley"})
    return eventi


def genera(scenario="ordinaria"):
    records = righe(scenario=scenario)
    records += [{"tipo": "manuale", "inizio": f"{GIORNO}T10:00:00+02:00", "fine": f"{GIORNO}T10:30:00+02:00",
                 "categoria": "riunione", "descrizione": "Confronto organizzativo (ESEMPIO)"},
                {"tipo": "manuale", "inizio": f"{GIORNO}T13:00:00+02:00", "fine": f"{GIORNO}T13:15:00+02:00",
                 "categoria": "amministrativa_offline", "descrizione": "Attività offline (ESEMPIO)"},
                {"tipo": "osservazione", "testo": "Giornata inventata, destinata esclusivamente a test e demo."}]
    doc = aggrega.aggregate(modelli.parse_records(records), mappa_sintetica())
    return records, doc


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    for scenario in ("ordinaria", "senza_segnali", "halley_poc"):
        folder = args.output / scenario
        folder.mkdir()
        records, doc = genera(scenario)
        (folder / "raw.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
        (folder / "giorno.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (folder / "fatti-ai.json").write_text(json.dumps(fatti.estrai(doc), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (folder / "fallback.json").write_text(json.dumps(sintesi.genera(doc, None, adesso=f"{GIORNO}T14:00:00+02:00"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Tre giornate sintetiche scritte in {args.output}")


if __name__ == "__main__":
    main()
