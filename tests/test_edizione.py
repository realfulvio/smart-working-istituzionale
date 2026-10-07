import json
from resoconto import edizione
from tools.configura_edizione import prepara
import pytest

def test_materializzazione_rifiuta_residui(tmp_path, monkeypatch):
    monkeypatch.setenv("RENDICONTO_EDIZIONE", "neutra")
    (tmp_path / "residuo.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="residui"):
        prepara(tmp_path)
    assert (tmp_path / "residuo.json").read_text(encoding="utf-8") == "{}"

def test_neutra_non_copia_overlay(tmp_path, monkeypatch):
    monkeypatch.setenv("RENDICONTO_EDIZIONE", "neutra")
    prepara(tmp_path)
    j = json.loads((tmp_path / "ente.json").read_text(encoding="utf-8"))
    assert j["nome"] == "Il tuo Ente"
    assert j["logo"] == "identita.png"
    assert not (tmp_path / "edizioni").exists()
    assert json.loads((tmp_path / "edizione.json").read_text(encoding="utf-8"))["overlay"] is None

def test_overlay_risoluzione_e_fallback(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "edizioni/esempio").mkdir(parents=True)
    (root / "config/raccolta.json").write_text("{}", encoding="utf-8")
    (root / "edizioni/esempio/ente.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(edizione, "RADICE", root)
    monkeypatch.setenv("RENDICONTO_EDIZIONE", "esempio")
    assert edizione.percorso("ente.json") == root / "edizioni/esempio/ente.json"
    assert edizione.percorso("raccolta.json") == root / "config/raccolta.json"
