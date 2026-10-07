# Disinstallazione per l'utente. I dati (resoconti, chiave, JSON) restano, salvo -RimuoviDati
# con conferma per categoria. Nessun Unblock-File, nessuna esclusione Defender, nessun HKLM.
# Codici di uscita: 0 ok · 20 processi/file in uso · 30 rimozione parziale · 1 errore generico
# Con l'app aperta: chiede «Chiudo i processi…? [s/N]» (solo processi con l'eseguibile nella cartella di
# installazione); senza risposta «s», o in una sessione non interattiva senza -Forza, RIFIUTA con codice 20 e non
# tocca nulla. -Forza chiude quei processi senza chiedere. I programmi di terzi non vengono mai chiusi.
# -MostraEsito (usato dalla voce «App installate»): se l'esito non è 0 mostra una finestra di messaggio, così il
# rifiuto non sparisce con la console (collaudo ALFA3 N4). RSW_SENZA_FINESTRE=1 la sopprime (collaudi automatici).
param(
  [string]$Destinazione = "",
  [string]$CartellaDati = "",
  [switch]$RimuoviDati,
  [switch]$Forza,
  [switch]$MostraEsito
)
$ErrorActionPreference = "Stop"
$script:CodiceUscita = 0
$log = Join-Path $env:TEMP ("rsw_disinstalla_{0:yyyyMMdd_HHmmss}.log" -f (Get-Date))

function Scrivi-Log {
  param([string]$Msg)
  $riga = "{0:HH:mm:ss}  {1}" -f (Get-Date), $Msg
  Add-Content -LiteralPath $log -Value $riga -Encoding UTF8
  Write-Host $Msg
}

