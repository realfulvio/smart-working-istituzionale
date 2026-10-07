"""Contratti consolidati: minimizzazione, determinismo, provenienza, firma e retention."""
import copy
import datetime as dt
import json
from pathlib import Path
from unittest import mock

import pytest

from aggregatore import aggrega, modelli, sigillo
from aggregatore.cli import validate
from aggregatore.configurazione import valida_fascia
from collector.percorsi import Percorsi
from collector import retention
from redattore import fatti, sintesi, motore, controllo
from tools.simula_edizione import genera, mappa_sintetica


@pytest.mark.parametrize("scenario", ["ordinaria", "senza_segnali", "halley_poc"])
def test_giornate_sintetiche_deterministiche_e_valide(scenario):
    records, doc = genera(scenario)
    assert validate(doc) == []
    meta, events = records[0], records[1:]
    assert aggrega.aggregate(modelli.parse_records([meta, *reversed(events)]), mappa_sintetica()) == doc
    assert doc["schema"].endswith("/5")


def test_hardware_non_cambia_documento_ne_fatti():
    records, doc = genera()
    for ram in (8, 32):
        r = copy.deepcopy(records)
        r[0]["postazione"] = {"ram_gb": ram, "host": "PC-ESEMPIO", "tipo": "vdi"}
        r[0]["dipendente"]["account"] = "ENTE\\esempio"
        d = aggrega.aggregate(modelli.parse_records(r), mappa_sintetica())
        assert d == doc and fatti.estrai(d) == fatti.estrai(doc)


def test_confini_sovrapposizioni_gap_sessioni_e_revisioni():
    _, d = genera()
    by = {f["ora"]: f for f in d["fasce"]}
    assert by["08:00"]["app"] == ["outlook", "word"]
    assert by["08:15"]["app"] == ["outlook"]
    assert by["09:00"]["stato"] == "sessione_bloccata"
    assert by["09:30"]["stato"] == "attivita_rilevata"
    assert by["10:00"]["stato"] == "nessuna_attivita_informatica_rilevata"
    assert by["11:00"]["stato"] == "sessione_disconnessa"
    assert by["11:30"]["stato"] == "nessuna_attivita_informatica_rilevata"
    assert d["totali"]["con_manuali"] == {"numero_attivita_dichiarate": 2}
    forbidden = {"account", "host", "hostname", "ram_gb", "sid", "minuti_complessivi", "minuti_attivita_rilevata", "operazioni_rete"}
    def walk(obj):
        if isinstance(obj, dict):
            assert not set(obj) & forbidden
            for v in obj.values(): walk(v)
        elif isinstance(obj, list):
            for v in obj: walk(v)
    walk(d)
    for key in ("per_applicazione", "per_categoria", "per_sito"):
        assert all("minuti" not in r for r in d["totali"]["rilevati"][key])


def test_fallback_e_frasi_con_provenienza_distinta():
    _, d = genera()
    f = fatti.estrai(d)
    assert any(x["origine"] == "osservazione" for x in f)
    s = sintesi.genera(d, None)
    assert s["motore"]["tipo"] == "testo_standard"
    by = {x["id"]: x for x in f}
    for frase in s["frasi"]:
        assert len({by[i]["origine"] for i in frase["fatti"]}) == 1
    # Consistenza anche quando il modello tenta una fusione opaca.
    a = next(x for x in f if x["tipo"] == "applicazioni")
    b = next(x for x in f if x["tipo"] == "manuale")
    out = {"frasi": [{"testo": "Risultano applicazioni rilevate e attività dichiarate dal dipendente.", "fatti": [a["id"], b["id"]]}]}
    assert any("provenienze" in x for x in controllo.controlla(out["frasi"], f)["problemi"])


def test_sigilli_nuovi_registrati_manomessi_e_senza_identificativi(tmp_path):
    _, d = genera()
    key = sigillo.load_or_create_key(str(tmp_path / "chiave"), {"account": "ENTE\\esempio", "pc": "PC-ESEMPIO"})
    tech = sigillo.seal_technical(d, key)
    final = sigillo.seal_final(tech, key)
    assert validate(final) == []
    assert sigillo.verify(final)["esito"] == "INTEGRO"
    assert sigillo.verify(final, [str(tmp_path / "chiave")])["esito"] == "VALIDO"
    for seal in final["integrita"].values():
        assert "account" not in seal and "pc" not in seal
    changed = copy.deepcopy(final)
    changed["fasce"][33]["app"] = ["inventato"]
    assert sigillo.verify(changed)["esito"] == "ALTERATO"
    changed = copy.deepcopy(final)
    changed["integrita"]["sigillo_finale"]["pc"] = "inventato"
    assert sigillo.verify(changed)["esito"] == "ALTERATO"


