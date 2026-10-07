# Prepara il pacchetto ALFA in locale (MAI su unità di rete).
# Uso (dopo build_app.ps1), nella radice del repository:
#   powershell -ExecutionPolicy Bypass -File tools\pacchetto\prepara_alfa.ps1 `
#     -App build\dist\RendicontoSW -LlamaZip <llama-b11386-win.zip> -Modello17 <Qwen3-1.7B-Q4_K_M.gguf> `
#     [-Destinazione "$env:USERPROFILE\Downloads\ALFA"]
param(
  [Parameter(Mandatory = $true)][string]$App,
  [Parameter(Mandatory = $true)][string]$LlamaZip,
  [Parameter(Mandatory = $true)][string]$Modello17,
  [string]$Destinazione = (Join-Path $env:USERPROFILE "Downloads\ALFA"),
  [string]$Commit = ""
)
$ErrorActionPreference = "Stop"
$pieno = [System.IO.Path]::GetFullPath($Destinazione)
# Percorso di rete: UNC o unità mappata (DriveType Network). Il programma non scrive mai su risorse di rete.
function Test-PercorsoRete([string]$p) {
  if ($p -match '^\\\\') { return $true }
  if ($p -match '^([A-Za-z]):') { try { return ([System.IO.DriveInfo]::new($Matches[1] + ':\')).DriveType -eq [System.IO.DriveType]::Network } catch { return $false } }
  return $false
}
if (Test-PercorsoRete $pieno) {
  throw "Destinazione non ammessa ($pieno): niente scrittura su unità di rete."
}
if (-not (Test-Path $App)) { throw "App non trovata: $App" }
if (-not (Test-Path $LlamaZip)) { throw "Zip llama non trovato: $LlamaZip" }
if (-not (Test-Path $Modello17)) { throw "Modello 1.7B non trovato: $Modello17" }

$radice = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (Test-Path $pieno) {
  Get-ChildItem $pieno -Force | Remove-Item -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $pieno, "$pieno\app", "$pieno\ai\llama", "$pieno\ai\modelli", "$pieno\licenze" | Out-Null

Copy-Item -Recurse -Force (Join-Path $App '*') "$pieno\app"
# Config del pacchetto: modalita collector (predefinita dal 06/10/2026), AI-Light, estensione spenta
# PyInstaller --onedir mette config in app\_internal\config\ (copia anche in app\config\ per leggibilità)
$cfgCandidates = @(
  (Join-Path $pieno "app\_internal\config\app.json"),
  (Join-Path $pieno "app\config\app.json")
)
$cfgPath = $cfgCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($cfgPath) {
  $cfg = Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
  $cfg.modalita = "collector"
  $cfg | Add-Member -NotePropertyName estensione_browser -NotePropertyValue $false -Force
  $cfg.profilo_ai = "AI-LIGHT"
  ($cfg | ConvertTo-Json -Depth 6) | Set-Content -Encoding UTF8 $cfgPath
  $legibile = Join-Path $pieno "app\config"
  New-Item -ItemType Directory -Force -Path $legibile | Out-Null
  Copy-Item -Force $cfgPath (Join-Path $legibile "app.json")
}

$llamaTmp = Join-Path $env:TEMP ("rsw_llama_" + [guid]::NewGuid().ToString('N'))
Expand-Archive -Force $LlamaZip $llamaTmp
# zip ufficiale: file in radice oppure in una sottocartella
$srcLlama = $llamaTmp
$sub = Get-ChildItem $llamaTmp -Directory | Select-Object -First 1
if ($sub -and -not (Test-Path (Join-Path $llamaTmp "llama-server.exe"))) { $srcLlama = $sub.FullName }
# Solo llama-server.exe e le DLL necessarie (collaudo ALFA B9: evitiamo i 21 exe di tool llama.cpp)
$destLlama = Join-Path $pieno "ai\llama"
New-Item -ItemType Directory -Force -Path $destLlama | Out-Null
$server = Join-Path $srcLlama "llama-server.exe"
if (-not (Test-Path $server)) { throw "llama-server.exe non trovato in $srcLlama" }
Copy-Item -Force $server $destLlama
Get-ChildItem -Path $srcLlama -File | Where-Object { $_.Extension -ieq '.dll' } | ForEach-Object {
  Copy-Item -Force $_.FullName $destLlama
}
Remove-Item -Recurse -Force $llamaTmp
$altriExe = @(Get-ChildItem $destLlama -Filter *.exe | Where-Object { $_.Name -ne 'llama-server.exe' })
if ($altriExe.Count) { throw ("Nel pacchetto ci sono exe llama non ammessi: {0}" -f ($altriExe.Name -join ', ')) }

Copy-Item -Force $Modello17 (Join-Path $pieno "ai\modelli\Qwen3-1.7B-Q4_K_M.gguf")

Copy-Item -Force (Join-Path $radice 'LICENSE') "$pieno\licenze\EUPL-1.2.txt"
Copy-Item -Force (Join-Path $radice 'THIRD_PARTY_NOTICES.md') "$pieno\licenze\"
if (Test-Path (Join-Path $radice 'licenze')) {
  Copy-Item -Force (Join-Path $radice 'licenze\*') "$pieno\licenze\"
}
Copy-Item -Force (Join-Path $radice 'applicazione\assets\fonts\*.txt') "$pieno\licenze\" -ErrorAction SilentlyContinue
Copy-Item -Force (Join-Path $PSScriptRoot 'installa.ps1'), (Join-Path $PSScriptRoot 'disinstalla.ps1') $pieno
Copy-Item -Force (Join-Path $PSScriptRoot 'LEGGIMI_ALFA.txt') (Join-Path $pieno 'LEGGIMI_ALFA.txt')
# LEGGIMI.txt minimale che rimanda all'ALFA
@"
Pacchetto ALFA di prova — leggere LEGGIMI_ALFA.txt
Installazione: powershell -ExecutionPolicy Bypass -File .\installa.ps1
"@ | Set-Content -Encoding UTF8 (Join-Path $pieno 'LEGGIMI.txt')

if (-not $Commit) {
  try { $Commit = (git -C $radice rev-parse --short HEAD) } catch { $Commit = "sconosciuto" }
}
@"
Rendiconto SW ALFA
commit=$Commit
data=$(Get-Date -Format 'yyyy-MM-dd HH:mm')
pyinstaller=vedere build
modello=Qwen3-1.7B-Q4_K_M.gguf
llama=b11386
profilo_ai=AI-LIGHT
modalita=collector
estensione_browser=false
"@ | Set-Content -Encoding UTF8 (Join-Path $pieno 'VERSIONE.txt')

$righe = Get-ChildItem -Recurse -File $pieno | Where-Object { $_.Name -ne 'SHA256SUMS.txt' } | Sort-Object FullName | ForEach-Object {
  $rel = $_.FullName.Substring($pieno.Length + 1)
  "{0}  {1}" -f (Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLower(), $rel
}
$righe | Set-Content -Encoding UTF8 "$pieno\SHA256SUMS.txt"
Get-ChildItem "$pieno\app\*.exe", "$pieno\ai\llama\llama-server.exe" -ErrorAction SilentlyContinue | ForEach-Object {
  Write-Host ("{0}: firma {1}" -f $_.Name, (Get-AuthenticodeSignature $_.FullName).Status)
}
Write-Host "ALFA pronta: $pieno  ($($righe.Count) file). NON scrivere su unità di rete."
