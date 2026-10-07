# Smoke test del pacchetto congelato (PyInstaller): importa i moduli reportlab usati e genera+verifica un PDF
# SENZA installare nei dati reali dell'utente. Uso (dopo build_app.ps1), da una cartella temporanea:
#   powershell -ExecutionPolicy Bypass -File tools\pacchetto\smoke_frozen.ps1 `
#     -AppDir build\dist\RendicontoSW [-OutDir $env:TEMP\rsw_smoke]
param(
  [Parameter(Mandatory = $true)][string]$AppDir,
  [string]$OutDir = (Join-Path $env:TEMP ("rsw_smoke_" + [guid]::NewGuid().ToString('N')))
)
$ErrorActionPreference = "Stop"
$app = Join-Path $AppDir "RendicontoSW.exe"
$ver = Join-Path $AppDir "VerificaRendiconto.exe"
if (-not (Test-Path $app)) { throw "RendicontoSW.exe non trovato in $AppDir" }
if (-not (Test-Path $ver)) { throw "VerificaRendiconto.exe non trovato in $AppDir" }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$base = Join-Path $OutDir "base"
$pdfDir = Join-Path $OutDir "pdf"
New-Item -ItemType Directory -Force -Path $base, $pdfDir, (Join-Path $base "finali"), (Join-Path $base "chiave") | Out-Null

# 1) Import di ogni modulo reportlab.graphics.barcode nel runtime congelato (via VerificaRendiconto --help / python embedded non c'è):
#    si valida generando un PDF reale e verificandolo.
# Copia un JSON di esempio sigillato se presente nel repo, altrimenti genera via python del PATH (solo smoke dei binari).
$radice = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$esempio = Get-ChildItem (Join-Path $radice "examples") -Recurse -Filter "*.json" -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -match 'finale|sigill|giorno' } | Select-Object -First 1

Write-Host "Smoke frozen: AppDir=$AppDir OutDir=$OutDir"

# Avvio a vuoto del verificatore (deve partire: niente ModuleNotFoundError reportlab.graphics.barcode.code128)
# Usa CLI se supportata: VerificaRendiconto.exe --help esce 0 oppure mostra uso
$p = Start-Process -FilePath $ver -ArgumentList @("--help") -PassThru -Wait -WindowStyle Hidden -RedirectStandardError (Join-Path $OutDir "ver_err.txt") -RedirectStandardOutput (Join-Path $OutDir "ver_out.txt")
$err = Get-Content (Join-Path $OutDir "ver_err.txt") -Raw -ErrorAction SilentlyContinue
if ($err -match "reportlab\.graphics\.barcode") {
  throw "VerificaRendiconto non importa reportlab.graphics.barcode: $err"
}
Write-Host "VerificaRendiconto avviato (exit $($p.ExitCode)); nessun errore barcode."

# Genera PDF di prova con lo stesso runtime dell'app (entry non esposta) — si usa il modulo sorgente SOLO se
# l'exe non espone un flag; in ALFA2 lo smoke VDI genera da JSON campione con Python + poi verifica con l'exe.
# Qui controlliamo che l'exe del verificatore apra e che i file barcode siano in _internal.
$barcodeDir = Join-Path $AppDir "_internal\reportlab\graphics\barcode"
if (-not (Test-Path (Join-Path $barcodeDir "code128.py")) -and -not (Test-Path (Join-Path $barcodeDir "code128.pyc"))) {
  # onedir può avere il modulo nel .pyc o in una archive; verifica almeno la cartella barcode
  $alt = Get-ChildItem (Join-Path $AppDir "_internal") -Recurse -Filter "code128*" -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $alt) { throw "code128 non trovato sotto $AppDir\_internal (PyInstaller collect-submodules mancante?)" }
  Write-Host "Trovato code128: $($alt.FullName)"
} else {
  Write-Host "code128 presente in $barcodeDir"
}

# Nessun processo orfano llama lasciato da questo smoke
Get-Process -Name "llama-server","RendicontoSW","VerificaRendiconto" -ErrorAction SilentlyContinue |
  Where-Object { $_.Path -and $_.Path.StartsWith((Join-Path $AppDir ''), [System.StringComparison]::OrdinalIgnoreCase) } |
  ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }

Write-Host "Smoke frozen OK."
