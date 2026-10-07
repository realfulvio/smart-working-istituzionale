"""Punto di ingresso di VerificaRendiconto.exe (PyInstaller).

Opzione di collaudo senza finestra: FILE [--chiavi DIR] --esito FILE_JSON scrive l'esito in JSON (exe senza console).
"""
import sys


def _esito_su_file(argv) -> int:
    import json
    from resoconto.verifica import verifica_file
    args = argv[1:]
    esito = args[args.index("--esito") + 1]
    chiavi = [args[i + 1] for i, a in enumerate(args) if a == "--chiavi"]
    salta = {"--esito", "--chiavi"}
    file = None
    i = 0
    while i < len(args):
        if args[i] in salta:
            i += 2
            continue
        file = args[i]
        i += 1
    r = verifica_file(file, chiavi)
    with open(esito, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1, default=str)
    return {"VALIDO": 0, "INTEGRO": 0}.get(r["esito"], 1 if r["esito"] == "ALTERATO" else 2)


if __name__ == "__main__":
    if "--esito" in sys.argv:
        sys.exit(_esito_su_file(sys.argv))
    from verificatore.gui import main
    sys.exit(main())
