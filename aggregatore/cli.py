"""Riga di comando dell'aggregatore.

  python -m aggregatore aggrega raw.jsonl -o giorno.json [--chiave DIR] [--senza-sigillo] [--adesso ISO] [--mappa FILE]
        [--profilo sistemi_informativi]
  python -m aggregatore rivedi giorno.json --revisione revisione.jsonl [--osservazioni TESTO] -o rivisto.json
        (revisione.jsonl: righe 'manuale', 'segnalazione', 'osservazione'; --manuali è un sinonimo)
  python -m aggregatore sigilla-finale rivisto.json --chiave DIR -o finale.json [--adesso ISO]
  python -m aggregatore verifica file.json [--chiavi DIR ...] [--json] [--solo-tecnico]
  python -m aggregatore valida file.json            (controllo con schema/giornaliero.schema.json)
  python -m aggregatore registra-chiave pubblica.json --chiavi DIR
  python -m aggregatore valida-mappa [config/applicazioni.json]

Codici di uscita di «verifica»: 0 VALIDO, 1 INTEGRO, 2 ALTERATO / NON SIGILLATO / errore (anche eccezioni).
Senza il sigillo finale il file è NON SIGILLATO (dichiarazioni, osservazioni e sintesi non sono coperte dal solo
sigillo tecnico); --solo-tecnico verifica volutamente la sola parte tecnica.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

from . import aggrega, mappa, modelli, sigillo

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schema", "giornaliero.schema.json")


def _load(p: str) -> dict:
    return sigillo.load_stretto(p)          # rifiuta chiavi duplicate e NaN: il file deve avere un solo significato


def _save(doc: dict, p: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")


def _stretto(o):
    """Il «pattern» di JSON Schema è ECMA-262 (il «$» finale non accetta un a-capo finale); jsonschema usa re.search di
    Python, dove «$» accetta anche un a-capo finale: si sostituisce con \\Z (fine del testo) così «halley» + a-capo non
    è un identificativo valido."""
    if isinstance(o, dict):
        return {k: (v[:-1] + "\\Z" if k == "pattern" and isinstance(v, str) and v.endswith("$") and not v.endswith("\\$")
                    else _stretto(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [_stretto(x) for x in o]
    return o


def validate(doc: dict, schema_path: str = SCHEMA_PATH) -> list[str]:
    try:
        import jsonschema
    except ImportError:
        return ["jsonschema non installato: controllo dello schema saltato"]
    if schema_path == SCHEMA_PATH and doc.get("schema") == "rendiconto-sw/giornaliero/4":
        schema_path = os.path.join(os.path.dirname(SCHEMA_PATH), "giornaliero-v4.schema.json")
    if schema_path == SCHEMA_PATH and doc.get("schema") == "rendiconto-sw/giornaliero/3":
        schema_path = os.path.join(os.path.dirname(SCHEMA_PATH), "giornaliero-v3.schema.json")
    schema = _stretto(_load(schema_path))
    v = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    return [f"{'/'.join(map(str, e.absolute_path)) or '(radice)'}: {e.message}" for e in sorted(v.iter_errors(doc), key=str)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="aggregatore", description="Aggregatore Rendiconto SW (deterministico)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("aggrega"); a.add_argument("raw"); a.add_argument("-o", "--out", required=True)
    a.add_argument("--chiave", help="cartella della chiave (creata se manca)"); a.add_argument("--senza-sigillo", action="store_true")
    a.add_argument("--adesso", help="istante del sigillo (per esempi riproducibili)")
    a.add_argument("--mappa", help="mappatura applicazioni/siti (predefinita: config/applicazioni.json)")
    a.add_argument("--profilo", action="append", default=[],
                   help="profilo facoltativo dei siti da attivare (es. sistemi_informativi); ripetibile")
    r = sub.add_parser("rivedi"); r.add_argument("giorno"); r.add_argument("--revisione", "--manuali", dest="revisione")
    r.add_argument("--osservazioni", default=""); r.add_argument("-o", "--out", required=True)
    s = sub.add_parser("sigilla-finale"); s.add_argument("file"); s.add_argument("--chiave", required=True)
    s.add_argument("-o", "--out", required=True); s.add_argument("--adesso")
    v = sub.add_parser("verifica"); v.add_argument("file"); v.add_argument("--chiavi", action="append", default=[])
    v.add_argument("--json", action="store_true")
    v.add_argument("--solo-tecnico", action="store_true", help="verifica la sola parte tecnica (senza sigillo finale)")
    va = sub.add_parser("valida"); va.add_argument("file")
    rk = sub.add_parser("registra-chiave"); rk.add_argument("pubblica"); rk.add_argument("--chiavi", required=True)
    vm = sub.add_parser("valida-mappa"); vm.add_argument("file", nargs="?", default=mappa.PERCORSO_PREDEFINITO)
    ns = ap.parse_args(argv)

    try:
        if ns.cmd == "aggrega":
            inp = modelli.read_jsonl(ns.raw)
            mp = (mappa.Mappa.da_file(ns.mappa, ns.profilo) if ns.mappa
                  else mappa.Mappa.predefinita(ns.profilo) if ns.profilo else None)
            doc = aggrega.aggregate(inp, mp)
            if not ns.senza_sigillo:
                key = sigillo.load_or_create_key(ns.chiave or os.path.join(os.path.expanduser("~"), ".rendiconto_sw", "chiave"))
                doc = sigillo.seal_technical(doc, key, ns.adesso)
            _save(doc, ns.out)
            t = doc["totali"]["rilevati"]
            print(f"{ns.out}: {t['numero_fasce']} fasce, di cui con attività rilevata {(t.get('fasce_per_stato') or {}).get('attivita_rilevata', 0)}"
                  + (f", sigillo tecnico {doc['integrita']['sigillo_tecnico']['codice']}" if doc["integrita"]["sigillo_tecnico"] else ""))
            return 0
        if ns.cmd == "rivedi":
            doc = _load(ns.giorno)
            res = sigillo.verify(doc, check_final=False)
            if doc["integrita"].get("sigillo_tecnico") and not res["tecnico"]["valido"]:
                print("ERRORE: la parte tecnica non corrisponde al sigillo tecnico", file=sys.stderr)
                return 2
            rv = modelli.read_revisione(ns.revisione) if ns.revisione else modelli.Ingresso(None)
            oss = "\n".join([o for o in rv.osservazioni if o] + ([ns.osservazioni] if ns.osservazioni else []))
            doc = aggrega.apply_review(doc, rv.manuali, oss, rv.segnalazioni)
            doc["integrita"]["sigillo_finale"] = None
            _save(doc, ns.out)
            c = doc["totali"]["con_manuali"]
            print(f"{ns.out}: attività dichiarate {len(doc['manuali'])}, "
                  f"segnalazioni {len(doc['segnalazioni_dipendente'])}")
            return 0
        if ns.cmd == "sigilla-finale":
            doc = sigillo.seal_final(_load(ns.file), sigillo.load_or_create_key(ns.chiave), ns.adesso)
            _save(doc, ns.out)
            print(f"{ns.out}: sigillo finale {doc['integrita']['sigillo_finale']['codice']}")
            return 0
        if ns.cmd == "verifica":
            try:
                res = sigillo.verify(_load(ns.file), ns.chiavi)
            except (ValueError, OSError):
                raise
            except Exception as e:   # noqa: BLE001 - un file manomesso non deve mai uscire con un'eccezione (codice 1 = INTEGRO)
                print(f"ERRORE: dati non verificabili ({type(e).__name__})", file=sys.stderr)
                return 2
            if res["esito"] in ("VALIDO", "INTEGRO") and not res["finale"].get("presente") and not ns.solo_tecnico:
                res["esito"] = "NON SIGILLATO"
                res["motivi"].insert(0, "manca il sigillo finale: dichiarazioni, osservazioni e sintesi non sono coperte "
                                        "(usare --solo-tecnico per verificare la sola parte tecnica)")
            if ns.json:
                print(json.dumps(res, ensure_ascii=True, indent=1))
            else:
                print(f"ESITO: {res['esito']}  (fase: {res['fase']})")
                for k in ("tecnico", "finale"):
                    if res[k].get("presente"):
                        print(f"  sigillo {k}: {'valido' if res[k]['valido'] else 'NON valido'} — codice {res[k]['codice']}")
                for m in res["motivi"]:
                    print(f"  - {m}")
            return {"VALIDO": 0, "INTEGRO": 1}.get(res["esito"], 2)
        if ns.cmd == "valida":
            errs = validate(_load(ns.file))
            for e in errs:
                print(e)
            print("conforme allo schema" if not errs else f"{len(errs)} errori")
            return 0 if not errs else 2
        if ns.cmd == "registra-chiave":
            j = _load(ns.pubblica)
            os.makedirs(ns.chiavi, exist_ok=True)
            nome = f"{j.get('account', 'chiave').replace(chr(92), '_')}_{j.get('pc', '')}_{j['impronta'].replace(' ', '')[:8]}.json"
            shutil.copyfile(ns.pubblica, os.path.join(ns.chiavi, nome))
            print(f"chiave registrata: {nome}")
            return 0
        if ns.cmd == "valida-mappa":
            mp = mappa.Mappa.da_file(ns.file)
            tutti = mappa.Mappa.da_file(ns.file, [p for p in mp.profili if p != mappa.PROFILO_GENERALE])
            extra = {p: sum(1 for x in tutti.siti if x not in mp.siti) for p in mp.profili if p != mappa.PROFILO_GENERALE}
            print(f"mappatura {mp.versione}: {len(mp.per_exe)} eseguibili, {len(mp.per_id)} applicazioni, "
                  f"{len(mp.siti)} siti del profilo generale, {len(mp.categorie)} categorie"
                  + "".join(f"; profilo facoltativo {p}: {n} siti" for p, n in extra.items()))
            return 0
    except (modelli.ErroreIngresso, ValueError, OSError) as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
