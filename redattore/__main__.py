"""Riga di comando del redattore AI-Light (M5).

  python -m redattore fatti rivisto.json                      elenco numerato dei fatti (ciò che vede il modello)
  python -m redattore sintetizza rivisto.json -o con_sintesi.json
        [--motore llamacpp --server PERCORSO/llama-server --modello PERCORSO/modello.gguf [--thread 4]]
        [--motore ollama --modello qwen3:1.7b] [--motore standard] [--adesso ISO]
  python -m redattore conferma con_sintesi.json -o confermato.json [--adesso ISO]     («Ho verificato la sintesi»)
  python -m redattore controlla con_sintesi.json              ripete il controllo anti-invenzione sulla sintesi salvata
  python -m redattore riscrivi con_sintesi.json -o nuovo.json [opzioni del motore]     («Riscrivi», max 3 volte)
  python -m redattore modifica con_sintesi.json -o nuovo.json --testo "…" [--accetta-avvisi]
        testo modificato dal dipendente (diventa dichiarato, ricontrollato; codice 3 = avvisi da confermare)
  python -m redattore profilo rivisto.json --modelli CARTELLA  profilo AI e modello che verrebbero usati
Con --motore auto (predefinito se c'è --modelli o RSW_MODELLI_AI) il modello si sceglie dal profilo: AI-STANDARD
(Qwen3-4B, PC ≥ 14 GB rilevati) o AI-LIGHT (Qwen3-1.7B), con ripiego se la memoria libera non basta.

Poi: python -m aggregatore sigilla-finale confermato.json --chiave DIR -o finale.json
Variabili d'ambiente (valori predefiniti): RSW_LLAMA_SERVER, RSW_MODELLO_AI, RSW_MODELLI_AI (cartella dei modelli),
RSW_CACHE_AI (cartella della cache del prefisso del prompt).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from aggregatore.cli import _load, _save
from . import controllo, fatti, motore, profilo, sintesi


def _opzioni_motore(p):
    p.add_argument("--motore", choices=["auto", "llamacpp", "ollama", "standard"], default=None)
    p.add_argument("--server", default=os.environ.get("RSW_LLAMA_SERVER"))
    p.add_argument("--modello", default=os.environ.get("RSW_MODELLO_AI"))
    p.add_argument("--modelli", default=os.environ.get("RSW_MODELLI_AI"))
    p.add_argument("--cache", default=os.environ.get("RSW_CACHE_AI"))
    p.add_argument("--profilo", choices=["AI-LIGHT", "AI-STANDARD"], help="forza il profilo")
    p.add_argument("--thread", type=int, default=4); p.add_argument("--adesso")


def _crea_motore(ns, doc):
    """(motore o None, profilo o None) oppure solleva ValueError."""
    tipo = ns.motore or ("auto" if ns.modelli else "llamacpp")
    if tipo == "standard":
        return None, None
    if tipo == "ollama":
        return motore.Ollama(ns.modello or "qwen3:1.7b", thread=ns.thread), None
    if not ns.server:
        raise ValueError("serve --server (o RSW_LLAMA_SERVER)")
    if tipo == "auto":
        if not ns.modelli:
            raise ValueError("serve --modelli (o RSW_MODELLI_AI)")
        sc = profilo.scegli(doc, ns.modelli, forza=ns.profilo)
        print(f"profilo {sc['profilo'] or '—'} (richiesto {sc['profilo_richiesto']}, {sc['motivo']})")
        if not sc["modello"]:
            return None, None
        return motore.LlamaCpp(ns.server, sc["modello"], thread=ns.thread, cache_prefisso=ns.cache), sc["profilo"]
    if not ns.modello:
        raise ValueError("servono --server e --modello (o RSW_LLAMA_SERVER / RSW_MODELLO_AI)")
    return motore.LlamaCpp(ns.server, ns.modello, thread=ns.thread, cache_prefisso=ns.cache), ns.profilo


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="redattore", description="Redattore AI-Light del Rendiconto SW (M5)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fatti"); f.add_argument("file")
    s = sub.add_parser("sintetizza"); s.add_argument("file"); s.add_argument("-o", "--out", required=True)
    _opzioni_motore(s)
    r = sub.add_parser("riscrivi"); r.add_argument("file"); r.add_argument("-o", "--out", required=True)
    _opzioni_motore(r)
    mo = sub.add_parser("modifica"); mo.add_argument("file"); mo.add_argument("-o", "--out", required=True)
    mo.add_argument("--testo", required=True); mo.add_argument("--accetta-avvisi", action="store_true")
    mo.add_argument("--adesso")
    pr = sub.add_parser("profilo"); pr.add_argument("file"); pr.add_argument("--modelli", default=os.environ.get("RSW_MODELLI_AI"))
    c = sub.add_parser("conferma"); c.add_argument("file"); c.add_argument("-o", "--out", required=True); c.add_argument("--adesso")
    k = sub.add_parser("controlla"); k.add_argument("file")
    ns = ap.parse_args(argv)
    try:
        if ns.cmd == "fatti":
            print(fatti.elenco(fatti.estrai(_load(ns.file))))
            return 0
        if ns.cmd == "profilo":
            print(json.dumps(profilo.scegli(_load(ns.file), ns.modelli or "."), ensure_ascii=False, indent=1))
            return 0
        if ns.cmd == "modifica":
            try:
                out = sintesi.modifica(_load(ns.file), ns.testo, ns.adesso, accetta_avvisi=ns.accetta_avvisi)
            except sintesi.AvvisiModifica as e:
                print("Il testo modificato contiene dati che non risultano nella giornata:")
                for x in e.problemi:
                    print(f"  - {x}")
                print("Correggere il testo oppure ripetere con --accetta-avvisi (gli avvisi restano nel resoconto).")
                return 3
            _save(out, ns.out)
            print(f"{ns.out}: sintesi modificata dal dipendente (dichiarata), controllo {out['sintesi_ai']['controllo_modifica']['esito']}")
            return 0
        if ns.cmd in ("sintetizza", "riscrivi"):
            doc = _load(ns.file)
            m, prof = _crea_motore(ns, doc)
            if ns.cmd == "riscrivi":
                nuovo = sintesi.riscrivi(doc, m, ns.adesso, profilo=prof)
                si = nuovo["sintesi_ai"]
            else:
                si = sintesi.genera(doc, m, adesso=ns.adesso, profilo=prof)
                nuovo = sintesi.applica(doc, si)
            _save(nuovo, ns.out)
            p = si["prestazioni"]
            print(f"{ns.out}: sintesi {si['esito']} ({len(si['frasi'])} frasi, controllo {si['controllo']['esito']}, "
                  f"tentativi {len(si['controllo']['tentativi'])}"
                  + (f", {p['secondi_totali']} s, picco {p['ram_picco_mb']} MB" if p.get("secondi_totali") else "") + ")")
            print(si["testo"])
            return 0
        if ns.cmd == "conferma":
            _save(sintesi.conferma(_load(ns.file), ns.adesso), ns.out)
            print(f"{ns.out}: sintesi confermata dal dipendente")
            return 0
        if ns.cmd == "controlla":
            doc = _load(ns.file)
            si = doc.get("sintesi_ai")
            if not si:
                print("nessuna sintesi nel file"); return 2
            attuali = fatti.estrai(doc)
            if fatti.impronta(attuali) != si["impronta_fatti"]:
                print("ALTERATO: i fatti attuali non corrispondono a quelli usati per la sintesi"); return 2
            if si.get("origine_testo") == "dichiarata":
                print("testo modificato dal dipendente (dichiarato)")
                r = sintesi.controlla_modifica(si["testo"], attuali)
            else:
                r = controllo.controlla(si["frasi"], attuali)
            print(f"controllo: {r['esito']}")
            for x in r["problemi"]:
                print(f"  - {x}")
            return 0 if r["esito"] == "superato" else 2
    except (ValueError, OSError, motore.ErroreMotore) as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
