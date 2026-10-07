"""Grafo statico degli import di prima parte degli eseguibili (RendicontoSW.exe, VerificaRendiconto.exe, host).

Nato dal collaudo ALFA3 (N1): il pacchetto ``estensione`` mancava nell'eseguibile ma «Chiudi giornata» lo importava.
Qui si leggono (con ast, senza eseguire nulla) tutti gli import raggiungibili dai punti d'ingresso, anche quelli
dentro le funzioni, e per ciascuno si annota se è «protetto» (dentro un try che cattura ImportError).
Usato da: tests/test_pacchetto_import.py (controllo statico), crea_sorgente_build.py (sorgenti per la build sulla VDI)
e scansiona_pyz.py (moduli attesi nell'archivio PYZ dell'eseguibile congelato).
"""
from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field

RADICE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PACCHETTO = os.path.join(RADICE, "tools", "pacchetto")
INGRESSI = {"app": ["app_entry.py", "verifica_entry.py"], "host": ["host_entry.py"]}
SCRIPT_BUILD = {"app": "build_app.ps1", "host": "build_host.ps1"}
ECCEZIONI_IMPORT = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}


def pacchetti_prima_parte(radice: str = RADICE) -> set[str]:
    return {d for d in os.listdir(radice)
            if os.path.isfile(os.path.join(radice, d, "__init__.py")) and d not in ("tests", "build")}


@dataclass
class Import:
    modulo: str            # nome assoluto importato (es. "estensione.lettore")
    da: str                # modulo che importa
    riga: int
    protetto: bool         # dentro try/except ImportError
    in_funzione: bool


@dataclass
class Grafo:
    moduli: set[str] = field(default_factory=set)          # moduli di prima parte raggiungibili (file trovati)
    mancanti: set[str] = field(default_factory=set)        # importati ma senza file nel sorgente
    imports: list[Import] = field(default_factory=list)
    dinamici: list[tuple[str, int, str]] = field(default_factory=list)   # import non letterali (modulo, riga, testo)


def file_modulo(nome: str, radice: str = RADICE) -> str | None:
    base = os.path.join(radice, *nome.split("."))
    for c in (base + ".py", os.path.join(base, "__init__.py")):
        if os.path.isfile(c):
            return c
    return None


