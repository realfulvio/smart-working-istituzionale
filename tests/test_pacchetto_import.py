"""Collaudo ALFA3 N1: ogni import di prima parte raggiungibile dagli eseguibili è raccolto da PyInstaller oppure
escluso di proposito E protetto (try/except ImportError). Controllo statico con ast, anche degli import nelle
funzioni (quello di «estensione» che ha rotto «Chiudi giornata» era dentro chiudi())."""
from __future__ import annotations

import os
import sys
import textwrap

import pytest

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RADICE, "tools", "pacchetto"))
import crea_sorgente_build  # noqa: E402
import moduli_app  # noqa: E402


def test_app_nessun_problema_di_import():
    assert moduli_app.problemi("app") == []


def test_host_nessun_problema_di_import():
    assert moduli_app.problemi("host") == []


def test_build_raccoglie_tutta_la_prima_parte_ed_esclude_estensione():
    op = moduli_app.opzioni_build("build_app.ps1")
    assert "estensione" in op["exclude-module"]
    usati = {m.split(".")[0] for m in moduli_app.grafo(moduli_app.INGRESSI["app"], {"estensione"}).moduli}
    assert usati <= set(op["collect-submodules"])
    assert {"aggregatore", "applicazione", "collector", "redattore", "resoconto",
            "verificatore"} <= set(op["collect-submodules"])


def test_import_di_estensione_nell_app_solo_protetti():
    g = moduli_app.grafo(moduli_app.INGRESSI["app"], {"estensione"})
    est = [i for i in g.imports if i.modulo.split(".")[0] == "estensione"]
    assert est, "atteso almeno l'import protetto in collector.giornata.carica_estensione"
    assert all(i.protetto for i in est), [(i.da, i.riga) for i in est if not i.protetto]
    assert {i.da for i in est} == {"collector.giornata"}
    assert not any(m.startswith("estensione") for m in g.moduli)


def test_moduli_attesi_comprendono_chiusura_e_collaudo():
    att = moduli_app.moduli_attesi("app")
    for m in ("collector.giornata", "collector.stato", "applicazione.smoke",
              "applicazione.gui", "resoconto.pdf", "resoconto.verifica", "verificatore.gui", "aggregatore.cli",
              "redattore.motore"):
        assert m in att, m
    assert not any(m.startswith("estensione") for m in att)


def _albero(tmp_path, codice: dict[str, str]):
    for rel, testo in codice.items():
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(textwrap.dedent(testo), encoding="utf-8")


def test_rileva_import_non_protetto_di_modulo_escluso(tmp_path):
    """Il caso ALFA3: import in una funzione, pacchetto escluso dalla build, nessuna protezione."""
    _albero(tmp_path, {
        "ing.py": "from app import chiusura\n",
        "app/__init__.py": "",
        "app/chiusura.py": """
            def chiudi():
                from est.host import intervalli
                return intervalli
            def chiudi_bene():
                try:
                    from est import lettore
                except ImportError:
                    lettore = None
                return lettore
            """,
        "est/__init__.py": "", "est/host.py": "intervalli = 1\n", "est/lettore.py": "",
    })
    g = moduli_app.grafo([str(tmp_path / "ing.py")], {"est"}, radice=str(tmp_path))
    est = [(i.da, i.modulo, i.protetto, i.in_funzione) for i in g.imports if i.modulo.startswith("est")]
    assert ("app.chiusura", "est.host", False, True) in est
    assert ("app.chiusura", "est", True, True) in est
    assert not any(m.startswith("est") for m in g.moduli)


def test_rileva_modulo_mancante_nel_sorgente(tmp_path):
    _albero(tmp_path, {"ing.py": "import app.nonce\n", "app/__init__.py": ""})
    g = moduli_app.grafo([str(tmp_path / "ing.py")], radice=str(tmp_path))
    assert "app.nonce" in g.mancanti


def test_import_relativi_risolti(tmp_path):
    _albero(tmp_path, {"ing.py": "from app import a\n", "app/__init__.py": "",
                       "app/a.py": "from . import b\nfrom .c import x\n", "app/b.py": "", "app/c.py": "x = 1\n"})
    g = moduli_app.grafo([str(tmp_path / "ing.py")], radice=str(tmp_path))
    assert {"app", "app.a", "app.b", "app.c"} <= g.moduli


def test_archivio_sorgenti_build_completo():
    voci = crea_sorgente_build.elenco()
    assert crea_sorgente_build.controlla(voci) == []
    for v in ("estensione", "examples", "tools/pacchetto", "config", "schema"):
        assert v in voci


def test_archivio_sorgenti_senza_estensione_viene_rifiutato():
    """La build ALFA3 partiva da un archivio senza «estensione»: ora il controllo lo segnala."""
    voci = [v for v in crea_sorgente_build.elenco() if v != "estensione"]
    err = crea_sorgente_build.controlla(voci)
    assert any("estensione" in e for e in err)


@pytest.mark.parametrize("pkg", sorted(moduli_app.pacchetti_prima_parte()))
def test_nessun_import_dinamico_non_verificabile(pkg):
    for d, _, files in os.walk(os.path.join(RADICE, pkg)):
        for f in files:
            if f.endswith(".py"):
                rel = os.path.relpath(os.path.join(d, f), RADICE)[:-3].replace(os.sep, ".")
                _, din = moduli_app.import_di_file(os.path.join(d, f), rel, moduli_app.pacchetti_prima_parte())
                assert din == [], din