function Mostra-Esito {
  param([int]$Codice, [string]$Msg)
  if (-not $MostraEsito -or $Codice -eq 0 -or $env:RSW_SENZA_FINESTRE -eq '1') { return }
  $testo = ("La disinstallazione di Rendiconto SW non è stata completata (codice {0}).`n`n{1}`n`nDettagli nel log:`n{2}" -f
            $Codice, $(if ($Msg) { $Msg } else { "Vedi il log." }), $log)
  try {
    Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
    [void][System.Windows.Forms.MessageBox]::Show($testo, "Rendiconto SW - disinstallazione",
      [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning)
  } catch {
    Write-Host $testo
    try { [void](Read-Host "Premi Invio per chiudere") } catch {}
  }
}

function Esci-Con {
  param([int]$Codice, [string]$Msg)
  if ($Msg) { Scrivi-Log $Msg }
  Scrivi-Log ("Log: {0}" -f $log)
  Scrivi-Log ("Codice di uscita: {0}" -f $Codice)
  Mostra-Esito $Codice $Msg
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


function Get-ProcessiBloccanti {
  <#
    Restart Manager: elenca i processi che tengono aperti file nella cartella
    (anche PowerShell con FileStream, non solo moduli caricati).
  #>
  param([string]$Cartella)
  $ris = @()
  if (-not (Test-Path -LiteralPath $Cartella)) { return $ris }
  $files = @(Get-ChildItem -LiteralPath $Cartella -Recurse -File -Force -ErrorAction SilentlyContinue |
    Select-Object -First 48 | ForEach-Object { $_.FullName })
  if (-not $files.Count) { return $ris }
  if (-not ("RSW_RmNative" -as [type])) {
    Add-Type -Namespace RSW -Name RmNative -MemberDefinition @"
[DllImport("rstrtmgr.dll", CharSet=CharSet.Unicode)]
public static extern int RmStartSession(out uint pSessionHandle, int dwSessionFlags, string strSessionKey);
[DllImport("rstrtmgr.dll")]
public static extern int RmEndSession(uint pSessionHandle);
[DllImport("rstrtmgr.dll", CharSet=CharSet.Unicode)]
public static extern int RmRegisterResources(uint pSessionHandle, uint nFiles, string[] rgsFilenames, uint nApplications, IntPtr rgApplications, uint nServices, string[] rgsServiceNames);
[DllImport("rstrtmgr.dll")]
public static extern int RmGetList(uint dwSessionHandle, out uint pnProcInfoNeeded, ref uint pnProcInfo, IntPtr rgAffectedApps, ref uint lpdwRebootReasons);
"@ -ErrorAction Stop
  }
  $session = [uint32]0
  $key = [guid]::NewGuid().ToString("N").Substring(0, 32)
  if ([RSW.RmNative]::RmStartSession([ref]$session, 0, $key) -ne 0) { return $ris }
  try {
    if ([RSW.RmNative]::RmRegisterResources($session, [uint32]$files.Count, [string[]]$files, [uint32]0, [IntPtr]::Zero, [uint32]0, $null) -ne 0) {
      return $ris
    }
    $needed = [uint32]0; $count = [uint32]0; $reboot = [uint32]0
    $rc = [RSW.RmNative]::RmGetList($session, [ref]$needed, [ref]$count, [IntPtr]::Zero, [ref]$reboot)
    # 234 = ERROR_MORE_DATA
    if ($needed -eq 0) { return $ris }
    # RM_PROCESS_INFO is ~ raw size: allocate buffer. Structure size ~ 672 bytes on Unicode.
    $structSize = 672
    $buf = [Runtime.InteropServices.Marshal]::AllocHGlobal([int]($structSize * $needed))
    try {
      $count = $needed
      $rc = [RSW.RmNative]::RmGetList($session, [ref]$needed, [ref]$count, $buf, [ref]$reboot)
      if ($rc -ne 0) { return $ris }
      $radice = (Get-PercorsoLungo $Cartella).TrimEnd('\') + '\'
      for ($i = 0; $i -lt $count; $i++) {
        $ptr = [IntPtr]::Add($buf, $i * $structSize)
        $pid_ = [Runtime.InteropServices.Marshal]::ReadInt32($ptr)  # dwProcessId at start of RM_UNIQUE_PROCESS
        if ($pid_ -le 0) { continue }
        $nome = $null
        try { $nome = (Get-Process -Id $pid_ -ErrorAction SilentlyContinue).ProcessName } catch {}
        if (-not $nome) { $nome = "PID $pid_" }
        $exe = $null
        try { $exe = (Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $pid_) -ErrorAction SilentlyContinue).ExecutablePath } catch {}
        $tipo = 'terzi'
        if ($exe) {
          try {
            if ((Get-PercorsoLungo $exe).StartsWith($radice, [System.StringComparison]::OrdinalIgnoreCase)) { $tipo = 'app' }
          } catch {}
        }
        $ris += [pscustomobject]@{ Tipo = $tipo; Nome = $nome; Pid = $pid_; Path = $exe }
      }
    } finally {
      [Runtime.InteropServices.Marshal]::FreeHGlobal($buf)
    }
  } finally {
    [void][RSW.RmNative]::RmEndSession($session)
  }
  return $ris
}

function Get-ProcessiCartella {
  param([string]$Cartella)
  $ris = @()
  if (-not (Test-Path -LiteralPath $Cartella)) { return $ris }
  $radice = (Get-PercorsoLungo $Cartella).TrimEnd('\') + '\'
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {
    $exe = $_.ExecutablePath
    if (-not $exe) { return }
    $pieno = Get-PercorsoLungo $exe
    if ($pieno.StartsWith($radice, [System.StringComparison]::OrdinalIgnoreCase)) {
      $ris += [pscustomobject]@{ Tipo = 'app'; Nome = $_.Name; Pid = $_.ProcessId; Path = $pieno; Riga = [string]$_.CommandLine }
    }
  }
  # Terzi che hanno caricato moduli dalla cartella (es. Acrobat con VCRUNTIME dalla installazione)
  Get-Process -ErrorAction SilentlyContinue | ForEach-Object {
    $p = $_
    $gia = $ris | Where-Object { $_.Pid -eq $p.Id }
    if ($gia) { return }
    $mod = $false
    try {
      $mod = [bool]($p.Modules | Where-Object {
        $_.FileName -and (Get-PercorsoLungo $_.FileName).StartsWith($radice, [System.StringComparison]::OrdinalIgnoreCase)
      } | Select-Object -First 1)
    } catch { $mod = $false }
    if ($mod) {
      $ris += [pscustomobject]@{ Tipo = 'terzi'; Nome = $p.ProcessName; Pid = $p.Id; Path = $null }
    }
  }
  return $ris
}

function Stop-ProcessiPropri {
  param([string]$Cartella)
  $chiusi = @()
  $lista = Get-ProcessiCartella $Cartella | Where-Object { $_.Tipo -eq 'app' }
  foreach ($p in $lista) {
    try {
      Stop-Process -Id $p.Pid -Force -ErrorAction Stop
      $chiusi += ("{0} (PID {1})" -f $p.Nome, $p.Pid)
    } catch {
      Scrivi-Log ("Impossibile chiudere {0} (PID {1}): {2}" -f $p.Nome, $p.Pid, $_.Exception.Message)
    }
  }
  return $chiusi
}

function Rimuovi-CollegamentiPerBersaglio {
  param([string]$Dest)
  $radice = (Get-PercorsoLungo $Dest).TrimEnd('\') + '\'
  $luoghi = @(
    (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"),
    [Environment]::GetFolderPath('Desktop'),
    [Environment]::GetFolderPath('CommonDesktopDirectory')
  ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique
  $sh = New-Object -ComObject WScript.Shell
  foreach ($dir in $luoghi) {
    Get-ChildItem -LiteralPath $dir -Filter *.lnk -ErrorAction SilentlyContinue | ForEach-Object {
      try {
        $lnk = $sh.CreateShortcut($_.FullName)
        $tp = $lnk.TargetPath
        if ($tp -and (Get-PercorsoLungo $tp).StartsWith($radice, [System.StringComparison]::OrdinalIgnoreCase)) {
          Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
          Scrivi-Log ("Rimosso collegamento: {0}" -f $_.FullName)
        }
      } catch {}
    }
  }
  # Nomi noti (retrocompatibilità)
  $start = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
  foreach ($n in @("Resoconto lavoro agile.lnk", "Verifica resoconto.lnk", "Disinstalla Rendiconto SW.lnk")) {
    Remove-Item -LiteralPath (Join-Path $start $n) -Force -ErrorAction SilentlyContinue
  }
}

function Rimuovi-HostBrowserSeNostri {
  param([string]$Dest)
  $radice = (Get-PercorsoLungo $Dest).TrimEnd('\') + '\'
  $nome = 'org.smartworking.istituzionale'
  foreach ($c in @(
    'Software\Google\Chrome\NativeMessagingHosts',
    'Software\Microsoft\Edge\NativeMessagingHosts',
    'Software\Mozilla\NativeMessagingHosts'
  )) {
    $k = "HKCU:\$c\$nome"
    if (-not (Test-Path -LiteralPath $k)) { continue }
    try {
      $val = (Get-Item -LiteralPath $k).GetValue('')
      if (-not $val) { continue }
      $pieno = Get-PercorsoLungo $val
      $appartiene = $pieno.StartsWith($radice, [System.StringComparison]::OrdinalIgnoreCase)
      if (-not $appartiene -and (Test-Path -LiteralPath $val)) {
        try {
          $m = Get-Content -LiteralPath $val -Raw -ErrorAction Stop | ConvertFrom-Json
          if ($m.path) {
            $pp = Get-PercorsoLungo ([string]$m.path)
            $appartiene = $pp.StartsWith($radice, [System.StringComparison]::OrdinalIgnoreCase)
          }
        } catch {}
      }
      if ($appartiene) {
        Remove-Item -LiteralPath $k -Force -ErrorAction SilentlyContinue
        Scrivi-Log ("Rimossa chiave host browser: {0}" -f $k)
      } else {
        Scrivi-Log ("Host browser lasciato (non punta a questa installazione): {0} -> {1}" -f $k, $val)
      }
    } catch {
      Scrivi-Log ("Host browser: impossibile leggere {0}: {1}" -f $k, $_.Exception.Message)
    }
  }
}

function Rimuovi-VoceDisinstalla {
  $k = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\RendicontoSW'
  if (Test-Path -LiteralPath $k) {
    Remove-Item -LiteralPath $k -Recurse -Force -ErrorAction SilentlyContinue
    Scrivi-Log "Rimossa voce «App installate» (HKCU Uninstall)."
  }
}

function Conferma-Si {
  param([string]$Domanda)
  if ($Forza) { return $true }
  if (-not [Environment]::UserInteractive) {
    Scrivi-Log ("Conferma richiesta ma sessione non interattiva (usare -Forza): {0}" -f $Domanda)
    return $false
  }
  # -NonInteractive o console senza input: Read-Host fallisce → nessuna conferma → rifiuto (codice 20), mai errore 1
  try { $r = Read-Host $Domanda } catch {
    Scrivi-Log ("Conferma richiesta ma nessuno può rispondere (usare -Forza): {0}" -f $Domanda)
    return $false
  }
  return ($r -match '^[sSyY]')
}

# --- inizio ---
# Processo di raccolta della modalita collector («RendicontoSW.exe _esegui», attivo tra «Avvia giornata» e «Pausa» o
# «Chiudi giornata»). Prima gli si chiede di fermarsi come con «Pausa» (stato\comando.json nella cartella dati, solo
# se stato\demone.json riporta lo stesso PID): chiude la fascia in corso e scrive la pausa. Se entro 20 s non e'
# uscito lo si chiude. Nessuna conferma: e' un processo in sottofondo dell'app che si sta disinstallando. I dati
# della giornata restano; alla prossima apertura basta «Riprendi» o «Chiudi giornata».
function Get-ProcessiRaccolta {
  param([string]$Cartella)
  return @(Get-ProcessiCartella $Cartella | Where-Object { $_.Tipo -eq 'app' -and $_.Riga -match '(^|\s)_esegui(\s|$)' })
}

function Stop-Raccolta {
  param([string]$Cartella, [string[]]$CartelleDati)
  $racc = @(Get-ProcessiRaccolta $Cartella)
  if (-not $racc.Count) { return }
  foreach ($r in $racc) {
    Scrivi-Log ("Processo di raccolta attivo: {0} (PID {1})" -f $r.Nome, $r.Pid)
    foreach ($d in ($CartelleDati | Select-Object -Unique)) {
      $fd = Join-Path $d 'stato\demone.json'
      if (-not (Test-Path -LiteralPath $fd)) { continue }
      try { $info = Get-Content -LiteralPath $fd -Raw -Encoding UTF8 | ConvertFrom-Json } catch { continue }
      if (-not $info -or [string]$info.pid -ne [string]$r.Pid) { continue }
      $ts = (Get-Date).ToString("yyyy-MM-dd'T'HH:mm:sszzz", [System.Globalization.CultureInfo]::InvariantCulture)
      $fc = Join-Path $d 'stato\comando.json'
      try {
        [System.IO.File]::WriteAllText($fc + '.tmp', ('{"comando": "pausa", "ts": "' + $ts + '"}'), (New-Object System.Text.UTF8Encoding($false)))
        Move-Item -LiteralPath ($fc + '.tmp') -Destination $fc -Force
        Scrivi-Log ("Chiesta la pausa al processo di raccolta (PID {0}): {1}" -f $r.Pid, $fc)
      } catch {
        Scrivi-Log ("Impossibile scrivere {0}: {1}" -f $fc, $_.Exception.Message)
      }
      break
    }
  }
  $limite = (Get-Date).AddSeconds(20)
  while ((Get-Date) -lt $limite -and @(Get-ProcessiRaccolta $Cartella).Count) { Start-Sleep -Milliseconds 500 }
  foreach ($r in @(Get-ProcessiRaccolta $Cartella)) {
    try {
      Stop-Process -Id $r.Pid -Force -ErrorAction Stop
      Scrivi-Log ("Processo di raccolta chiuso: {0} (PID {1})" -f $r.Nome, $r.Pid)
    } catch {
      Scrivi-Log ("Impossibile chiudere il processo di raccolta {0} (PID {1}): {2}" -f $r.Nome, $r.Pid, $_.Exception.Message)
    }
  }
  if (-not @(Get-ProcessiRaccolta $Cartella).Count) { Scrivi-Log "Processo di raccolta fermato." }
}

try { "--- disinstalla Rendiconto SW ---" | Set-Content -LiteralPath $log -Encoding UTF8 } catch {}
Scrivi-Log "Disinstallazione di Rendiconto SW…"

if (-not $env:LOCALAPPDATA) { Esci-Con 1 "LOCALAPPDATA non definita." }
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
    $CartellaDati = Join-Path $parentDest ($leafDest + "_dati")
  }
}
$dati = Get-PercorsoLungo $CartellaDati
$destAtteso = $dest
$daRimuovere = Join-Path $parentDest ($leafDest + ".da_rimuovere")
Scrivi-Log ("Destinazione: {0}" -f $dest)
Scrivi-Log ("Cartella dati: {0}" -f $dati)

# Pulisci residuo di una disinstallazione precedente
if (Test-Path -LiteralPath $daRimuovere) {
  if (Test-EGiunzione $daRimuovere) {
    Scrivi-Log "ATTENZIONE: $daRimuovere è una giunzione/reparse: non la cancello."
  } else {
    Scrivi-Log "Rimozione residuo di disinstallazione precedente: $daRimuovere"
    Remove-Item -LiteralPath $daRimuovere -Recurse -Force -ErrorAction SilentlyContinue
  }
}

if (Test-Path -LiteralPath $dest) {
  if (Test-EGiunzione $dest) {
    Esci-Con 1 ("{0} è un collegamento/giunzione: non lo cancello." -f $dest)
  }
  $pieno = Get-PercorsoLungo (Get-Item -LiteralPath $dest).FullName
  if (-not $pieno.Equals($destAtteso, [System.StringComparison]::OrdinalIgnoreCase)) {
    Esci-Con 1 ("Destinazione inattesa: {0} (atteso {1})." -f $pieno, $destAtteso)
  }
}

# Processi: prima il processo di raccolta (si ferma da solo), poi gli altri
Stop-Raccolta $dest @($dati, $datiDefault)
$proc = @(Get-ProcessiCartella $dest)
$app = @($proc | Where-Object { $_.Tipo -eq 'app' })
$terzi = @($proc | Where-Object { $_.Tipo -eq 'terzi' })

if ($app.Count) {
  $elenco = ($app | ForEach-Object { "{0} (PID {1})" -f $_.Nome, $_.Pid }) -join ', '
  Scrivi-Log ("Processi dell'applicazione in esecuzione: {0}" -f $elenco)
  if (-not $Forza) {
    if (-not (Conferma-Si "Chiudo i processi di Rendiconto SW nella cartella di installazione? [s/N]")) {
      Esci-Con 20 ("Disinstallazione annullata: Rendiconto SW è ancora aperto ({0}). Chiudilo e rilancia, oppure rispondi «s» per chiuderlo." -f $elenco)
    }
  }
  $chiusi = Stop-ProcessiPropri $dest
  if ($chiusi.Count) {
    Scrivi-Log ("Chiusi: {0}" -f ($chiusi -join ', '))
    Start-Sleep -Seconds 1
  }
}

if ($terzi.Count -or @(Get-ProcessiCartella $dest | Where-Object { $_.Tipo -eq 'terzi' }).Count) {
  $terzi = @(Get-ProcessiCartella $dest | Where-Object { $_.Tipo -eq 'terzi' })
  if ($terzi.Count) {
    $elenco = ($terzi | ForEach-Object { "{0} (PID {1})" -f $_.Nome, $_.Pid }) -join ', '
    Scrivi-Log ("Programmi di terzi che usano file della cartella (NON verranno chiusi): {0}" -f $elenco)
    Scrivi-Log "Chiudili a mano e rilancia la disinstallazione."
    if (-not $Forza) {
      if (-not (Conferma-Si "Hai chiuso i programmi elencati e vuoi riprovare? [s/N]")) {
        Esci-Con 20 ("La disinstallazione non è completata: chiudi {0} e rilancia." -f $elenco)
      }
    }
  }
}

# Test atomico: rinomina (fallisce se handle aperti)
$rinominata = $null
if (Test-Path -LiteralPath $dest) {
  try {
    if (Test-Path -LiteralPath $daRimuovere) {
      Remove-Item -LiteralPath $daRimuovere -Recurse -Force -ErrorAction SilentlyContinue
    }
    Rename-Item -LiteralPath $dest -NewName ($leafDest + ".da_rimuovere") -ErrorAction Stop
    $rinominata = $daRimuovere
    Scrivi-Log ("Cartella rinominata (nessun file in uso rilevato): {0}" -f ($leafDest + ".da_rimuovere"))
  } catch {
    $ancora = @(Get-ProcessiCartella $dest)
    if (-not $ancora.Count) {
      $ancora = @(Get-ProcessiBloccanti $dest)
    } else {
      # integra eventuali bloccanti non già elencati (handle aperti)
      $bloc = @(Get-ProcessiBloccanti $dest)
      foreach ($b in $bloc) {
        if (-not ($ancora | Where-Object { $_.Pid -eq $b.Pid })) { $ancora += $b }
      }
    }
    $det = if ($ancora.Count) {
      ($ancora | ForEach-Object { "{0}/{1} (PID {2})" -f $_.Tipo, $_.Nome, $_.Pid }) -join ', '
    } else { "nessun processo elencabile (handle di terzi o file bloccati)" }
    Scrivi-Log ("Processi che bloccano la cartella (NON chiusi se terzi): {0}" -f $det)
    Esci-Con 20 ("Impossibile liberare la cartella: {0}. Dettaglio: {1}" -f $det, $_.Exception.Message)
  }
}

# Cancellazione con ritenti
$bersaglio = if ($rinominata) { $rinominata } else { $null }
$ok = $true
$resti = @()
if ($bersaglio -and (Test-Path -LiteralPath $bersaglio)) {
  $ok = $false
  $ultimo = $null
  for ($t = 1; $t -le 3; $t++) {
    try {
      Remove-Item -LiteralPath $bersaglio -Recurse -Force -ErrorAction Stop
      if (-not (Test-Path -LiteralPath $bersaglio)) { $ok = $true; break }
    } catch {
      $ultimo = $_
      Scrivi-Log ("Tentativo {0}/3: {1}" -f $t, $_.Exception.Message)
      Stop-ProcessiPropri $bersaglio | Out-Null
      Start-Sleep -Seconds 2
    }
  }
  if (-not $ok) {
    if (Test-Path -LiteralPath $bersaglio) {
      $resti = @(Get-ChildItem -LiteralPath $bersaglio -Recurse -Force -ErrorAction SilentlyContinue |
        Select-Object -First 20 | ForEach-Object { $_.FullName })
    }
    Scrivi-Log "DISINSTALLAZIONE INCOMPLETA: restano file nella cartella rinominata."
    foreach ($r in $resti) { Scrivi-Log ("  resta: {0}" -f $r) }
    if ($ultimo) { Scrivi-Log ("Dettaglio: {0}" -f $ultimo.Exception.Message) }
    Scrivi-Log "Chiudi Acrobat/Edge/altro che usa DLL dalla cartella, poi rilancia disinstalla.ps1."
    $script:CodiceUscita = 30
  }
}

# Host browser e Uninstall solo se cartella sparita (o non c'era)
$cartellaSparita = -not (Test-Path -LiteralPath $dest) -and -not (Test-Path -LiteralPath $daRimuovere)
if ($cartellaSparita -or $ok) {
  Rimuovi-HostBrowserSeNostri $destAtteso
  Rimuovi-VoceDisinstalla
}

# Collegamenti PER ULTIMI e solo se ok
if ($ok -and $cartellaSparita) {
  Rimuovi-CollegamentiPerBersaglio $destAtteso
} elseif ($ok -and -not (Test-Path -LiteralPath $dest)) {
  Rimuovi-CollegamentiPerBersaglio $destAtteso
}

# Cache AI (sempre, è ricreabile)
Remove-Item -LiteralPath (Join-Path $dati "cache_ai") -Recurse -Force -ErrorAction SilentlyContinue

# Dati utente: default CONSERVA; -RimuoviDati = conferma per categoria; mai PDF in Documenti
if ($RimuoviDati) {
  Scrivi-Log "Rimozione dati richiesta (-RimuoviDati). I PDF in Documenti\Rendiconti lavoro agile NON vengono toccati."
  if (-not (Test-Path -LiteralPath $dati)) {
    Scrivi-Log "Nessuna cartella dati da rimuovere."
  } else {
    $categorie = [ordered]@{
      'Giornate e resoconti sigillati (giorni, finali, revisione)' = @('giorni', 'finali', 'revisione')
      'Stato dell''app e registro di lavoro (stato, raw, diagnostica, log)' = @('stato', 'raw', 'diagnostica', 'log')
      'Chiave di firma di questa postazione (chiave)' = @('chiave')
    }
    foreach ($c in $categorie.GetEnumerator()) {
      $bytes = [long]0
      $presenti = @()
      foreach ($s in $c.Value) {
        $p = Join-Path $dati $s
        if (Test-Path -LiteralPath $p) {
          $presenti += $s
          Get-ChildItem -LiteralPath $p -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object { $bytes += $_.Length }
        }
      }
      if (-not $presenti.Count) {
        Scrivi-Log ("Categoria assente: {0}" -f $c.Key)
        continue
      }
      $mb = [math]::Round($bytes / 1MB, 2)
      Scrivi-Log ("Categoria «{0}»: cartelle {1}, circa {2} MB" -f $c.Key, ($presenti -join ', '), $mb)
      if (Conferma-Si ("Eliminare «{0}»? [s/N]" -f $c.Key)) {
        foreach ($s in $presenti) {
          Remove-Item -LiteralPath (Join-Path $dati $s) -Recurse -Force -ErrorAction SilentlyContinue
          Scrivi-Log ("  eliminata: {0}" -f $s)
        }
      } else {
        Scrivi-Log ("  conservata: {0}" -f $c.Key)
      }
    }
    Scrivi-Log "Non vengono toccati: servizi.json, Collector/PoC residui, PDF in Documenti."
  }
}

# Riepilogo
$restaProg = @()
if (Test-Path -LiteralPath $dest) { $restaProg += $dest }
if (Test-Path -LiteralPath $daRimuovere) { $restaProg += $daRimuovere }
Scrivi-Log "--- riepilogo ---"
if ($restaProg.Count -eq 0) {
  Scrivi-Log "Programma: rimosso."
} else {
  Scrivi-Log ("Programma: restano {0}" -f ($restaProg -join ', '))
}
Scrivi-Log ("Dati utente ({0}): {1}" -f $dati, $(if (Test-Path -LiteralPath $dati) { 'presenti (default: conservati)' } else { 'assenti' }))
Scrivi-Log "PDF in Documenti: non toccati."
if ($script:CodiceUscita -eq 0 -and $restaProg.Count -eq 0) {
  Scrivi-Log "Rendiconto SW disinstallato."
  Esci-Con 0 $null
} elseif ($script:CodiceUscita -eq 30 -or $restaProg.Count) {
  Esci-Con 30 "Disinstallazione incompleta: vedi elenco sopra."
} else {
  Esci-Con $script:CodiceUscita $null
}
