import json
import sys
from pathlib import Path

from applicazione import servizio
from redattore import profilo


def test_installazione_alternativa_preferisce_runtime_e_modello_propri(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "locale"))
    normal = tmp_path / "locale/Programs/RendicontoSW/ai"
    adjacent = tmp_path / "collaudo/ai"
    for ai in (normal, adjacent):
        (ai / "llama").mkdir(parents=True)
        (ai / "modelli").mkdir()
        (ai / "llama" / servizio._EXE_LLAMA).write_bytes(b"test")
    (adjacent / "modelli" / profilo.MODELLI["AI-LIGHT"]).write_bytes(b"fixture")
    cfg = tmp_path / "app.json"
    cfg.write_text(json.dumps({"server_ai": str(normal / "llama" / servizio._EXE_LLAMA),
                               "modelli_ai": str(normal / "modelli")}), encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(adjacent.parent / "RendicontoSW.exe"))
    imp = servizio.carica_impostazioni(str(tmp_path / "dati"), str(cfg))
    assert Path(imp["server_ai"]).parent.parent == adjacent
    assert Path(imp["modelli_ai"]) == adjacent / "modelli"


def test_cause_locali_e_nessun_avvio_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(profilo, "memoria_gb", lambda: (8, 4))
    imp = servizio.impostazioni_predefinite(str(tmp_path))
    imp.update(server_ai=str(tmp_path / servizio._EXE_LLAMA), modelli_ai=str(tmp_path / "modelli"))
    s = servizio.Servizio(str(tmp_path / "base"), impostazioni=imp)
    assert s.disponibilita_ai()["causa"] == "runtime_assente"
    Path(imp["server_ai"]).write_bytes(b"fixture")
    assert s.disponibilita_ai()["causa"] == "modello_assente"
    model = Path(imp["modelli_ai"]) / profilo.MODELLI["AI-LIGHT"]
    model.parent.mkdir(); model.write_bytes(b"fixture")
    assert s.disponibilita_ai()["profilo"] == "AI-LIGHT"
    monkeypatch.setattr(profilo, "memoria_gb", lambda: (16, 1))
    assert s.disponibilita_ai()["causa"] == "memoria_insufficiente"
    monkeypatch.setattr(servizio.os, "access", lambda *a: False)
    assert s.disponibilita_ai()["causa"] == "permesso_negato"


def test_scelta_testo_standard_non_dichiara_ai_assente():
    assert servizio._profilo_pubblico({"motivo": "Testo standard richiesto"}) == {"motivo": "Testo standard richiesto"}
    out = servizio._profilo_pubblico({"messaggio": "modello non installato", "server_ai": "path privato", "memoria_gb": {"totale": 8}})
    assert out == {"motivo": "modello non installato"}
