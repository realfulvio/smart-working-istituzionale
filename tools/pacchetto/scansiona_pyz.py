"""Scansione dell'archivio PYZ di un eseguibile PyInstaller: i moduli di prima parte attesi ci sono tutti?

Uso (con il Python della build, che ha PyInstaller): python tools/pacchetto/scansiona_pyz.py <exe> [<exe> …]
Esito in JSON su stdout; codice 0 se nessun modulo atteso manca e i moduli esclusi (estensione) sono assenti.
Collaudo ALFA3 N1: «estensione» mancava ma era importata; ora è esclusa di proposito e importata solo protetta.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import moduli_app  # noqa: E402


def moduli_pyz(exe: str) -> tuple[set[str], str]:
    from PyInstaller.archive.readers import CArchiveReader
    arch = CArchiveReader(exe)
    for nome, voce in arch.toc.items():
        if voce[-1] == "z":                    # typecode PYZ
            pyz = arch.open_embedded_archive(nome)
            return set(pyz.toc.keys()), nome
    raise RuntimeError(f"nessun archivio PYZ in {exe}")


def main(argv: list[str]) -> int:
    attesi = moduli_app.moduli_attesi("app")
    esclusi = moduli_app.opzioni_build("build_app.ps1")["exclude-module"]
    pp = moduli_app.pacchetti_prima_parte()
    esito, ok = {}, True
    for exe in argv[1:]:
        mods, nome = moduli_pyz(exe)
        mancanti = [m for m in attesi if m not in mods]
        presenti_esclusi = sorted(m for m in mods if any(m == e or m.startswith(e + ".") for e in esclusi))
        prima_parte = sorted(m for m in mods if m.split(".")[0] in pp)
        esito[os.path.basename(exe)] = {"pyz": nome, "moduli_totali": len(mods), "prima_parte": len(prima_parte),
                                        "attesi": len(attesi), "mancanti": mancanti,
                                        "esclusi_presenti": presenti_esclusi,
                                        "pacchetti": sorted({m.split(".")[0] for m in prima_parte})}
        ok = ok and not mancanti and not presenti_esclusi
    print(json.dumps({"ok": ok, "esclusi_attesi": esclusi, "eseguibili": esito}, ensure_ascii=False, indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
