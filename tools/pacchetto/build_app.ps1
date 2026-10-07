param([string]$Edizione = "neutra")
# Costruisce RendicontoSW.exe e VerificaRendiconto.exe (PyInstaller --onedir, finestra senza console).
# Uso, nella radice del repository, con il venv di sviluppo attivo (Python 3.13 + requirements + pyinstaller):
#   powershell -ExecutionPolicy Bypass -File tools\pacchetto\build_app.ps1
# Uscita: build\dist\RendicontoSW\ (contiene anche VerificaRendiconto.exe e le librerie comuni).
#
# FIRMA DEL CODICE: TODO con il certificato di firma dell'Ente. Gli eseguibili prodotti NON sono firmati.
# Non usare certificati autofirmati, esclusioni di Defender/ASR/EDR o altri aggiramenti: la distribuzione
# ai colleghi attende la firma. Per la sola prova pilota si usa Python dal sorgente.
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8="1"
$env:PYTHONIOENCODING="utf-8"
# reportlab.graphics.barcode importa i suoi moduli (code128, qr, …) per nome: PyInstaller non li vede e senza
# --collect-submodules sia il PDF sia VerificaRendiconto.exe falliscono (collaudo ALFA del 05/10/2026).
# Pacchetti di prima parte: TUTTI raccolti esplicitamente (collaudo ALFA3 N1: un import mancante faceva fallire
# «Chiudi giornata» solo nell'eseguibile). «estensione» è ESCLUSA di proposito (non si distribuisce nell'ALFA):
# il codice la importa solo dentro try/except ImportError. Controllo: tests/test_pacchetto_import.py e, sull'exe,
# tools/pacchetto/scansiona_pyz.py.
$env:RENDICONTO_EDIZIONE = $Edizione
$configBuild = Join-Path (Get-Location) ("build/config-edizione-" + [guid]::NewGuid().ToString('N'))
python -m tools.configura_edizione $configBuild
if ($LASTEXITCODE -ne 0) { throw "Configurazione edizione fallita" }
$primaParte = @("aggregatore", "applicazione", "collector", "redattore", "resoconto", "verificatore")
$raccolta = @()
foreach ($m in $primaParte) { $raccolta += @("--collect-submodules", $m) }
$comuni = @("--noconfirm", "--clean", "--onedir", "--windowed", "--distpath", "build\dist", "--workpath", "build\work",
            "--specpath", "build", "--add-data", ($configBuild + ";config"), "--add-data", "..\schema;schema",
            "--add-data", "..\applicazione\assets;applicazione\assets", "--collect-data", "tzdata",
            "--collect-data", "resoconto",
            "--hidden-import", "win32timezone", "--collect-submodules", "reportlab.graphics.barcode", "--exclude-module", "unittest", "--exclude-module", "pydoc",
            "--exclude-module", "estensione",
            # ReportLab usa Pillow solo per il logo PNG dell'Ente: i codec AVIF e WebP (~8 MB) non servono mai
            "--exclude-module", "PIL._avif", "--exclude-module", "PIL.AvifImagePlugin",
            "--exclude-module", "PIL._webp", "--exclude-module", "PIL.WebPImagePlugin",
            "--icon", "..\applicazione\assets\rendiconto.ico") + $raccolta
python -m PyInstaller @comuni --name RendicontoSW tools\pacchetto\app_entry.py
if ($LASTEXITCODE -ne 0) { throw "Build applicazione fallita" }
python -m PyInstaller @comuni --name VerificaRendiconto tools\pacchetto\verifica_entry.py
if ($LASTEXITCODE -ne 0) { throw "Build Verificatore fallita" }
# un'unica cartella: l'eseguibile del verificatore accanto a quello dell'applicazione (stesse librerie)
Copy-Item build\dist\VerificaRendiconto\VerificaRendiconto.exe build\dist\RendicontoSW\ -Force
Get-ChildItem build\dist\RendicontoSW\*.exe | ForEach-Object {
  $s = Get-AuthenticodeSignature $_.FullName
  Write-Host ("{0}: firma {1} (TODO: firma con il certificato dell'Ente)" -f $_.Name, $s.Status)
}
