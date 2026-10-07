"""ALFA3: opzioni di collaudo headless degli entry point congelati (PDF da JSON + verifica su file)."""
import json
import runpy
import sys
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[1]
ESEMPIO = RADICE / "examples" / "01_giornata_ufficio" / "finale.json"
CHIAVI = RADICE / "examples" / "chiavi_registrate"


def _esegui(script, argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", [script] + argv)
    with pytest.raises(SystemExit) as e:
        runpy.run_path(str(RADICE / "tools" / "pacchetto" / script), run_name="__main__")
    return e.value.code


def test_smoke_pdf_e_verifica_su_file(tmp_path, monkeypatch):
    pdf = tmp_path / "prova.pdf"
    esito_pdf = tmp_path / "esito_pdf.json"
    assert _esegui("app_entry.py", ["--smoke-pdf", str(ESEMPIO), str(pdf), "--esito", str(esito_pdf)], monkeypatch) == 0
    assert pdf.is_file() and json.loads(esito_pdf.read_text(encoding="utf-8"))["ok"] is True
    esito = tmp_path / "esito_ver.json"
    codice = _esegui("verifica_entry.py", [str(pdf), "--chiavi", str(CHIAVI), "--esito", str(esito)], monkeypatch)
    r = json.loads(esito.read_text(encoding="utf-8"))
    assert codice == 0 and r["esito"] in ("VALIDO", "INTEGRO"), r


def test_smoke_pdf_errore_riportato(tmp_path, monkeypatch):
    esito = tmp_path / "e.json"
    codice = _esegui("app_entry.py", ["--smoke-pdf", str(tmp_path / "manca.json"), str(tmp_path / "x.pdf"),
                                      "--esito", str(esito)], monkeypatch)
    assert codice == 1 and json.loads(esito.read_text(encoding="utf-8"))["ok"] is False
