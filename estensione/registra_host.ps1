# Registra l'host Native Messaging dell'estensione per l'UTENTE corrente (HKCU, senza diritti di amministratore).
# NON installa l'estensione e non tocca le policy del browser: l'installazione dell'estensione (forcelist via GPO)
# resta una scelta del CED, da fare solo dopo i presupposti dell'art. 4 (vedi README.md e PRIVACY.md).
# Uso: powershell -ExecutionPolicy Bypass -File registra_host.ps1 -Cartella <cartella con host-*.json e l'exe> [-Forza]
# Senza -Forza: se la chiave esiste con un valore diverso, legge/logga il valore esistente e rifiuta.
param(
  [Parameter(Mandatory = $true)][string]$Cartella,
  [switch]$Forza
)
$ErrorActionPreference = 'Stop'
$nome = 'org.smartworking.istituzionale'
$Cartella = [System.IO.Path]::GetFullPath($Cartella)
$exe = Join-Path $Cartella 'RendicontoSW-host.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw "Manca $exe" }
$log = Join-Path $env:TEMP ("rsw_registra_host_{0:yyyyMMdd_HHmmss}.log" -f (Get-Date))
function Scrivi-Log([string]$Msg) {
  Add-Content -LiteralPath $log -Value $Msg -Encoding UTF8
  Write-Host $Msg
}
Scrivi-Log "Registrazione host Native Messaging (log: $log)"
foreach ($b in @(@{ chiave = 'Software\Google\Chrome\NativeMessagingHosts'; json = 'host-chromium.json' },
                 @{ chiave = 'Software\Microsoft\Edge\NativeMessagingHosts'; json = 'host-chromium.json' },
                 @{ chiave = 'Software\Mozilla\NativeMessagingHosts'; json = 'host-firefox.json' })) {
  $src = Join-Path $Cartella $b.json
  if (-not (Test-Path -LiteralPath $src)) { throw "Manca $src" }
  $m = Get-Content -LiteralPath $src -Raw | ConvertFrom-Json
  $m.path = $exe
  $dst = Join-Path $Cartella ("registrato-" + $b.json)
  ($m | ConvertTo-Json -Depth 5) | Set-Content -LiteralPath $dst -Encoding UTF8
  $k = "HKCU:\$($b.chiave)\$nome"
  if (Test-Path -LiteralPath $k) {
    $esistente = $null
    try { $esistente = (Get-Item -LiteralPath $k).GetValue('') } catch {}
    Scrivi-Log ("Valore esistente per {0}: {1}" -f $k, $esistente)
    if ($esistente -and -not $esistente.Equals($dst, [System.StringComparison]::OrdinalIgnoreCase)) {
      if (-not $Forza) {
        throw ("Chiave già presente con valore diverso. Valore attuale: {0}. Nuovo: {1}. Usa -Forza per sovrascrivere (dopo aver annotato il valore)." -f $esistente, $dst)
      }
      Scrivi-Log "Sovrascrittura forzata (-Forza)."
    }
  }
  New-Item -Path $k -Force | Out-Null
  Set-Item -Path $k -Value $dst
  Scrivi-Log "Registrato: $k -> $dst"
}
