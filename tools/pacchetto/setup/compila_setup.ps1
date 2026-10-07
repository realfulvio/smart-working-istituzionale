# Compila il Setup guidato di Rendiconto SW (Inno Setup 6) da una cartella di pacchetto già pronta (prepara_alfa.ps1).
#   powershell -ExecutionPolicy Bypass -File tools\pacchetto\setup\compila_setup.ps1 `
#     -Pacchetto "$env:USERPROFILE\Downloads\BONIFICA" -Uscita "$env:USERPROFILE\Downloads\SETUP_BONIFICA" [-Dividi] [-Iscc <ISCC.exe>]
# Passi: 1) struttura del pacchetto e SHA256SUMS.txt (stesse regole di installa.ps1, più severe: ogni file del pacchetto
# deve essere elencato e corrispondere, perché finisce dentro il Setup); 2) ISCC.exe di Inno Setup 6.4+ (se manca:
# winget install --id JRSoftware.InnoSetup -e --scope user, installatore firmato, nessun diritto di amministratore);
# 3) compilazione di RendicontoSW.iss con /DPacchetto, /DSpazioExtra (pacchetto × 1,3 per lo staging di installa.ps1)
# e /O<Uscita>; 4) SHA-256 del Setup in <Setup>.sha256 accanto.
# Cosa NON fa: firma, esclusioni antivirus, Unblock-File, scritture in rete, modifiche al pacchetto.
# Codici: 0 ok · 10 pacchetto non integro · 2 Inno Setup non trovato/non installabile · 3 compilazione non riuscita · 1 errore
param(
  [Parameter(Mandatory = $true)][string]$Pacchetto,
  [Parameter(Mandatory = $true)][string]$Uscita,
  [string]$Iscc = "",
  [switch]$Dividi,
  [switch]$NonInstallareInno,
  [switch]$SoloVerifica
)
$ErrorActionPreference = "Stop"
$sep = [IO.Path]::DirectorySeparatorChar
$log = Join-Path ([IO.Path]::GetTempPath()) ("rsw_compila_setup_{0:yyyyMMdd_HHmmss}.log" -f (Get-Date))

function Scrivi {
  param([string]$Msg)
  Add-Content -LiteralPath $log -Value ("{0:HH:mm:ss}  {1}" -f (Get-Date), $Msg) -Encoding UTF8
  Write-Host $Msg
}

function Esci {
  param([int]$Codice, [string]$Msg)
  if ($Msg) { Scrivi $Msg }
  Scrivi ("Log: {0}" -f $log)
  Scrivi ("Codice di uscita: {0}" -f $Codice)
  exit $Codice
}