def _protegge(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    tipi = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(isinstance(t, ast.Name) and t.id in ECCEZIONI_IMPORT for t in tipi)


def _assoluto(nome_modulo: str, e_pacchetto: bool, livello: int, modulo: str | None) -> str:
    if livello == 0:
        return modulo or ""
    parti = nome_modulo.split(".")
    if not e_pacchetto:
        parti = parti[:-1]
    parti = parti[:len(parti) - (livello - 1)] if livello > 1 else parti
    return ".".join(parti + ([modulo] if modulo else []))


def import_di_file(path: str, nome_modulo: str, prima_parte: set[str],
                   radice: str = RADICE) -> tuple[list[Import], list]:
    with open(path, encoding="utf-8") as f:
        albero = ast.parse(f.read(), path)
    e_pacchetto = os.path.basename(path) == "__init__.py"
    out, dinamici = [], []

    def visita(nodo, protetto: bool, in_funzione: bool):
        if isinstance(nodo, ast.Try) or (hasattr(ast, "TryStar") and isinstance(nodo, getattr(ast, "TryStar"))):
            p = protetto or any(_protegge(h) for h in nodo.handlers)
            for x in nodo.body:
                visita(x, p, in_funzione)
            for x in nodo.handlers + nodo.orelse + nodo.finalbody:
                visita(x, protetto, in_funzione)
            return
        f = in_funzione or isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
        if isinstance(nodo, ast.Import):
            for a in nodo.names:
                if a.name.split(".")[0] in prima_parte:
                    out.append(Import(a.name, nome_modulo, nodo.lineno, protetto, in_funzione))
        elif isinstance(nodo, ast.ImportFrom):
            base = _assoluto(nome_modulo, e_pacchetto, nodo.level, nodo.module)
            if base.split(".")[0] in prima_parte:
                out.append(Import(base, nome_modulo, nodo.lineno, protetto, in_funzione))
                for a in nodo.names:          # «from pacchetto import sottomodulo»
                    sotto = f"{base}.{a.name}"
                    if a.name != "*" and file_modulo(sotto, radice):
                        out.append(Import(sotto, nome_modulo, nodo.lineno, protetto, in_funzione))
        elif isinstance(nodo, ast.Call):
            fn = nodo.func
            nome = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else ""
            if nome in ("import_module", "__import__") and nodo.args:
                a0 = nodo.args[0]
                if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                    if a0.value.split(".")[0] in prima_parte:
                        out.append(Import(a0.value, nome_modulo, nodo.lineno, protetto, in_funzione))
                else:
                    # Un solo ingresso esterno documentato: l'archivio storico del CED,
                    # materializzato nella config. Il loader valida nomi pdf_<cifre>.
                    archivio = (nome_modulo in ("resoconto.storico", "resoconto.storico.__init__")
                                and ast.unparse(nodo) == "importlib.import_module('.' + nome, __name__)"
                                and "re.fullmatch('pdf_[0-9]+', nome)" in ast.unparse(albero))
                    if not archivio:
                        dinamici.append((nome_modulo, nodo.lineno, ast.unparse(nodo)[:120]))
        for figlio in ast.iter_child_nodes(nodo):
            visita(figlio, protetto, f)
    visita(albero, False, False)
    return out, dinamici


def grafo(ingressi: list[str], escludi: set[str] = frozenset(), radice: str = RADICE) -> Grafo:
    """Visita gli import dai file d'ingresso; non entra nei moduli esclusi dalla build (escludi)."""
    pp = pacchetti_prima_parte(radice)
    g = Grafo()
    da_fare: list[tuple[str, str]] = []
    for ing in ingressi:
        p = os.path.join(PACCHETTO, ing) if not os.path.isabs(ing) else ing
        da_fare.append(("__main__:" + os.path.basename(p), p))
    visti = set()
    while da_fare:
        nome, path = da_fare.pop()
        if path in visti:
            continue
        visti.add(path)
        imps, din = import_di_file(path, nome if not nome.startswith("__main__:") else "__main__", pp, radice)
        g.dinamici += din
        for imp in imps:
            g.imports.append(imp)
            parti = imp.modulo.split(".")
            # anche i pacchetti genitori vengono importati (es. «collector» per «collector.stato»)
            for i in range(1, len(parti) + 1):
                m = ".".join(parti[:i])
                if any(m == x or m.startswith(x + ".") for x in escludi):
                    break
                fm = file_modulo(m, radice)
                if fm is None:
                    if i == len(parti):
                        g.mancanti.add(m)
                    continue
                g.moduli.add(m)
                da_fare.append((m, fm))
    return g


def opzioni_build(script: str) -> dict[str, list[str]]:
    """--exclude-module / --hidden-import / --collect-submodules dello script di build PowerShell."""
    with open(os.path.join(PACCHETTO, script), encoding="utf-8-sig") as f:
        testo = "\n".join(r for r in f.read().splitlines() if not r.lstrip().startswith("#"))
    out = {}
    for op in ("exclude-module", "hidden-import", "collect-submodules"):
        out[op] = [x for x in re.findall(r'["\']?--' + op + r'["\']?\s*,?\s*["\']?([A-Za-z0-9_.$]+)', testo)
                   if not x.startswith("$")]
    # elenco dei pacchetti di prima parte raccolti con un ciclo: $primaParte = @("a", "b", …)
    m = re.search(r'\$primaParte\s*=\s*@\(([^)]*)\)', testo)
    if m and re.search(r'--collect-submodules["\']?\s*,\s*\$m\b', testo):
        out["collect-submodules"] += re.findall(r'["\']([A-Za-z0-9_.]+)["\']', m.group(1))
    return out


def problemi(tipo: str = "app", radice: str = RADICE) -> list[str]:
    """Elenco dei problemi di confezionamento per gli eseguibili «app» o «host» (vuoto = tutto a posto)."""
    op = opzioni_build(SCRIPT_BUILD[tipo])
    escludi = set(op["exclude-module"])
    g = grafo(INGRESSI[tipo], escludi, radice)
    raccolti = set(op["collect-submodules"]) | set(op["hidden-import"])
    pp = pacchetti_prima_parte(radice)
    out = []
    for imp in g.imports:
        esclusa = next((x for x in escludi if imp.modulo == x or imp.modulo.startswith(x + ".")), None)
        if esclusa and not imp.protetto:
            out.append(f"{imp.da}:{imp.riga} importa {imp.modulo}, escluso dalla build ({esclusa}), senza "
                       "protezione try/except ImportError")
    for m in sorted(g.mancanti):
        out.append(f"modulo di prima parte importato ma assente nel sorgente: {m}")
    if tipo == "app":
        for top in sorted({m.split(".")[0] for m in g.moduli} & pp):
            if top not in raccolti:
                out.append(f"pacchetto di prima parte {top} usato dall'app ma non elencato in --collect-submodules "
                           f"di {SCRIPT_BUILD[tipo]}")
        for top in sorted(raccolti & pp):
            if top in escludi:
                out.append(f"{top} è sia raccolto sia escluso")
    for nome, riga, testo in g.dinamici:
        out.append(f"{nome}:{riga} import dinamico non letterale (non verificabile): {testo}")
    return out


def moduli_attesi(tipo: str = "app", radice: str = RADICE) -> list[str]:
    """Moduli di prima parte che devono stare nell'archivio PYZ (grafo statico + sottomoduli raccolti)."""
    op = opzioni_build(SCRIPT_BUILD[tipo])
    escludi = set(op["exclude-module"])
    m = set(grafo(INGRESSI[tipo], escludi, radice).moduli)
    for top in op["collect-submodules"]:
        if top in pacchetti_prima_parte(radice):
            for d, _, files in os.walk(os.path.join(radice, top)):
                if "__pycache__" in d:
                    continue
                rel = os.path.relpath(d, radice).replace(os.sep, ".")
                for f in files:
                    if f.endswith(".py"):
                        m.add(rel if f == "__init__.py" else f"{rel}.{f[:-3]}")
    return sorted(x for x in m if not any(x == e or x.startswith(e + ".") for e in escludi)
                  and not x.endswith(".__main__"))


if __name__ == "__main__":
    import sys
    t = sys.argv[1] if len(sys.argv) > 1 else "app"
    pr = problemi(t)
    print("\n".join(pr) if pr else f"{t}: nessun problema di import")
    sys.exit(1 if pr else 0)