@pytest.mark.parametrize("value", [5, 10, True, "15", 17, 0])
def test_fasce_non_piu_fini_del_requisito(value):
    with pytest.raises(ValueError): valida_fascia(value)


@pytest.mark.parametrize("minutes,count", [(15, 96), (20, 72), (30, 48), (60, 24)])
def test_fasce_configurate_e_verifica_indipendente_da_config_attuale(monkeypatch, tmp_path, minutes, count):
    monkeypatch.setattr(aggrega, "FASCIA_MIN", minutes)
    monkeypatch.setattr(aggrega, "FASCIA", dt.timedelta(minutes=minutes))
    _, d = genera()
    assert len(d["fasce"]) == count and validate(d) == []
    key = sigillo.load_or_create_key(str(tmp_path / "chiave"))
    final = sigillo.seal_final(sigillo.seal_technical(d, key), key)
    monkeypatch.setattr(aggrega, "FASCIA_MIN", 15)
    assert sigillo.verify(final)["esito"] == "INTEGRO"


@pytest.mark.parametrize("url", ["https://127.0.0.1:9", "http://example.test:9", "http://localhost:9", "http://127.0.0.1@example.test", "http://[::1]:9"])
def test_motore_non_accetta_endpoint_esterni(url):
    with mock.patch("urllib.request.build_opener") as opener:
        with pytest.raises(motore.ErroreMotore): motore.Ollama(url=url)
        opener.assert_not_called()


def test_retention_non_tocca_storici_ne_documenti_non_confermati(tmp_path):
    p = Percorsi(str(tmp_path / "dati"))
    raw = Path(p.raw_giorno("2026-10-05"))
    raw.write_text("storico", encoding="utf-8")
    retention.marca_nuova(p, "2026-10-05")
    assert not (Path(p.base) / "retention" / "2026-10-05.json").exists()
    policy = {"retention_raw_giorni": 1, "retention_da_data": "2026-10-01"}
    assert retention.applica(p, dt.date(2026, 10, 7), policy, esegui=True)["eliminati"] == []
    assert raw.read_text(encoding="utf-8") == "storico"
    retention.marca_nuova(p, "2026-10-06")
    Path(p.raw_giorno("2026-10-06")).write_text("nuovo", encoding="utf-8")
    assert retention.applica(p, dt.date(2026, 10, 7), policy, esegui=True)["eliminati"] == []


def test_retention_scadenza_conferma_anteprima_backup_e_default(tmp_path):
    p = Percorsi(str(tmp_path / "dati"))
    retention.marca_nuova(p, "2026-10-05")
    raw = Path(p.raw_giorno("2026-10-05"))
    raw.write_text("sintetico", encoding="utf-8")
    backup = Path(str(raw) + ".prima_della_chiusura")
    backup.write_text("sintetico", encoding="utf-8")
    _, d = genera()
    key = sigillo.load_or_create_key(str(tmp_path / "chiave"))
    final = sigillo.seal_final(sigillo.seal_technical(d, key), key)
    folder = Path(p.base) / "finali"
    folder.mkdir()
    fp = folder / "2026-10-05.json"
    fp.write_text(json.dumps(final), encoding="utf-8")
    policy = {"retention_raw_giorni": 2, "retention_da_data": "2026-10-01"}
    assert retention.applica(p, dt.date(2026, 10, 6), policy)["eleggibili"] == []
    assert retention.applica(p, dt.date(2026, 10, 7), {})["stato"] == "policy_da_validare"
    assert retention.applica(p, dt.date(2026, 10, 7), policy)["eleggibili"] == ["2026-10-05"]
    assert raw.exists() and backup.exists()
    assert retention.applica(p, dt.date(2026, 10, 7), policy, esegui=True)["eliminati"] == ["2026-10-05"]
    assert not raw.exists() and not backup.exists() and fp.exists()
