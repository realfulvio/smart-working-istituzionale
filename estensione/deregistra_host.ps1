# Rimuove la registrazione dell'host Native Messaging per l'utente corrente (HKCU).
# Cancella SOLO le chiavi il cui valore (o il path nel manifest) punta al nostro host/manifest.
# Uso: powershell -ExecutionPolicy Bypass -File deregistra_host.ps1 [-Cartella <installazione>] [-Forza]
param(
  [string]$Cartella = '',
  [switch]$Forza
)
$ErrorActionPreference = 'Stop'
$nome = 'org.smartworking.istituzionale'
$radici = @()
if ($Cartella) {
  $radici += ([System.IO.Path]::GetFullPath($Cartella).TrimEnd('\') + '\')
}
# Percorsi tipici dell'app
if ($env:LOCALAPPDATA) {
  $radici += ([System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\RendicontoSW')).TrimEnd('\') + '\')
}
function Test-NostroValore([string]$Val) {
  if (-not $Val) { return $false }
  try { $pieno = [System.IO.Path]::GetFullPath($Val) } catch { return $false }
  foreach ($r in $radici) {
    if ($r -and $pieno.StartsWith($r, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
  }
  # Manifest: leggi path interno
  if (Test-Path -LiteralPath $Val) {
    try {
      $m = Get-Content -LiteralPath $Val -Raw | ConvertFrom-Json
      if ($m.path) {
        $pp = [System.IO.Path]::GetFullPath([string]$m.path)
        foreach ($r in $radici) {
          if ($r -and $pp.StartsWith($r, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
        }
        if ([IO.Path]::GetFileName($pp) -ieq 'RendicontoSW-host.exe') { return $true }
      }
      if ($m.name -eq $nome) { return $true }
    } catch {}
  }
  return $false
}
foreach ($c in 'Software\Google\Chrome\NativeMessagingHosts', 'Software\Microsoft\Edge\NativeMessagingHosts',
               'Software\Mozilla\NativeMessagingHosts') {
  $k = "HKCU:\$c\$nome"
  if (-not (Test-Path -LiteralPath $k)) { Write-Host "Assente: $k"; continue }
  $val = $null
  try { $val = (Get-Item -LiteralPath $k).GetValue('') } catch {}
  Write-Host ("Valore attuale {0}: {1}" -f $k, $val)
  if ($Forza -or (Test-NostroValore $val)) {
    Remove-Item -LiteralPath $k -Force
    Write-Host "Rimosso: $k"
  } else {
    Write-Host "NON rimosso (non punta al nostro host; usa -Forza se sei sicuro): $k"
  }
}
