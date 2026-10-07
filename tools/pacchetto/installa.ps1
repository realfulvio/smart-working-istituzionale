# Installazione per l'utente (nessun diritto di amministratore, nessuna modifica di sistema).
# Legge dalla cartella condivisa del CED (solo lettura) e copia in %LOCALAPPDATA%\Programs\RendicontoSW.
#   powershell -ExecutionPolicy Bypass -File installa.ps1 [-Origine "..."] [-Destinazione "..."] [-CartellaDati "..."] [-Reinstalla] [-Forza]
# Cosa fa: confronto versione, controllo processi/spazio, verifica SHA-256 (elenco ⊆ file e copia),
# staging + scambio con rollback, collegamenti (WorkingDirectory = Documenti), voce Uninstall HKCU,
# copia di disinstalla.ps1 nella cartella di installazione.
# Cosa NON fa: Unblock-File, esclusioni Defender/ASR, HKLM, servizi, attività pianificate, scrittura su unità di rete.
# Codici: 0 ok · 10 impronte · 20 app in uso · 40 spazio · 50 versione più vecchia · 1 errore
param(
  [string]$Origine = $PSScriptRoot,
  [string]$Destinazione = "",
  [string]$CartellaDati = "",
  [switch]$Reinstalla,
  [switch]$Forza
)
$ErrorActionPreference = "Stop"
$log = Join-Path $env:TEMP ("rsw_installa_{0:yyyyMMdd_HHmmss}.log" -f (Get-Date))

function Scrivi-Log {
  param([string]$Msg)
  $riga = "{0:HH:mm:ss}  {1}" -f (Get-Date), $Msg
  Add-Content -LiteralPath $log -Value $riga -Encoding UTF8
  Write-Host $Msg
}

function Esci-Con {
  param([int]$Codice, [string]$Msg)
  if ($Msg) { Scrivi-Log $Msg }
  Scrivi-Log ("Log: {0}" -f $log)
  Scrivi-Log ("Codice di uscita: {0}" -f $Codice)
  exit $Codice
}

