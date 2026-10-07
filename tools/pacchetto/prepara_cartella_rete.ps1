# Prepara, IN LOCALE, la cartella da copiare a mano in una cartella condivisa dell'Ente (la copia la fa l'Ente).
# Questo script NON scrive mai su unità di rete (e rifiuta qualunque destinazione di rete).
# Uso:
#   powershell -ExecutionPolicy Bypass -File tools\pacchetto\prepara_cartella_rete.ps1 `
#       -App build\dist\RendicontoSW -LlamaZip llama-b11386-bin-win-cpu-x64.zip -Modelli C:\percorso\modelli
# Contenuto prodotto (in %USERPROFILE%\Downloads\RendicontoSW_rete_AAAAMMGG):
#   app\        RendicontoSW.exe, VerificaRendiconto.exe e librerie (da build_app.ps1; NON firmati: TODO)
#   ai\llama\   SOLO llama-server.exe e DLL (coerente con B9 / prepara_alfa.ps1)
#   ai\modelli\ Qwen3-1.7B-Q4_K_M.gguf (AI-LIGHT) e, se presente, Qwen3-4B-Q4_K_M.gguf (AI-STANDARD)
#   licenze\    EUPL, THIRD_PARTY_NOTICES, licenze di llama.cpp, LLVM OpenMP, Qwen3, font
#   installa.ps1, disinstalla.ps1, LEGGIMI.txt, SHA256SUMS.txt, VERSIONE.txt
# Nota: SHA256SUMS.txt elenca i file ma non è autenticato finché non c'è code signing (TODO CED).
param(
  [Parameter(Mandatory = $true)][string]$App,
  [Parameter(Mandatory = $true)][string]$LlamaZip,
  [Parameter(Mandatory = $true)][string]$Modelli,
  [string]$Destinazione = (Join-Path $env:USERPROFILE ("Downloads\RendicontoSW_rete_" + (Get-Date -Format yyyyMMdd))),
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
if (Test-PercorsoRete $pieno) { throw "Destinazione non ammessa ($pieno): si prepara in locale, la copia sulla cartella condivisa si fa a mano." }
$radice = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
New-Item -ItemType Directory -Force -Path $pieno, "$pieno\app", "$pieno\ai\llama", "$pieno\ai\modelli", "$pieno\licenze" | Out-Null
Copy-Item -Recurse -Force (Join-Path $App '*') "$pieno\app"

# Solo llama-server.exe + DLL (come prepara_alfa / B9)
$llamaTmp = Join-Path $env:TEMP ("rsw_llama_" + [guid]::NewGuid().ToString('N'))
Expand-Archive -Force $LlamaZip $llamaTmp
$srcLlama = $llamaTmp
$sub = Get-ChildItem -LiteralPath $llamaTmp -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
if ($sub -and -not (Test-Path -LiteralPath (Join-Path $llamaTmp "llama-server.exe"))) { $srcLlama = $sub.FullName }
$destLlama = Join-Path $pieno "ai\llama"
$server = Join-Path $srcLlama "llama-server.exe"
if (-not (Test-Path -LiteralPath $server)) { throw "llama-server.exe non trovato in $srcLlama" }
Copy-Item -LiteralPath $server -Destination $destLlama -Force
Get-ChildItem -LiteralPath $srcLlama -File | Where-Object { $_.Extension -ieq '.dll' } | ForEach-Object {
  Copy-Item -LiteralPath $_.FullName -Destination $destLlama -Force
}
Remove-Item -LiteralPath $llamaTmp -Recurse -Force
$altriExe = @(Get-ChildItem -LiteralPath $destLlama -Filter *.exe | Where-Object { $_.Name -ne 'llama-server.exe' })
if ($altriExe.Count) { throw ("Nel pacchetto ci sono exe llama non ammessi: {0}" -f ($altriExe.Name -join ', ')) }

foreach ($m in @("Qwen3-1.7B-Q4_K_M.gguf", "Qwen3-4B-Q4_K_M.gguf")) {
  $f = Join-Path $Modelli $m
  if (Test-Path -LiteralPath $f) { Copy-Item -LiteralPath $f -Destination "$pieno\ai\modelli" -Force } else { Write-Host "modello assente (facoltativo per il 4B): $m" }
}
Copy-Item -Force (Join-Path $radice 'LICENSE') "$pieno\licenze\EUPL-1.2.txt"
Copy-Item -Force (Join-Path $radice 'THIRD_PARTY_NOTICES.md') "$pieno\licenze\"
if (Test-Path -LiteralPath (Join-Path $radice 'licenze')) {
  Copy-Item -Force (Join-Path $radice 'licenze\*') "$pieno\licenze\"
}
Copy-Item -Force (Join-Path $radice 'applicazione\assets\fonts\*.txt') "$pieno\licenze\" -ErrorAction SilentlyContinue
Copy-Item -Force (Join-Path $PSScriptRoot 'installa.ps1'), (Join-Path $PSScriptRoot 'disinstalla.ps1'), (Join-Path $PSScriptRoot 'LEGGIMI.txt') $pieno

if (-not $Commit) {
  try { $Commit = (git -C $radice rev-parse --short HEAD) } catch { $Commit = "sconosciuto" }
}
@"
Rendiconto SW
commit=$Commit
data=$(Get-Date -Format 'yyyy-MM-dd HH:mm')
"@ | Set-Content -Encoding UTF8 (Join-Path $pieno 'VERSIONE.txt')

# impronte SHA-256 di tutti i file (verificate da installa.ps1 sulla copia; elenco non autenticato senza code signing)
$righe = Get-ChildItem -LiteralPath $pieno -Recurse -File | Where-Object { $_.Name -ne 'SHA256SUMS.txt' } | Sort-Object FullName | ForEach-Object {
  $rel = $_.FullName.Substring($pieno.Length + 1)
  "{0}  {1}" -f (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower(), $rel
}
$righe | Set-Content -Encoding UTF8 "$pieno\SHA256SUMS.txt"
Get-ChildItem -LiteralPath "$pieno\app" -Filter *.exe -ErrorAction SilentlyContinue | ForEach-Object {
  Write-Host ("{0}: firma {1}" -f $_.Name, (Get-AuthenticodeSignature -LiteralPath $_.FullName).Status)
}
$ls = Join-Path $pieno "ai\llama\llama-server.exe"
if (Test-Path -LiteralPath $ls) {
  Write-Host ("llama-server.exe: firma {0}" -f (Get-AuthenticodeSignature -LiteralPath $ls).Status)
}
Write-Host "Pronta: $pieno  ($($righe.Count) file). Copiarla a mano nella cartella condivisa dell'Ente."
