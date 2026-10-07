import copy
import io
import json

from pypdf import PdfReader
from aggregatore import aggrega, modelli, sigillo
from aggregatore.cli import validate
from collector import giornata, postazione
from collector.percorsi import Percorsi
from redattore import fatti, sintesi
from resoconto import ente
from resoconto.pdf import crea_pdf, pdf_bytes
from resoconto.verifica import verifica_file
from tools.simula_edizione import genera, mappa_sintetica

POST = {"nome_macchina": "PC-SEGRETO-ESEMPIO", "tipo": "VDI", "sistema_operativo": "Windows 11 build 26100",
        "processore": "CPU-SEGRETA-ESEMPIO", "ram_gb": 8}


def test_flag_disattivato_non_legge_hardware(tmp_path, monkeypatch):
    monkeypatch.setattr(ente, "carica", lambda: {"dati_tecnici_postazione": False})
    def vietata():
        raise AssertionError("hardware letto con flag disattivato")
    monkeypatch.setattr(postazione, "rileva", vietata)
    assert "dati_tecnici_postazione" not in giornata.meta(Percorsi(str(tmp_path)), "2026-10-07")


def test_snapshot_tecnico_sigillato_non_cambia_fatti_ne_sintesi(tmp_path):
    records, original = genera()
    records[0]["dati_tecnici_postazione"] = {**POST, "ip": "VIETATO", "sid": "VIETATO", "numero_serie": "VIETATO"}
    doc = aggrega.aggregate(modelli.parse_records(records), mappa_sintetica())
    assert doc["dati_tecnici_postazione"] == POST
    assert fatti.estrai(doc) == fatti.estrai(original)
    assert sintesi.genera(doc, None, adesso="2026-10-07T14:00:00+02:00") == sintesi.genera(original, None, adesso="2026-10-07T14:00:00+02:00")
    key = sigillo.load_or_create_key(str(tmp_path / "chiave"))
    doc = sigillo.seal_final(sigillo.seal_technical(doc, key), key)
    assert validate(doc) == []
    assert sigillo.verify(doc, [str(tmp_path / "chiave")])["esito"] == "VALIDO"
    for field, value in POST.items():
        changed = copy.deepcopy(doc)
        changed["dati_tecnici_postazione"][field] = 16 if field == "ram_gb" else "PC fisso" if field == "tipo" else "alterato"
        assert sigillo.verify(changed)["esito"] == "ALTERATO", field
    path = crea_pdf(doc, str(tmp_path / "report.pdf"))
    assert verifica_file(path, [str(tmp_path / "chiave")])["esito"] == "VALIDO"
    pages = PdfReader(io.BytesIO(pdf_bytes(doc))).pages
    assert "Dati tecnici della postazione" not in pages[0].extract_text()
    assert POST["nome_macchina"] not in pages[0].extract_text()
    assert "Dati tecnici della postazione" in "\n".join(p.extract_text() for p in pages[1:])
    bad = copy.deepcopy(doc); bad["dati_tecnici_postazione"]["ip"] = "vietato"
    assert validate(bad)


def test_ente_flag_default_e_false(tmp_path):
    cfg = tmp_path / "ente.json"
    assert ente.carica(str(cfg))["dati_tecnici_postazione"] is True
    cfg.write_text(json.dumps({"dati_tecnici_postazione": False}), encoding="utf-8")
    assert ente.carica(str(cfg))["dati_tecnici_postazione"] is False