function Trova-Iscc {
  $cand = @()
  if ($Iscc) { $cand += $Iscc }
  foreach ($radice in @('HKCU:', 'HKLM:')) {
    foreach ($k in @('Software\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1',
                     'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1')) {
      try {
        $p = (Get-ItemProperty -LiteralPath "$radice\$k" -ErrorAction Stop).InstallLocation
        if ($p) { $cand += (Join-Path $p 'ISCC.exe') }
      } catch {}
    }
  }
  if ($env:LOCALAPPDATA) { $cand += (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe') }
  if (${env:ProgramFiles(x86)}) { $cand += (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe') }
  if ($env:ProgramFiles) { $cand += (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe') }
  $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
  if ($cmd) { $cand += $cmd.Source }
  foreach ($c in $cand) {
    if ($c -and (Test-Path -LiteralPath $c)) { return (Get-Item -LiteralPath $c).FullName }
  }
  return $null
}

try { "--- compila_setup Rendiconto SW ---" | Set-Content -LiteralPath $log -Encoding UTF8 } catch {}
# percorsi relativi risolti rispetto alla cartella corrente di PowerShell (non a quella del processo .NET)
$Pacchetto = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Pacchetto).TrimEnd('\', '/')
$Uscita = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Uscita).TrimEnd('\', '/')
$iss = Join-Path $PSScriptRoot 'RendicontoSW.iss'
Scrivi ("Pacchetto: {0}" -f $Pacchetto)
Scrivi ("Uscita:    {0}" -f $Uscita)
# Percorso di rete: UNC o unità mappata (DriveType Network). Il programma non scrive mai su risorse di rete.
function Test-PercorsoRete([string]$p) {
  if ($p -match '^\\\\') { return $true }
  if ($p -match '^([A-Za-z]):') { try { return ([System.IO.DriveInfo]::new($Matches[1] + ':\')).DriveType -eq [System.IO.DriveType]::Network } catch { return $false } }
  return $false
}
if (Test-PercorsoRete $Uscita) { Esci 1 "Cartella di uscita non ammessa: $Uscita (niente unità né percorsi di rete)." }
if (($Uscita + $sep).StartsWith($Pacchetto + $sep, [StringComparison]::OrdinalIgnoreCase)) {
  Esci 1 "La cartella di uscita non può stare dentro il pacchetto (finirebbe nel Setup successivo)."
}
if (-not (Test-Path -LiteralPath $iss)) { Esci 1 "Script Inno non trovato: $iss" }

# 1) Struttura e impronte
foreach ($n in @('installa.ps1', 'disinstalla.ps1', 'SHA256SUMS.txt', 'VERSIONE.txt', 'app\RendicontoSW.exe', 'app\VerificaRendiconto.exe')) {
  $p = Join-Path $Pacchetto ($n -replace '\\', $sep)
  if (-not (Test-Path -LiteralPath $p)) { Esci 10 "Nel pacchetto manca $n" }
}
$mappa = @{}
foreach ($r in Get-Content -LiteralPath (Join-Path $Pacchetto 'SHA256SUMS.txt')) {
  if ($r -match '^([0-9a-fA-F]{64})\s+(.+)$') { $mappa[($Matches[2].Trim() -replace '/', '\')] = $Matches[1].ToLower() }
}
if ($mappa.Count -eq 0) { Esci 10 "SHA256SUMS.txt vuoto o in formato non riconosciuto." }
Scrivi ("Verifica delle impronte di {0} file elencati…" -f $mappa.Count)
$file = @(Get-ChildItem -LiteralPath $Pacchetto -Recurse -File -Force)
$extra = @(); $errati = @(); $visti = @{}; $byte = [long]0
foreach ($f in $file) {
  $rel = $f.FullName.Substring($Pacchetto.Length).TrimStart('\', '/') -replace '/', '\'
  if ($rel -ieq 'SHA256SUMS.txt') { continue }
  $byte += $f.Length
  if (-not $mappa.ContainsKey($rel)) { $extra += $rel; continue }
  $visti[$rel] = $true
  $h = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash.ToLower()
  if ($h -ne $mappa[$rel]) { $errati += $rel }
}
$mancanti = @($mappa.Keys | Where-Object { -not $visti.ContainsKey($_) })
foreach ($x in $extra | Select-Object -First 20) { Scrivi ("  non elencato: {0}" -f $x) }
foreach ($x in $errati | Select-Object -First 20) { Scrivi ("  impronta diversa: {0}" -f $x) }
foreach ($x in $mancanti | Select-Object -First 20) { Scrivi ("  mancante: {0}" -f $x) }
if ($extra.Count -or $errati.Count -or $mancanti.Count) {
  Esci 10 ("Pacchetto non integro: {0} non elencati, {1} impronte diverse, {2} mancanti. Nessun Setup compilato." -f $extra.Count, $errati.Count, $mancanti.Count)
}
$ver = (Get-Content -LiteralPath (Join-Path $Pacchetto 'VERSIONE.txt') | Where-Object { $_ -match '^(commit|data)=' }) -join ' '
Scrivi ("Pacchetto integro: {0} file, {1:N0} byte ({2})." -f ($file.Count - 1), $byte, $ver)
if ($SoloVerifica) { Esci 0 "Solo verifica richiesta: fine." }

# 2) Inno Setup
$isccExe = Trova-Iscc
if (-not $isccExe -and -not $NonInstallareInno) {
  $wg = Get-Command winget.exe -ErrorAction SilentlyContinue
  if ($wg) {
    Scrivi "Inno Setup non trovato: installazione per l'utente con winget (JRSoftware.InnoSetup, --scope user)…"
    # in Windows PowerShell 5.1 lo stderr di un programma con 2>&1 e "Stop" interromperebbe lo script
    $ErrorActionPreference = "Continue"
    & $wg.Source install --id JRSoftware.InnoSetup -e --scope user --silent --accept-package-agreements --accept-source-agreements --disable-interactivity 2>&1 |
      ForEach-Object { Scrivi ("  winget: {0}" -f $_) }
    $ErrorActionPreference = "Stop"
    Scrivi ("winget: codice {0}" -f $LASTEXITCODE)
    $isccExe = Trova-Iscc
  } else {
    Scrivi "winget non disponibile."
  }
}
if (-not $isccExe) {
  Esci 2 ("ISCC.exe non trovato. Installa Inno Setup 6 per l'utente (winget install --id JRSoftware.InnoSetup -e --scope user, " +
          "oppure innosetup-6.7.3.exe da https://jrsoftware.org/isdl.php scegliendo «Installa solo per me») e rilancia, " +
          "anche con -Iscc <percorso di ISCC.exe>. Non aggirare eventuali blocchi di sicurezza.")
}
$vIscc = (Get-Item -LiteralPath $isccExe).VersionInfo.FileVersion
Scrivi ("ISCC: {0} (versione {1})" -f $isccExe, $vIscc)

# Margine conservativo per exe + temporanei Inno, prima di compilare 1,3 GB.
$driveSetup = [System.IO.DriveInfo]::new([IO.Path]::GetPathRoot([IO.Path]::GetFullPath($Uscita)))
$liberiSetup = $driveSetup.AvailableFreeSpace
$richiestiSetup = [long]([Math]::Max(4GB, $byte * 3))
Scrivi ("Spazio prima del Setup: {0:N0} byte liberi; margine richiesto {1:N0}." -f $liberiSetup,$richiestiSetup)
if ($liberiSetup -lt $richiestiSetup) { Esci 3 "Spazio insufficiente: compilazione non avviata." }
# 3) Compilazione: il nome deriva dalla versione dichiarata in Inno.
$versioneMatch = [regex]::Match((Get-Content -LiteralPath $iss -Raw -Encoding UTF8), '#define AppVer "([0-9]+\.[0-9]+\.[0-9]+)"')
if (-not $versioneMatch.Success) { Esci 3 "AppVer assente o non valida nel file Inno Setup." }
$setupNome = 'Setup_RendicontoSW_' + $versioneMatch.Groups[1].Value
New-Item -ItemType Directory -Force -Path $Uscita | Out-Null
Get-ChildItem -LiteralPath $Uscita -Filter ($setupNome + '*') -ErrorAction SilentlyContinue | Remove-Item -Force
$spazio = [long]($byte * 1.3)
$argomenti = @("/DPacchetto=$Pacchetto", "/DSpazioExtra=$spazio", "/O$Uscita", "/Qp")
if ($Dividi) { $argomenti += "/DDividi=1" }
$entePacchetto = Get-Content -LiteralPath (Join-Path $Pacchetto "app/_internal/config/ente.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$argomenti += ("/DNomeEnte=" + $entePacchetto.nome)
$immaginiSetup = Join-Path $Uscita "immagini"
python (Join-Path $PSScriptRoot "genera_immagini.py") --config (Join-Path $Pacchetto "app/_internal/config/ente.json") --output $immaginiSetup
if ($LASTEXITCODE -ne 0) { Esci 3 "Generazione immagini edizione fallita." }
$argomenti += ("/DImmagini=" + $immaginiSetup)
$argomenti += $iss
Scrivi ("Compilazione (può richiedere diversi minuti per 1,4 GB): {0} {1}" -f $isccExe, ($argomenti -join ' '))
$t0 = Get-Date
$ErrorActionPreference = "Continue"
& $isccExe @argomenti 2>&1 | ForEach-Object { Scrivi ("  iscc: {0}" -f $_) }
$rc = $LASTEXITCODE
$ErrorActionPreference = "Stop"
Scrivi ("ISCC: codice {0} in {1:N0} s" -f $rc, ((Get-Date) - $t0).TotalSeconds)
$setup = Join-Path $Uscita ($setupNome + '.exe')
if ($rc -ne 0 -or -not (Test-Path -LiteralPath $setup)) { Esci 3 "Compilazione non riuscita: vedi le righe «iscc:» del log." }

# 4) Impronte del risultato
$righe = @()
foreach ($o in @(Get-ChildItem -LiteralPath $Uscita -Filter ($setupNome + '*') | Where-Object { $_.Extension -in '.exe', '.bin' } | Sort-Object Name)) {
  $h = (Get-FileHash -LiteralPath $o.FullName -Algorithm SHA256).Hash.ToLower()
  $righe += ("{0}  {1}" -f $h, $o.Name)
  Scrivi ("{0}: {1:N0} byte, SHA-256 {2}" -f $o.Name, $o.Length, $h)
}
$righe | Set-Content -LiteralPath ($setup + '.sha256') -Encoding ASCII
try { Scrivi ("Firma del Setup: {0} (atteso NotSigned finché non c'è il certificato dell'Ente)" -f (Get-AuthenticodeSignature -LiteralPath $setup).Status) } catch {}
Esci 0 ("Setup pronto: {0}" -f $setup)
