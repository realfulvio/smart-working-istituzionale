"""Archivio dei sorgenti per la build PyInstaller sulla VDI (tar.gz), dal commit indicato (git archive).

Collaudo ALFA3 N1: la build ALFA3 partiva da un archivio «minimo» scelto a mano, senza il pacchetto ``estensione``,
mentre il codice lo importava. Ora l'archivio contiene TUTTI i pacchetti di prima parte (anche quelli esclusi dalla
build con --exclude-module, che restano fuori dall'eseguibile per scelta esplicita) e il programma si ferma se un
modulo raggiungibile dagli eseguibili manca dall'elenco.
Uso: python tools/pacchetto/crea_sorgente_build.py <commit> <uscita.tgz>
"""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import moduli_app  # noqa: E402

ALTRI = ["config", "schema", "examples", "licenze", "tools/pacchetto", "LICENSE", "THIRD_PARTY_NOTICES.md",
         "requirements.txt"]


def elenco(radice: str = moduli_app.RADICE) -> list[str]:
    return sorted(moduli_app.pacchetti_prima_parte(radice)) + ALTRI


def controlla(voci: list[str]) -> list[str]:
    top = {v.split("/")[0] for v in voci}
    errori = []
    for tipo in moduli_app.INGRESSI:
        for m in moduli_app.grafo(moduli_app.INGRESSI[tipo]).moduli:
            if m.split(".")[0] not in top:
                errori.append(f"{tipo}: {m} raggiungibile ma non nell'archivio dei sorgenti")
    return errori


def main(argv: list[str]) -> int:
    commit, uscita = argv[1], argv[2]
    voci = elenco()
    err = controlla(voci) + moduli_app.problemi("app") + moduli_app.problemi("host")
    if err:
        print("\n".join(err))
        return 1
    with open(uscita, "wb") as f:
        subprocess.run(["git", "-C", moduli_app.RADICE, "archive", "--format=tar.gz", commit] + voci, stdout=f,
                       check=True)
    print(f"{uscita}: {len(voci)} voci da {commit}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