function Get-PercorsoLungo {
  # Forma completa e LUNGA del percorso (nomi brevi 8.3 come C:\Users\NOMEUT~1\...).
  # GetFullPath normalizza; GetLongPathName espande la parte esistente; il resto (non ancora creato) si riattacca.
  # Senza «~» non esistono alias brevi diversi dal nome lungo: niente chiamata nativa (veloce sui moduli).
  param([string]$Percorso)
  if ([string]::IsNullOrWhiteSpace($Percorso)) { return $Percorso }
  try { $pieno = [System.IO.Path]::GetFullPath($Percorso) } catch { return $Percorso }
  if ($pieno.IndexOf('~') -lt 0) { return $pieno }
  if (-not ("RSW.PercorsoNativo" -as [type])) {
    try {
      Add-Type -Namespace RSW -Name PercorsoNativo -MemberDefinition @"
[DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
public static extern uint GetLongPathName(string lpszShortPath, System.Text.StringBuilder lpszLongPath, uint cchBuffer);
"@ -ErrorAction Stop
    } catch { return $pieno }
  }
  $resto = @()
  $p = $pieno
  if ($p.Length -gt 3) { $p = $p.TrimEnd('\') }
  while ($p -and -not (Test-Path -LiteralPath $p)) {
    $resto = @(Split-Path -Leaf $p) + $resto
    $p = Split-Path -Parent $p
  }
  if (-not $p) { return $pieno }
  $lungo = $p
  try {
    $sb = New-Object System.Text.StringBuilder 32768
    $n = [RSW.PercorsoNativo]::GetLongPathName($p, $sb, [uint32]$sb.Capacity)
    if ($n -gt 0 -and $n -lt $sb.Capacity) { $lungo = $sb.ToString() }
  } catch {}
  foreach ($r in $resto) { $lungo = Join-Path $lungo $r }
  return $lungo
}

function Test-EGiunzione {
  param([string]$Percorso)
  $item = Get-Item -LiteralPath $Percorso -Force -ErrorAction SilentlyContinue
  if (-not $item) { return $false }
  return [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)
}

function Get-CampoVersione {
  param([string]$File, [string]$Campo)
  if (-not (Test-Path -LiteralPath $File)) { return $null }
  $c = Get-Content -LiteralPath $File -ErrorAction SilentlyContinue
  $pref = $Campo + '='
  foreach ($r in $c) {
    if ($r.StartsWith($pref)) { return $r.Substring($pref.Length).Trim() }
  }
  return $null
}

function Confronta-VersionePacchetto {
  # 0 uguale (stesso commit) · 1 aggiornamento/diversa · -1 pacchetto più vecchio (data= precedente)
  param([string]$FileNuovo, [string]$FileVecchio)
  $cN = Get-CampoVersione $FileNuovo 'commit'
  $cV = Get-CampoVersione $FileVecchio 'commit'
  if ($cN -and $cV) {
    if ($cN.Equals($cV, [System.StringComparison]::OrdinalIgnoreCase)) { return 0 }
    if ($cV.StartsWith($cN, [System.StringComparison]::OrdinalIgnoreCase) -or
        $cN.StartsWith($cV, [System.StringComparison]::OrdinalIgnoreCase)) { return 0 }
  }
  $dN = Get-CampoVersione $FileNuovo 'data'
  $dV = Get-CampoVersione $FileVecchio 'data'
  if ($dN -and $dV) {
    try {
      $tN = [datetime]::ParseExact($dN, 'yyyy-MM-dd HH:mm', [Globalization.CultureInfo]::InvariantCulture)
      $tV = [datetime]::ParseExact($dV, 'yyyy-MM-dd HH:mm', [Globalization.CultureInfo]::InvariantCulture)
      if ($tN -lt $tV) { return -1 }
      if ($tN -gt $tV) { return 1 }
    } catch {}
  }
  return 1
}

function Get-ProcessiPropri {
  param([string]$Cartella)
  $ris = @()
  if (-not (Test-Path -LiteralPath $Cartella)) { return $ris }
  $radice = (Get-PercorsoLungo $Cartella).TrimEnd('\') + '\'
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {
    $exe = $_.ExecutablePath
    if (-not $exe) { return }
    $pieno = Get-PercorsoLungo $exe
    if ($pieno.StartsWith($radice, [System.StringComparison]::OrdinalIgnoreCase)) {
      $ris += ("{0} (PID {1})" -f $_.Name, $_.ProcessId)
    }
  }
  return $ris
}

function Get-DimensioneCartella {
  param([string]$Percorso)
  $n = [long]0
  if (-not (Test-Path -LiteralPath $Percorso)) { return $n }
  Get-ChildItem -LiteralPath $Percorso -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object { $n += $_.Length }
  return $n
}

function Rimuovi-Sicuro {
  param([string]$Percorso)
  if (-not (Test-Path -LiteralPath $Percorso)) { return }
  if (Test-EGiunzione $Percorso) {
    throw "Rifiuto di cancellare giunzione/reparse: $Percorso"
  }
  Remove-Item -LiteralPath $Percorso -Recurse -Force -ErrorAction Stop
}

function Get-ComandoDisinstalla {
  # Riga di comando della voce «App installate» (collaudo ALFA3 N4): copia disinstalla.ps1 in TEMP (la cartella di
  # installazione viene rimossa), lo esegue con -MostraEsito (finestra di messaggio se rifiuta) e PROPAGA il codice
  # di uscita (exit $LASTEXITCODE). Percorsi tra apici singoli (spazi ammessi; l'apice si raddoppia).
  param([string]$Dest, [string]$Dati)
  $q = { param($x) "'" + ($x -replace "'", "''") + "'" }
  $dis = Join-Path $Dest 'disinstalla.ps1'
  $corpo = "`$t = Join-Path `$env:TEMP ('rsw_uninst_' + [guid]::NewGuid().ToString('N') + '.ps1'); " +
           "Copy-Item -LiteralPath $(& $q $dis) -Destination `$t -Force; " +
           "& `$t -Destinazione $(& $q $Dest) -CartellaDati $(& $q $Dati) -MostraEsito; `$c = `$LASTEXITCODE; " +
           "Remove-Item -LiteralPath `$t -Force -EA SilentlyContinue; exit `$c"
  return "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command `"& { $corpo }`""
}

function Registra-Uninstall {
  param([string]$Dest, [string]$Dati, [string]$Commit)
  $k = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\RendicontoSW'
  New-Item -Path $k -Force | Out-Null
  $cmd = Get-ComandoDisinstalla -Dest $Dest -Dati $Dati
  Set-ItemProperty -LiteralPath $k -Name 'DisplayName' -Value 'Rendiconto SW'
  Set-ItemProperty -LiteralPath $k -Name 'Publisher' -Value 'Ente'
  Set-ItemProperty -LiteralPath $k -Name 'DisplayVersion' -Value $(if ($Commit) { $Commit } else { 'ALFA' })
  Set-ItemProperty -LiteralPath $k -Name 'InstallLocation' -Value $Dest
  Set-ItemProperty -LiteralPath $k -Name 'UninstallString' -Value $cmd
  Set-ItemProperty -LiteralPath $k -Name 'NoModify' -Value 1 -Type DWord
  Set-ItemProperty -LiteralPath $k -Name 'NoRepair' -Value 1 -Type DWord
}

# --- inizio ---
try { "--- installa Rendiconto SW ---" | Set-Content -LiteralPath $log -Encoding UTF8 } catch {}
Scrivi-Log "Installazione di Rendiconto SW…"

if (-not $env:LOCALAPPDATA) { Esci-Con 1 "LOCALAPPDATA non definita." }
$Origine = Get-PercorsoLungo $Origine
$destDefault = Get-PercorsoLungo (Join-Path $env:LOCALAPPDATA "Programs\RendicontoSW")
$datiDefault = Get-PercorsoLungo (Join-Path $env:LOCALAPPDATA "RendicontoSW")
if ([string]::IsNullOrWhiteSpace($Destinazione)) { $Destinazione = $destDefault }
$dest = Get-PercorsoLungo $Destinazione
# Percorso di rete: UNC o unità mappata (DriveType Network). Il programma non scrive mai su risorse di rete.
function Test-PercorsoRete([string]$p) {
  if ($p -match '^\\\\') { return $true }
  if ($p -match '^([A-Za-z]):') { try { return ([System.IO.DriveInfo]::new($Matches[1] + ':\')).DriveType -eq [System.IO.DriveType]::Network } catch { return $false } }
  return $false
}
if (Test-PercorsoRete $dest) {
  Esci-Con 1 ("Destinazione non ammessa: {0}" -f $dest)
}
$parentDest = Split-Path -Parent $dest
$leafDest = Split-Path -Leaf $dest
if ([string]::IsNullOrWhiteSpace($CartellaDati)) {
  if ($dest.Equals($destDefault, [System.StringComparison]::OrdinalIgnoreCase)) {
    $CartellaDati = $datiDefault
  } else {
    # Sandbox: non toccare i dati reali dell'utente
    $CartellaDati = Join-Path $parentDest ($leafDest + "_dati")
  }
}
$dati = Get-PercorsoLungo $CartellaDati
if (Test-PercorsoRete $dati) {
  Esci-Con 1 ("CartellaDati non ammessa: {0}" -f $dati)
}
$destAtteso = $dest
$destNuova = Join-Path $parentDest ($leafDest + ".nuova")
$destVecchia = Join-Path $parentDest ($leafDest + ".vecchia")
$daRimuovere = Join-Path $parentDest ($leafDest + ".da_rimuovere")
$sums = Join-Path $Origine "SHA256SUMS.txt"
Scrivi-Log ("Destinazione: {0}" -f $dest)
Scrivi-Log ("Cartella dati: {0}" -f $dati)

if (-not (Test-Path -LiteralPath $sums)) { Esci-Con 1 "SHA256SUMS.txt non trovato in $Origine" }

# Pulisci residui di installazioni/disinstallazioni interrotte
foreach ($r in @($destNuova, $destVecchia, $daRimuovere)) {
  if (Test-Path -LiteralPath $r) {
    Scrivi-Log "Rimozione residuo: $r"
    try { Rimuovi-Sicuro $r } catch { Scrivi-Log $_.Exception.Message }
  }
}

# Versione (commit= e data= in VERSIONE.txt)
$fileVerNuova = Join-Path $Origine 'VERSIONE.txt'
$fileVerOra = Join-Path $dest 'VERSIONE.txt'
$vNuova = Get-CampoVersione $fileVerNuova 'commit'
$vOra = Get-CampoVersione $fileVerOra 'commit'
if ((Test-Path -LiteralPath $fileVerOra) -and (Test-Path -LiteralPath $fileVerNuova)) {
  $cmp = Confronta-VersionePacchetto $fileVerNuova $fileVerOra
  if ($cmp -eq 0 -and -not $Reinstalla) {
    Esci-Con 0 ("Già installata la stessa versione (commit={0}). Usa -Reinstalla per forzare." -f $vOra)
  }
  if ($cmp -lt 0 -and -not $Forza) {
    Esci-Con 50 ("Il pacchetto (commit={0}, data più vecchia) è precedente a quello installato (commit={1}). Usa -Forza per procedere." -f $vNuova, $vOra)
  }
  Scrivi-Log ("Aggiornamento: {0} → {1}" -f $vOra, $vNuova)
} elseif ($vNuova) {
  Scrivi-Log ("Versione pacchetto: commit={0}" -f $vNuova)
}

# App in esecuzione
$inEsec = @(Get-ProcessiPropri $dest)
if ($inEsec.Count) {
  Esci-Con 20 ("App in esecuzione: {0}. Chiudila e rilancia l'installazione." -f ($inEsec -join ', '))
}

# Spazio disco: pacchetto × 1,3 (+ margine per staging)
$dimOrig = (Get-DimensioneCartella (Join-Path $Origine 'app')) +
           (Get-DimensioneCartella (Join-Path $Origine 'ai')) +
           (Get-DimensioneCartella (Join-Path $Origine 'licenze'))
$serve = [long]($dimOrig * 1.3)
$driveLetter = $dest.Substring(0, 1)
$libero = $null
try {
  $libero = (Get-PSDrive -Name $driveLetter).Free
} catch {
  try { $libero = (Get-Item -LiteralPath "$driveLetter`:\").PSDrive.Free } catch {}
}
if ($null -ne $libero -and $libero -lt $serve) {
  Esci-Con 40 ("Spazio insufficiente su {0}: servono circa {1:N0} byte, liberi {2:N0}." -f $driveLetter, $serve, $libero)
}

# Carica elenco SHA256 (formato: hash + 2 spazi + percorso relativo con \)
# Nota: l'elenco NON è autenticato finché non c'è code signing (TODO CED).
$mappa = @{}
Get-Content -LiteralPath $sums | ForEach-Object {
  if ($_ -match '^([0-9a-fA-F]{64})\s+(.+)$') {
    $rel = $Matches[2].Trim() -replace '/', '\'
    $mappa[$rel] = $Matches[1].ToLower()
  }
}
if ($mappa.Count -eq 0) { Esci-Con 10 "SHA256SUMS.txt vuoto o formato non riconosciuto (atteso: hash + spazi + percorso)." }

# File reali del pacchetto che verranno copiati: devono essere TUTTI in elenco (niente extras non elencati)
$daCopiare = @()
foreach ($sub in @('app', 'ai', 'licenze')) {
  $p = Join-Path $Origine $sub
  if (-not (Test-Path -LiteralPath $p)) { continue }
  Get-ChildItem -LiteralPath $p -Recurse -File -Force | ForEach-Object {
    $rel = $_.FullName.Substring($Origine.Length).TrimStart('\', '/')
    $rel = $rel -replace '/', '\'
    $daCopiare += $rel
  }
}
# Anche script/docs a radice del pacchetto presenti in SUMS (installa.ps1, …) — non obbligatori in dest
$extras = @()
foreach ($rel in $daCopiare) {
  if (-not $mappa.ContainsKey($rel)) { $extras += $rel }
}
if ($extras.Count) {
  Scrivi-Log "File nel pacchetto NON presenti in SHA256SUMS.txt (rifiutati):"
  $extras | Select-Object -First 30 | ForEach-Object { Scrivi-Log ("  {0}" -f $_) }
  Esci-Con 10 ("{0} file non elencati in SHA256SUMS.txt: installazione annullata." -f $extras.Count)
}

# Verifica impronte sul SORGENTE (fallimento rapido prima di toccare disco)
$errori = 0
foreach ($rel in $daCopiare) {
  $f = Join-Path $Origine $rel
  $h = (Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash.ToLower()
  if ($h -ne $mappa[$rel]) {
    Scrivi-Log ("impronta NON corrispondente (origine): {0}" -f $rel)
    $errori++
  }
}
if ($errori) { Esci-Con 10 "$errori file non corrispondono in origine: installazione annullata (avvisare i Sistemi Informativi)." }

# Staging
Scrivi-Log "Copia in cartella di staging…"
New-Item -ItemType Directory -Force -Path $destNuova | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $dati "cache_ai") | Out-Null

# Copia file per file con LiteralPath (gestisce [ ] nel percorso)
foreach ($rel in $daCopiare) {
  $src = Join-Path $Origine $rel
  # app\* → $destNuova\…  (toglie il prefisso app\)
  if ($rel -like 'app\*') {
    $destRel = $rel.Substring(4)
  } elseif ($rel -like 'ai\*') {
    $destRel = $rel
  } elseif ($rel -like 'licenze\*') {
    $destRel = $rel
  } else {
    continue
  }
  $dst = Join-Path $destNuova $destRel
  $dir = Split-Path -Parent $dst
  if (-not (Test-Path -LiteralPath $dir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
  }
  Copy-Item -LiteralPath $src -Destination $dst -Force
}

# Copia disinstalla.ps1 nell'installazione (per voce Uninstall e uso offline)
$disSrc = Join-Path $Origine 'disinstalla.ps1'
if (Test-Path -LiteralPath $disSrc) {
  Copy-Item -LiteralPath $disSrc -Destination (Join-Path $destNuova 'disinstalla.ps1') -Force
}
# VERSIONE.txt / LEGGIMI se presenti
foreach ($n in @('VERSIONE.txt', 'LEGGIMI_ALFA.txt', 'LEGGIMI.txt')) {
  $s = Join-Path $Origine $n
  if (Test-Path -LiteralPath $s) {
    Copy-Item -LiteralPath $s -Destination (Join-Path $destNuova $n) -Force
  }
}

# Verifica SHA-256 SULLA COPIA (staging)
Scrivi-Log "Verifica impronte sulla copia in staging…"
$erroriCopia = 0
foreach ($rel in $daCopiare) {
  if ($rel -like 'app\*') { $destRel = $rel.Substring(4) }
  elseif ($rel -like 'ai\*' -or $rel -like 'licenze\*') { $destRel = $rel }
  else { continue }
  $f = Join-Path $destNuova $destRel
  if (-not (Test-Path -LiteralPath $f)) {
    Scrivi-Log ("manca nella copia: {0}" -f $destRel); $erroriCopia++; continue
  }
  $h = (Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash.ToLower()
  if ($h -ne $mappa[$rel]) {
    Scrivi-Log ("impronta NON corrispondente (copia): {0}" -f $destRel); $erroriCopia++
  }
}
if ($erroriCopia) {
  try { Rimuovi-Sicuro $destNuova } catch {}
  Esci-Con 10 "$erroriCopia file non corrispondono nella copia: staging eliminato, installazione annullata."
}

# Scambio con rollback
Scrivi-Log "Scambio cartelle (con rollback)…"
$avevaDest = Test-Path -LiteralPath $dest
try {
  if ($avevaDest) {
    if (Test-EGiunzione $dest) { throw "La destinazione è una giunzione: interrompo." }
    Rename-Item -LiteralPath $dest -NewName ($leafDest + ".vecchia") -ErrorAction Stop
  }
  Rename-Item -LiteralPath $destNuova -NewName $leafDest -ErrorAction Stop
} catch {
  Scrivi-Log ("Errore nello scambio: {0}" -f $_.Exception.Message)
  # Rollback
  if (-not (Test-Path -LiteralPath $dest) -and (Test-Path -LiteralPath $destVecchia)) {
    try { Rename-Item -LiteralPath $destVecchia -NewName $leafDest -ErrorAction Stop } catch {}
  }
  if (Test-Path -LiteralPath $destNuova) { try { Rimuovi-Sicuro $destNuova } catch {} }
  Esci-Con 1 "Installazione annullata: ripristinata la versione precedente (se presente)."
}

# Rimuovi vecchia (file stale eliminati grazie allo swap)
if (Test-Path -LiteralPath $destVecchia) {
  try { Rimuovi-Sicuro $destVecchia; Scrivi-Log "Rimossa versione precedente." }
  catch { Scrivi-Log ("Impossibile rimuovere .vecchia subito: {0} (si potrà cancellare al prossimo giro)" -f $_.Exception.Message) }
}

# Guardia finale su $dest
$pieno = Get-PercorsoLungo (Get-Item -LiteralPath $dest).FullName
if (-not $pieno.Equals($destAtteso, [System.StringComparison]::OrdinalIgnoreCase)) {
  Esci-Con 1 ("Destinazione inattesa dopo lo scambio: {0}" -f $pieno)
}

# Collegamenti: WorkingDirectory = Documenti (non la cartella di installazione)
$start = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$wd = [Environment]::GetFolderPath('MyDocuments')
if (-not $wd) { $wd = $env:USERPROFILE }
$sh = New-Object -ComObject WScript.Shell
$lnk = $sh.CreateShortcut((Join-Path $start "Resoconto lavoro agile.lnk"))
$lnk.TargetPath = Join-Path $dest "RendicontoSW.exe"
$lnk.WorkingDirectory = $wd
$lnk.Save()
$lnk = $sh.CreateShortcut((Join-Path $start "Verifica resoconto.lnk"))
$lnk.TargetPath = Join-Path $dest "VerificaRendiconto.exe"
$lnk.WorkingDirectory = $wd
$lnk.Save()
Scrivi-Log ("Collegamenti creati (cartella di lavoro: {0})" -f $wd)

# Voce Uninstall per utente (HKCU, mai HKLM)
Registra-Uninstall -Dest $dest -Dati $dati -Commit $vNuova
Scrivi-Log "Registrata voce in Impostazioni → App (HKCU Uninstall)."

# Firma (informativa)
Get-ChildItem -LiteralPath $dest -Filter *.exe -ErrorAction SilentlyContinue | ForEach-Object {
  Scrivi-Log ("{0}: firma {1}" -f $_.Name, (Get-AuthenticodeSignature -LiteralPath $_.FullName).Status)
}
$llama = Join-Path $dest "ai\llama\llama-server.exe"
if (Test-Path -LiteralPath $llama) {
  Scrivi-Log ("llama-server.exe: firma {0}" -f (Get-AuthenticodeSignature -LiteralPath $llama).Status)
}

Scrivi-Log "--- riepilogo ---"
Scrivi-Log ("Installato in {0} (dati in {1})." -f $dest, $dati)
Scrivi-Log "Avvio: menu Start → Resoconto lavoro agile."
Scrivi-Log "Se Windows mostra SmartScreen: «Altre informazioni» → «Esegui comunque» (solo ALFA)."
Scrivi-Log "Se al primo avvio compare «Accesso negato» (ASR), riprova una volta; non aggiungere esclusioni antivirus."
Scrivi-Log "Nota: SHA256SUMS.txt non è autenticato finché gli eseguibili/elenco non sono firmati (code signing CED)."
Esci-Con 0 $null
