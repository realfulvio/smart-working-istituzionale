"""Collaudo ALFA3 (installer): N4 codice di uscita della voce «App installate» propagato e messaggio al rifiuto,
N5 documentazione allineata al comportamento, percorsi brevi 8.3 normalizzati (GetLongPathName)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parents[1]
PAC = RADICE / "tools" / "pacchetto"
INS = (PAC / "installa.ps1").read_text(encoding="utf-8-sig")
DIS = (PAC / "disinstalla.ps1").read_text(encoding="utf-8-sig")
LEGGIMI = (PAC / "LEGGIMI_ALFA.txt").read_text(encoding="utf-8")

pwsh = pytest.mark.skipif(shutil.which("pwsh") is None, reason="pwsh non installato")


def _funzione(script: Path, nome: str) -> str:
    """Testo della funzione PowerShell (dall'AST del parser: niente esecuzione del corpo dello script)."""
    cmd = (f"$a=[System.Management.Automation.Language.Parser]::ParseFile('{script}', [ref]$null, [ref]$null); "
           f"$f=$a.FindAll({{ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and "
           f"$n.Name -eq '{nome}' }}, $true) | Select-Object -First 1; $f.Extent.Text")
    r = subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], capture_output=True, text=True, check=True)
    assert r.stdout.strip().startswith("function"), r.stdout + r.stderr
    return r.stdout


@pwsh
@pytest.mark.parametrize("codice", [0, 20, 30])
def test_n4_comando_disinstalla_propaga_codice_e_percorsi_con_spazi(tmp_path, codice):
    dest = tmp_path / "Programmi prova" / "Rendiconto d'Ufficio"
    dati = tmp_path / "dati con spazi"
    dest.mkdir(parents=True)
    argomenti = tmp_path / "argomenti.txt"
    (dest / "disinstalla.ps1").write_text(
        "param([string]$Destinazione, [string]$CartellaDati, [switch]$MostraEsito)\n"
        f"\"$Destinazione|$CartellaDati|$MostraEsito\" | Set-Content -LiteralPath '{argomenti}'\n"
        f"exit {codice}\n", encoding="utf-8")
    funz = _funzione(PAC / "installa.ps1", "Get-ComandoDisinstalla")
    stampa = subprocess.run(["pwsh", "-NoProfile", "-Command",
                             funz + f"\nGet-ComandoDisinstalla -Dest '{str(dest).replace(chr(39), chr(39) * 2)}' "
                                    f"-Dati '{dati}'"], capture_output=True, text=True, check=True).stdout.strip()
    assert stampa.startswith('powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& {')
    assert "exit $c" in stampa and "-MostraEsito" in stampa
    # stessa riga, con pwsh al posto di powershell.exe (box Linux): il codice arriva al chiamante
    corpo = re.match(r'powershell\.exe -NoProfile -ExecutionPolicy Bypass -Command "(.*)"$', stampa).group(1)
    r = subprocess.run(["pwsh", "-NoProfile", "-Command", corpo], capture_output=True, text=True,
                       env=dict(os.environ, TEMP=str(tmp_path)))
    assert r.returncode == codice, r.stdout + r.stderr
    assert argomenti.read_text(encoding="utf-8").strip() == f"{dest}|{dati}|True"
    assert not list(tmp_path.glob("rsw_uninst_*.ps1")), "copia temporanea non rimossa"


def test_n4_disinstalla_mostra_esito_solo_se_rifiuta():
    assert "[switch]$MostraEsito" in DIS
    assert "Mostra-Esito $Codice $Msg" in DIS
    corpo = DIS[DIS.index("function Mostra-Esito"):DIS.index("function Esci-Con")]
    assert "$Codice -eq 0" in corpo and "RSW_SENZA_FINESTRE" in corpo and "MessageBox" in corpo
    assert "Read-Host" in corpo                     # ripiego: console che resta aperta


def test_n4_registra_uninstall_usa_il_comando_che_propaga():
    corpo = INS[INS.index("function Registra-Uninstall"):]
    assert "Get-ComandoDisinstalla -Dest $Dest -Dati $Dati" in corpo


def test_n5_documentazione_allineata():
    assert "Lo script ferma solo i processi della cartella" not in LEGGIMI
    assert "[s/N]" in DIS and "[S/n]" not in DIS
    assert "codice 20" in LEGGIMI and "-Forza" in LEGGIMI
    assert "RIFIUTA con codice 20" in DIS


@pwsh
@pytest.mark.parametrize("script", ["installa.ps1", "disinstalla.ps1"])
def test_83_get_percorso_lungo_non_rompe_e_normalizza(tmp_path, script):
    funz = _funzione(PAC / script, "Get-PercorsoLungo")
    (tmp_path / "esiste").mkdir()
    casi = [str(tmp_path / "esiste" / "nuova" / "RendicontoSW"), str(tmp_path / "esiste" / ".." / "esiste"),
            str(tmp_path / "NOMEUT~1" / "x")]
    out = subprocess.run(["pwsh", "-NoProfile", "-Command", funz + "\n" + "\n".join(
        f"Get-PercorsoLungo '{c}'" for c in casi)], capture_output=True, text=True, check=True).stdout.split("\n")
    assert out[0].strip() == casi[0]
    assert out[1].strip() == str(tmp_path / "esiste")
    assert out[2].strip() == casi[2]                # fuori da Windows la forma breve resta com'è, senza errori


@pytest.mark.parametrize("testo,nome", [(INS, "installa"), (DIS, "disinstalla")])
def test_83_confronti_per_percorso_usano_la_forma_lunga(testo, nome):
    assert "GetLongPathName" in testo
    corpo = testo[testo.index("function Get-PercorsoLungo"):]
    corpo = corpo[corpo.index("\n}\n"):]            # dopo la definizione della funzione
    assert "[System.IO.Path]::GetFullPath(" not in corpo, f"{nome}: confronto senza forma lunga"
    assert "$dest = Get-PercorsoLungo $Destinazione" in testo
    assert "$dati = Get-PercorsoLungo $CartellaDati" in testo
    assert "Get-PercorsoLungo $exe" in testo


def test_83_moduli_e_collegamenti_normalizzati():
    assert "(Get-PercorsoLungo $_.FileName).StartsWith($radice" in DIS
    assert "(Get-PercorsoLungo $tp).StartsWith($radice" in DIS


@pwsh
def test_conferma_senza_input_rifiuta_senza_errore():
    funz = _funzione(PAC / "disinstalla.ps1", "Conferma-Si")
    cmd = ("$Forza=$false; function Scrivi-Log { param($t) }\n" + funz +
           "\n$ErrorActionPreference='Stop'; if (Conferma-Si 'Chiudo? [s/N]') { exit 5 } else { exit 20 }")
    r = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL)
    assert r.returncode == 20, r.stdout + r.stderr
