"""M7 – impostazioni del CED e script del pacchetto (controlli statici: niente esclusioni antivirus, niente scritture su unità di rete)."""
import glob
import json
import os
import re

from applicazione.servizio import carica_impostazioni

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACCHETTO = os.path.join(RADICE, "tools", "pacchetto")


def test_impostazioni_ced_e_utente(tmp_path):
    ced = tmp_path / "app.json"
    ced.write_text(json.dumps({"modalita": "collector", "thread_ai": 6, "sconosciuta": 1}), encoding="utf-8")
    base = tmp_path / "base"; base.mkdir()
    imp = carica_impostazioni(str(base), str(ced))
    assert imp["modalita"] == "collector" and imp["thread_ai"] == 6 and "sconosciuta" not in imp
    (base / "impostazioni.json").write_text(json.dumps({"modalita": "boh"}), encoding="utf-8")
    assert carica_impostazioni(str(base), str(ced))["modalita"] == "collector"      # valore non valido → predefinito
    assert carica_impostazioni(str(base), str(tmp_path / "manca.json"))["cache_ai"].endswith("cache_ai")


def test_config_app_del_repository_valida():
    j = json.load(open(os.path.join(RADICE, "config", "app.json"), encoding="utf-8"))
    assert j["modalita"] == "collector"                     # predefinita dal 06/10/2026
    assert j["cache_ai"].endswith("RendicontoSW\\cache_ai")


def test_collector_predefinito_e_consuntivo_esplicito_rispettato(tmp_path):
    """06/10/2026: senza impostazioni (o con valore non valido) la modalità è «collector»; un «consuntivo» scritto
    esplicitamente dal CED (config del pacchetto o <base>/impostazioni.json) resta rispettato."""
    from applicazione.servizio import MODALITA_PREDEFINITA, impostazioni_predefinite
    base = tmp_path / "base"; base.mkdir()
    manca = str(tmp_path / "manca.json")
    assert MODALITA_PREDEFINITA == "collector" and impostazioni_predefinite(str(base))["modalita"] == "collector"
    assert carica_impostazioni(str(base), manca)["modalita"] == "collector"
    ced = tmp_path / "app.json"
    ced.write_text(json.dumps({"thread_ai": 2}), encoding="utf-8")            # chiave assente → predefinito
    assert carica_impostazioni(str(base), str(ced))["modalita"] == "collector"
    ced.write_text(json.dumps({"modalita": "consuntivo"}), encoding="utf-8")  # scelta esplicita del CED
    assert carica_impostazioni(str(base), str(ced))["modalita"] == "consuntivo"
    (base / "impostazioni.json").write_text(json.dumps({"modalita": "consuntivo"}), encoding="utf-8")
    assert carica_impostazioni(str(base), manca)["modalita"] == "consuntivo"
    (base / "impostazioni.json").write_text(json.dumps({"modalita": None}), encoding="utf-8")
    assert carica_impostazioni(str(base), manca)["modalita"] == "collector"


def test_impostazioni_con_bom_lette(tmp_path):
    """Il config del pacchetto è scritto da prepara_alfa.ps1 con Set-Content -Encoding UTF8 (PS 5.1 → BOM): prima
    veniva ignorato in silenzio da json.load."""
    base = tmp_path / "base"; base.mkdir()
    ced = tmp_path / "app.json"
    ced.write_bytes(b"\xef\xbb\xbf" + json.dumps({"modalita": "consuntivo", "profilo_ai": "AI-LIGHT"}).encode())
    imp = carica_impostazioni(str(base), str(ced))
    assert imp["modalita"] == "consuntivo" and imp["profilo_ai"] == "AI-LIGHT"


def test_prepara_pacchetto_imposta_collector():
    s = open(os.path.join(PACCHETTO, "prepara_alfa.ps1"), encoding="utf-8-sig").read()
    assert '$cfg.modalita = "collector"' in s and '"consuntivo"' not in s and "modalita=collector" in s


def test_script_senza_esclusioni_antivirus_ne_firme_finte():
    for f in (glob.glob(os.path.join(PACCHETTO, "*.ps1")) + [os.path.join(RADICE, "tools", "build_collector.ps1")]
              + glob.glob(os.path.join(RADICE, "estensione", "*.ps1"))):
        s = open(f, encoding="utf-8").read()
        for vietato in ("Add-MpPreference", "Set-MpPreference", "ExclusionPath", "ExclusionProcess",
                        "New-SelfSignedCertificate", "Set-AuthenticodeSignature", "DisableRealtimeMonitoring",
                        "CurrentVersion\\Run"):
            assert vietato not in s, (f, vietato)


def test_nessuno_script_scrive_su_unita_di_rete():
    """Gli script che scrivono in una destinazione rifiutano percorsi UNC e unità di rete (Test-PercorsoRete)."""
    for nome in ("installa.ps1", "disinstalla.ps1", "prepara_alfa.ps1", "prepara_cartella_rete.ps1"):
        s = open(os.path.join(PACCHETTO, nome), encoding="utf-8-sig").read()
        assert "function Test-PercorsoRete" in s and "DriveType" in s and "Test-PercorsoRete $" in s, nome
