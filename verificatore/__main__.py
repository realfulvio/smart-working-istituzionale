"""python -m verificatore FILE [--chiavi DIR] [--json] [--gui]"""
import argparse
import json
import sys

from resoconto.verifica import verifica_file


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="verificatore", description="Verifica un resoconto (PDF o JSON)")
    ap.add_argument("file", nargs="?")
    ap.add_argument("--chiavi", action="append", default=[], help="cartella del registro delle chiavi (ripetibile)")
    ap.add_argument("--json", action="store_true", help="esito in JSON")
    ap.add_argument("--gui", action="store_true", help="apri la finestra")
    ns = ap.parse_args(argv)
    if ns.gui or not ns.file:
        from .gui import main as gui
        return gui(([ns.file] if ns.file else []) + sum((["--chiavi", c] for c in ns.chiavi), []))
    r = verifica_file(ns.file, ns.chiavi)
    if ns.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(f"{r['esito']}: {ns.file}")
        for m in r["motivi"]:
            print(f"  - {m}")
    return {"VALIDO": 0, "INTEGRO": 0}.get(r["esito"], 1 if r["esito"] == "ALTERATO" else 2)


if __name__ == "__main__":
    sys.exit(main())
