"""Revisione dell'installer (ALFA): controlli statici e simulazioni sui .ps1 del pacchetto.

Non esegue installazioni/disinstallazioni Windows reali (box Linux): verifica contratti del codice,
parser PowerShell se disponibile, e piccole simulazioni Python dei controlli SHA/versione.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[1]
PAC = RADICE / "tools" / "pacchetto"
EST = RADICE / "estensione"

DIS = (PAC / "disinstalla.ps1").read_text(encoding="utf-8-sig")
INS = (PAC / "installa.ps1").read_text(encoding="utf-8-sig")
PREP = (PAC / "prepara_cartella_rete.ps1").read_text(encoding="utf-8-sig")
PREP_ALFA = (PAC / "prepara_alfa.ps1").read_text(encoding="utf-8-sig")
REG = (EST / "registra_host.ps1").read_text(encoding="utf-8-sig")
DEREG = (EST / "deregistra_host.ps1").read_text(encoding="utf-8-sig")


def _ha_pwsh() -> bool:
    return shutil.which("pwsh") is not None


@pytest.mark.parametrize(
    "percorso",
    [
        PAC / "disinstalla.ps1",
        PAC / "installa.ps1",
        PAC / "prepara_cartella_rete.ps1",
        PAC / "prepara_alfa.ps1",
        EST / "registra_host.ps1",
        EST / "deregistra_host.ps1",
    ],
)
def test_sintassi_powershell_parser(percorso: Path):
    if not _ha_pwsh():
        pytest.skip("pwsh non installato sul box")
    cmd = (
        "$e=$null; "
        f"[void][System.Management.Automation.Language.Parser]::ParseFile('{percorso}', [ref]$null, [ref]$e); "
        "if ($e) { $e | ForEach-Object { $_.Message }; exit 1 }"
    )
    r = subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_i1_disinstalla_processi_path_rinomina_collegamenti_ultimi_exit_log():
    assert "Get-ProcessiCartella" in DIS or "ExecutablePath" in DIS
    assert "Tipo = 'app'" in DIS or "Tipo='app'" in DIS or "Tipo = 'terzi'" in DIS
    assert "terzi" in DIS
    assert "Rename-Item" in DIS and "da_rimuovere" in DIS
    assert "Acrobat" in DIS or "terzi" in DIS
    assert "exit 20" in DIS or "Esci-Con 20" in DIS
    assert "Esci-Con 30" in DIS or "exit 30" in DIS
    assert "rsw_disinstalla_" in DIS and "TEMP" in DIS
    # nel corpo principale: rinomina prima della chiamata ai collegamenti
    corpo = DIS.split("# --- inizio ---", 1)[-1]
    assert corpo.index("Rename-Item") < corpo.index("Rimuovi-CollegamentiPerBersaglio")
    assert "WorkingDirectory" not in DIS  # non crea collegamenti


def test_i2_rimuovi_dati_per_categoria_mai_pdf_documenti():
    assert "RimuoviDati" in DIS
    assert "giorni" in DIS and "finali" in DIS and "chiave" in DIS
    assert "Conferma" in DIS or "Read-Host" in DIS
    assert "Rendiconti lavoro agile" in DIS or "PDF in Documenti" in DIS
    assert "servizi.json" in DIS
    # non cancella l'intera cartella dati in un colpo (solo sottopercorsi per categoria)
    assert "Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $dati" not in DIS
    assert "-LiteralPath $dati -Recurse" not in DIS


def test_i3_installa_staging_versione_spazio_rollback():
    assert "Reinstalla" in INS and "Forza" in INS
    assert "Confronta-Versione" in INS or "VERSIONE.txt" in INS
    assert (".nuova" in INS and ".vecchia" in INS) and ("leafDest" in INS or "RendicontoSW.nuova" in INS)
    assert "Esci-Con 20" in INS and "Esci-Con 40" in INS and "Esci-Con 50" in INS
    assert "rollback" in INS.lower() or "Ripristinata" in INS or "ripristinata" in INS


def test_i4_workingdirectory_documenti():
    assert "MyDocuments" in INS
    assert re.search(r"WorkingDirectory\s*=\s*\$wd", INS)
    assert not re.search(r"WorkingDirectory\s*=\s*\$dest\b", INS)


def test_i5_sha256_no_extras_verify_copy_nota_non_autenticato():
    assert "non elencati" in INS or "NON presenti in SHA256SUMS" in INS
    assert "copia" in INS.lower() and "Get-FileHash" in INS
    assert INS.count("Get-FileHash") >= 2  # origine + copia
    assert "non è autenticato" in INS or "non autenticato" in INS
    assert "code signing" in INS.lower() or "code signing" in (PAC / "LEGGIMI.txt").read_text(encoding="utf-8-sig").lower()


def test_i6_exit_codes_e_log():
    for testo, pref in ((DIS, "disinstalla"), (INS, "installa")):
        assert f"rsw_{pref}_" in testo
        assert "Esci-Con" in testo
        assert "Codice di uscita" in testo


def test_i7_uninstall_hkcu_copia_temp():
    assert r"CurrentVersion\Uninstall\RendicontoSW" in INS
    assert "HKCU:" in INS
    assert "HKLM" not in INS or "mai HKLM" in INS or "non HKLM" in INS.lower() or "nessun HKLM" in INS.lower() or "Cosa NON fa" in INS
    assert "UninstallString" in INS
    assert "disinstalla.ps1" in INS
    assert "Copy-Item" in INS and "TEMP" in INS  # wrapper copia in TEMP
    # disinstalla rimuove la voce
    assert r"CurrentVersion\Uninstall\RendicontoSW" in DIS


def test_i8_registra_e_deregistra_cauti():
    assert "Forza" in REG
    assert "Valore esistente" in REG or "valore diverso" in REG.lower() or "Valore attuale" in REG
    assert "throw" in REG.lower() or "Usa -Forza" in REG
    assert "Test-NostroValore" in DEREG or "NON rimosso" in DEREG
    assert "RendicontoSW-host.exe" in DEREG or "path" in DEREG.lower()


def test_i9_prepara_rete_solo_llama_server():
    assert "llama-server.exe" in PREP
    assert "altriExe" in PREP or "non ammessi" in PREP
    assert "Expand-Archive" in PREP
    # non deve più espandere direttamente nella destinazione ai\\llama come unica azione
    assert "Solo llama-server" in PREP or "solo llama-server" in PREP.lower() or "B9" in PREP


def test_i10_literalpath_e_giunzioni():
    assert "LiteralPath" in INS and "LiteralPath" in DIS
    assert "ReparsePoint" in INS and "ReparsePoint" in DIS


def test_mai_unblock_defender_hklm_servizi_task():
    """Vietati come comandi (righe non commento); i commenti possono citarli per vietarli."""
    vietati = (
        "Unblock-File",
        "Add-MpPreference",
        "Set-MpPreference",
        "ExclusionPath",
        "New-Service",
        "Register-ScheduledTask",
        "schtasks",
    )
    for nome, f in (
        ("disinstalla", DIS), ("installa", INS), ("prepara_rete", PREP),
        ("prepara_alfa", PREP_ALFA), ("registra", REG), ("deregistra", DEREG),
    ):
        for riga in f.splitlines():
            code = riga.lstrip()
            if code.startswith("#"):
                continue
            for v in vietati:
                assert v not in riga, (nome, v, riga)
            assert "HKLM:" not in riga, (nome, riga)


def test_prepara_alfa_presente_e_genera_versione():
    assert (PAC / "prepara_alfa.ps1").is_file()
    assert "VERSIONE.txt" in PREP_ALFA
    assert "LEGGIMI_ALFA.txt" in PREP_ALFA
    assert "commit=" in PREP_ALFA


def test_simulazione_sha256_rifiuta_extra(tmp_path: Path):
    """Simula il controllo «ogni file copiato ⊆ SHA256SUMS»."""
    orig = tmp_path / "pkg"
    (orig / "app").mkdir(parents=True)
    (orig / "ai" / "llama").mkdir(parents=True)
    f1 = orig / "app" / "RendicontoSW.exe"
    f1.write_bytes(b"fake-exe")
    f2 = orig / "ai" / "llama" / "llama-server.exe"
    f2.write_bytes(b"fake-llama")
    extra = orig / "app" / "malware.dll"
    extra.write_bytes(b"bad")

    def rel(p: Path) -> str:
        return str(p.relative_to(orig)).replace("/", "\\")

    listed = {rel(f1), rel(f2)}
    hashes = {rel(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (f1, f2)}
    reali = []
    for sub in ("app", "ai", "licenze"):
        d = orig / sub
        if not d.exists():
            continue
        for p in d.rglob("*"):
            if p.is_file():
                reali.append(rel(p))
    extras = [r for r in reali if r not in listed]
    assert extras == [rel(extra)]
    # dopo rimozione extra, tutti ok
    extra.unlink()
    reali2 = [rel(p) for p in (orig / "app").rglob("*") if p.is_file()]
    reali2 += [rel(p) for p in (orig / "ai").rglob("*") if p.is_file()]
    assert all(r in hashes for r in reali2)


def test_simulazione_confronto_data_versione():
    def cmp_data(d_nuova: str, d_vecchia: str) -> int:
        from datetime import datetime
        t_n = datetime.strptime(d_nuova, "%Y-%m-%d %H:%M")
        t_v = datetime.strptime(d_vecchia, "%Y-%m-%d %H:%M")
        return (t_n > t_v) - (t_n < t_v)

    assert cmp_data("2026-10-05 18:00", "2026-10-05 12:00") == 1
    assert cmp_data("2026-10-04 10:00", "2026-10-05 12:00") == -1
    assert cmp_data("2026-10-05 12:00", "2026-10-05 12:00") == 0


def test_parametri_destinazione_e_cartella_dati():
    """Sandbox: -Destinazione / -CartellaDati per non toccare i dati reali."""
    assert "Destinazione" in INS and "CartellaDati" in INS
    assert "Destinazione" in DIS and "CartellaDati" in DIS
    assert "RendicontoSW_dati" in INS or "_dati" in INS
    assert "non ammessa" in INS  # rifiuto unità di rete / UNC


def test_installa_rifiuta_app_in_esecuzione_prima_di_toccare():
    """N1 ALFA2: reinstallazione sopra app in esecuzione → exit 20 prima dello staging."""
    corpo = INS.split("# --- inizio ---", 1)[-1]
    assert "Get-ProcessiPropri" in corpo
    assert "Esci-Con 20" in corpo
    assert corpo.index("Get-ProcessiPropri") < corpo.index("Copia in cartella di staging")


def test_script_utf8_con_bom():
    """N2 ALFA2: PowerShell 5.1 legge UTF-8 solo con BOM."""
    for nome in ("installa.ps1", "disinstalla.ps1"):
        raw = (PAC / nome).read_bytes()[:3]
        assert raw == bytes([0xEF, 0xBB, 0xBF]), nome


def test_disinstalla_elenca_bloccanti_restart_manager():
    """B6/ALFA2: con file in uso elenca il processo (anche handle aperti, non solo moduli)."""
    assert "Get-ProcessiBloccanti" in DIS
    assert "RmStartSession" in DIS or "rstrtmgr" in DIS.lower()

