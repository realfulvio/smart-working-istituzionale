; Rendiconto SW 4.3.0 — Setup guidato (Inno Setup 6, lingua italiana, per utente, nessun diritto di amministratore).
; Smart Working Istituzionale
;
; Compilazione (vedi compila_setup.ps1, che prima verifica SHA256SUMS.txt e trova/installa ISCC):
;   ISCC.exe /DPacchetto="C:\Users\...\Downloads\BONIFICA" [/DSpazioExtra=<byte>] [/DDividi=1] /O<cartella> RendicontoSW.iss
;
; SCELTA TECNICA (vedi LEGGIMI_SETUP.md): il Setup NON reimplementa l'installazione. Estrae il pacchetto collaudato
; (stessa cartella di prepara_alfa.ps1: app\, ai\, licenze\, installa.ps1, disinstalla.ps1, SHA256SUMS.txt, …) in una
; cartella temporanea ed esegue, nascosto, installa.ps1 del pacchetto (verifica SHA-256, rifiuto con app aperta = 20,
; staging + scambio con rollback, collegamenti, cartella dati separata). Mostra un messaggio in italiano per ogni codice
; d'uscita (0/10/20/40/50/1). Se il codice non è 0 installa.ps1 ha già lasciato tutto com'era; il Setup non crea la voce
; «App installate», toglie i propri file unins000.* (se nuovi), mostra «Installazione non completata» e termina con lo
; stesso codice (vedi GetCustomSetupExitCode). NB: Abort in AfterInstall NON annulla l'installazione di Inno (provato).
; La disinstallazione è quella di Inno («App installate» o unins000.exe) che esegue, nascosto, disinstalla.ps1
; (codici 0/20/30/1; con 20/30/1 la voce resta per poter riprovare); alla fine chiede, con risposta predefinita «No»,
; se eliminare anche i resoconti salvati (disinstalla.ps1 -RimuoviDati -Forza; i PDF in Documenti non si toccano).
; Una sola voce in «App installate»: dopo l'installazione il Setup toglie la voce HKCU «RendicontoSW» scritta da
; installa.ps1 (solo se punta alla stessa cartella) e resta quella di Inno.

#if Ver < EncodeVer(6, 4, 0)
  #error Serve Inno Setup 6.4 o successivo (consigliato 6.7.3: winget install --id JRSoftware.InnoSetup -e --scope user)
#endif
#define AppNome "Rendiconto SW"
#ifndef NomeEnte
  #define NomeEnte "Il tuo Ente"
#endif
#define AppVer "5.0.0"
#ifndef Immagini
  #define Immagini SourcePath
#endif

#ifndef Pacchetto
  #error Indicare la cartella del pacchetto: ISCC /DPacchetto="C:\...\BONIFICA" RendicontoSW.iss
#endif
#if !FileExists(AddBackslash(Pacchetto) + "installa.ps1")
  #error Nel pacchetto manca installa.ps1
#endif
#if !FileExists(AddBackslash(Pacchetto) + "disinstalla.ps1")
  #error Nel pacchetto manca disinstalla.ps1
#endif
#if !FileExists(AddBackslash(Pacchetto) + "SHA256SUMS.txt")
  #error Nel pacchetto manca SHA256SUMS.txt
#endif
#if !FileExists(AddBackslash(Pacchetto) + "app\RendicontoSW.exe")
  #error Nel pacchetto manca app\RendicontoSW.exe
#endif
#ifndef SpazioExtra
  #define SpazioExtra "0"
#endif
#ifndef Dividi
  #define Dividi "0"
#endif

[Setup]
AppId={{FC51784D-B044-4431-8137-2EF754774F4B}
AppName={#AppNome}
AppVersion={#AppVer}
AppVerName={#AppNome} {#AppVer}
AppPublisher={#NomeEnte} (sviluppo)
AppCopyright=© 2026 Luca Accorsi · EUPL-1.2
AppComments=Resoconto della giornata di lavoro agile. Smart Working Istituzionale.
VersionInfoVersion={#AppVer}.0
VersionInfoCompany={#NomeEnte}
VersionInfoDescription=Installazione di {#AppNome} {#AppVer}
VersionInfoProductName={#AppNome}
VersionInfoProductVersion={#AppVer}
; Per utente, senza amministratore, stessa destinazione di installa.ps1
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\RendicontoSW
; Sempre la cartella predefinita (o quella di /DIR=): mai quella di un'installazione di prova precedente
UsePreviousAppDir=no
DisableDirPage=yes
DisableProgramGroupPage=yes
; Benvenuto → Informativa breve → «Installa» → Fine (niente pagina «Pronto»: il pulsante diventa «Installa»)
DisableReadyPage=yes
DisableWelcomePage=no
InfoBeforeFile=informativa_breve.rtf
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; File del disinstallatore FUORI dalla cartella del programma: installa.ps1 sostituisce l'intera cartella
; (staging + scambio) e disinstalla.ps1 la rinomina e la elimina.
UninstallFilesDir={app}_setup
UninstallDisplayName={#AppNome}
UninstallDisplayIcon={app}\RendicontoSW.exe
; Voce «App installate» solo se installa.ps1 è terminato con 0: CreateUninstallRegKey è valutata da Inno dopo [Files],
; quindi dopo AfterInstall: EseguiInstalla (verificato con il log del Setup). Uninstallable invece è valutata PRIMA di
; [Files]: resta yes e, se installa.ps1 rifiuta su un computer senza installazione precedente del Setup, i file
; unins000.* appena creati si eliminano in CurStepChanged(ssPostInstall).
Uninstallable=yes
CreateUninstallRegKey=VoceUninstall
; Il Setup non sostituisce file nella cartella del programma (lo fa installa.ps1): niente Restart Manager di Inno,
; il controllo dell'app aperta è in PrepareToInstall (per percorso) e di nuovo in installa.ps1 (codice 20).
CloseApplications=no
RestartApplications=no
SetupMutex=RendicontoSW_Setup_{#AppVer}
SetupLogging=yes
UninstallLogging=yes
ShowLanguageDialog=no
WizardStyle=modern
WizardImageFile={#Immagini}\wizard_100.bmp,{#Immagini}\wizard_150.bmp,{#Immagini}\wizard_200.bmp
WizardSmallImageFile={#Immagini}\wizard_piccola_100.bmp,{#Immagini}\wizard_piccola_150.bmp,{#Immagini}\wizard_piccola_200.bmp
SetupIconFile=..\..\..\applicazione\assets\rendiconto.ico
OutputBaseFilename=Setup_RendicontoSW_{#AppVer}
; Compressione: LZMA2 per file (il modello GGUF è già compresso: lo «solid» allunga solo i tempi).
; Un unico Setup.exe finché il compresso resta sotto 4,2 GB (pacchetto attuale ≈ 1,4 GB); /DDividi=1 per i file setup-*.bin.
Compression=lzma2/max
SolidCompression=no
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=2
#if Dividi == "1"
DiskSpanning=yes
DiskSliceSize=max
#else
DiskSpanning=no
#endif
; Spazio per la copia di staging di installa.ps1 (calcolato da compila_setup.ps1: pacchetto × 1,3)
ExtraDiskSpaceRequired={#SpazioExtra}

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[Messages]
SetupWindowTitle=Installazione - %1
WelcomeLabel1=Benvenuto nell'installazione di Rendiconto SW
WelcomeLabel2=Rendiconto SW {#AppVer} ti aiuta a preparare il resoconto della giornata di lavoro agile.%n%nL'installazione è solo per il tuo utente e non richiede diritti di amministratore. Se Rendiconto SW è aperto, chiudilo prima di proseguire (con una giornata in corso premi prima «Pausa»).%n%nNella pagina successiva trovi, in breve, che cosa registra l'app e che cosa non registra mai.
ClickNext=Premi «Avanti» per continuare oppure «Annulla» per uscire.
WizardInfoBefore=Informativa breve
InfoBeforeLabel=Che cosa registra Rendiconto SW e che cosa non registra mai.
InfoBeforeClickLabel=Quando sei pronto, premi «Installa».
WizardInstalling=Installazione in corso
InstallingLabel=Attendi: il Setup estrae il pacchetto, ne verifica le impronte SHA-256 e installa Rendiconto SW.
FinishedHeadingLabel=Rendiconto SW è installato
FinishedLabelNoIcons=Rendiconto SW {#AppVer} è installato per il tuo utente.%n%nLo trovi nel menu Start come «Resoconto lavoro agile»; il verificatore come «Verifica resoconto».
FinishedLabel=Rendiconto SW {#AppVer} è installato per il tuo utente.%n%nLo trovi nel menu Start come «Resoconto lavoro agile»; il verificatore come «Verifica resoconto».
ClickFinish=Premi «Fine» per chiudere.
SetupAborted=L'installazione non è stata completata e il computer è rimasto com'era.%n%nLeggi il messaggio precedente; se il problema persiste avvisa i Sistemi Informativi.
ConfirmUninstall=Vuoi disinstallare %1?%n%nI resoconti salvati restano sul computer: alla fine ti verrà chiesto se vuoi eliminarli anche.
UninstallStatusLabel=Attendi: rimozione di %1 in corso.
UninstalledAll=%1 è stato disinstallato.

[Files]
; Tutto il pacchetto in una cartella temporanea (eliminata alla fine, anche se il Setup viene annullato). SHA256SUMS.txt
; per ultimo: subito dopo la sua estrazione parte installa.ps1 (AfterInstall), prima che Inno decida se creare la voce
; «App installate» (CreateUninstallRegKey=VoceUninstall).
Source: "{#Pacchetto}\*"; DestDir: "{tmp}\pacchetto"; Excludes: "\SHA256SUMS.txt"; Flags: recursesubdirs createallsubdirs ignoreversion deleteafterinstall
Source: "{#Pacchetto}\SHA256SUMS.txt"; DestDir: "{tmp}\pacchetto"; Flags: ignoreversion deleteafterinstall; AfterInstall: EseguiInstalla

[Run]
Filename: "{app}\RendicontoSW.exe"; WorkingDir: "{userdocs}"; Description: "Avvia Rendiconto SW"; Flags: postinstall nowait skipifsilent; Check: AppInstallata

[Code]
function GetDriveTypeW(lpRootPathName: String): Cardinal;
  external 'GetDriveTypeW@kernel32.dll stdcall';

const
  CHIAVE_LEGACY = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\RendicontoSW';
  A_CAPO = #13#10;

var
  CopiaDisinstalla: String;
  CodiceInstalla: Integer;      { -1 = installa.ps1 non ancora eseguito }
  EsitoInstalla: String;        { messaggio mostrato all'utente se l'installazione non è riuscita }
  SetupGiaPresente: Boolean;    { c'era già un disinstallatore del Setup (aggiornamento/reinstallazione) }

function PowerShellExe: String;
begin
  // In modalità 64 bit {sys} è la System32 nativa (PowerShell 5.1 a 64 bit, come nel collaudo di installa.ps1)
  Result := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
end;

function SetEnvironmentVariable(lpName, lpValue: String): Boolean;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

{ Il Setup lanciato da PowerShell 7 ne eredita il PSModulePath: Windows PowerShell 5.1 caricherebbe i moduli di PS 7
  (es. Microsoft.PowerShell.Security) e installa.ps1 / disinstalla.ps1 uscirebbero con 1. Prima di ogni Exec si
  rimette il PSModulePath standard di Windows PowerShell 5.1 ; vale solo per questo processo e per i suoi figli. -NoProfile esclude i profili dell'utente. }
procedure PreparaAmbientePowerShell;
var
  Valore: String;
begin
  try
    Valore := ExpandConstant('{userdocs}') + '\WindowsPowerShell\Modules;' +
              ExpandConstant('{commonpf64}') + '\WindowsPowerShell\Modules;' +
              ExpandConstant('{sys}') + '\WindowsPowerShell\v1.0\Modules';
    if SetEnvironmentVariable('PSModulePath', Valore) then
      Log('PSModulePath per Windows PowerShell 5.1: ' + Valore)
    else
      Log('PSModulePath non impostato (errore ' + IntToStr(DLLGetLastError) + '): si prosegue con quello ereditato');
  except
    Log('PSModulePath non impostato: ' + GetExceptionMessage);
  end;
end;

function CartellaApp: String;
begin
  Result := RemoveBackslashUnlessRoot(ExpandConstant('{app}'));
end;

{ Stessa regola di installa.ps1 / disinstalla.ps1: cartella predefinita → dati in %LOCALAPPDATA%\RendicontoSW;
  qualunque altra cartella (prove con /DIR=) → «<cartella>_dati» accanto, così i dati reali non si toccano. }
function CartellaDati: String;
begin
  if SameText(CartellaApp, ExpandConstant('{localappdata}\Programs\RendicontoSW')) then
    Result := ExpandConstant('{localappdata}\RendicontoSW')
  else
    Result := CartellaApp + '_dati';
end;

function InstallaRiuscita: Boolean;
begin
  Result := (CodiceInstalla = 0);
end;

function VoceUninstall: Boolean;
begin
  Result := (CodiceInstalla = 0);
end;

function AppInstallata: Boolean;
begin
  Result := InstallaRiuscita and FileExists(CartellaApp + '\RendicontoSW.exe');
end;

function InitializeSetup: Boolean;
begin
  CodiceInstalla := -1;
  EsitoInstalla := '';
  Result := True;
end;

function Silenzioso: Boolean;
begin
  if IsUninstaller then
    Result := UninstallSilent
  else
    Result := WizardSilent;
end;

{ Processi il cui eseguibile sta nella cartella del programma (RendicontoSW, VerificaRendiconto, llama-server).
  Il processo di raccolta della modalità collector («RendicontoSW.exe _esegui», attivo a giornata avviata) in
  installazione è indicato come tale; in disinstallazione non blocca: lo ferma disinstalla.ps1. }
function ProcessiAperti: String;
var
  Locator, Servizio, Insieme, Oggetto: Variant;
  I, Pid: Integer;
  Radice, Exe, Nome, Riga: String;
  Raccolta: Boolean;
begin
  Result := '';
  Radice := Lowercase(AddBackslash(CartellaApp));
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Servizio := Locator.ConnectServer('.', 'root\CIMV2');
    Insieme := Servizio.ExecQuery('SELECT Name, ProcessId, ExecutablePath, CommandLine FROM Win32_Process');
    for I := 0 to Insieme.Count - 1 do
    begin
      Oggetto := Insieme.ItemIndex(I);
      if not (VarIsNull(Oggetto.ExecutablePath) or VarIsEmpty(Oggetto.ExecutablePath)) then
      begin
        Exe := Oggetto.ExecutablePath;
        if Pos(Radice, Lowercase(Exe)) = 1 then
        begin
          Nome := Oggetto.Name;
          Pid := Oggetto.ProcessId;
          Riga := '';
          if not (VarIsNull(Oggetto.CommandLine) or VarIsEmpty(Oggetto.CommandLine)) then
            Riga := Oggetto.CommandLine;
          Raccolta := Pos(' _esegui ', Riga + ' ') > 0;
          if Raccolta and IsUninstaller then
            Log('Processo di raccolta ' + Nome + ' (PID ' + IntToStr(Pid) + '): lo ferma disinstalla.ps1')
          else
          begin
            if Raccolta then
              Nome := Nome + ', raccolta attività della giornata in corso';
            if Result <> '' then
              Result := Result + '; ';
            Result := Result + Nome + ' (PID ' + IntToStr(Pid) + ')';
          end;
        end;
      end;
    end;
  except
    { Se WMI non risponde decide installa.ps1 / disinstalla.ps1 (codice 20) }
    Log('Controllo dei processi non disponibile: ' + GetExceptionMessage);
  end;
end;

function AppChiusaOppureAnnulla(const Esito: String): Boolean;
var
  Aperti: String;
begin
  Result := True;
  repeat
    Aperti := ProcessiAperti;
    if Aperti = '' then
      Exit;
    Log('Rendiconto SW è aperto: ' + Aperti);
    if Silenzioso then
    begin
      Result := False;
      Exit;
    end;
    if Pos('raccolta attività', Aperti) > 0 then
      Aperti := Aperti + '.' + A_CAPO + A_CAPO + 'La giornata è in corso: in Rendiconto SW premi «Pausa» (o «Chiudi ' +
                'giornata») per fermare la raccolta';
    if MsgBox('Rendiconto SW è aperto: ' + Aperti + '.' + A_CAPO + A_CAPO +
              'Chiudi Rendiconto SW (e il verificatore, se aperto), poi premi «Riprova».' + A_CAPO +
              'Con «Annulla» ' + Esito, mbError, MB_RETRYCANCEL) <> IDRETRY then
    begin
      Result := False;
      Exit;
    end;
  until False;
end;

{ Ultimo log rsw_<nome>_AAAAMMGG_HHMMSS.log in %TEMP% (il nome ordina per data). }
function UltimoLog(const Prefisso: String): String;
var
  R: TFindRec;
  Migliore: String;
begin
  Result := '';
  Migliore := '';
  if FindFirst(AddBackslash(GetEnv('TEMP')) + Prefisso + '*.log', R) then
  begin
    try
      repeat
        if CompareText(R.Name, Migliore) > 0 then
          Migliore := R.Name;
      until not FindNext(R);
    finally
      FindClose(R);
    end;
  end;
  if Migliore <> '' then
    Result := AddBackslash(GetEnv('TEMP')) + Migliore;
end;

{ Copia il log dello script nel log del Setup e restituisce il motivo (la riga prima di «Log: …»). }
function DettaglioDalLog(const FileLog: String): String;
var
  Righe: TArrayOfString;
  I: Integer;
  R: String;
begin
  Result := '';
  if (FileLog = '') or not LoadStringsFromFile(FileLog, Righe) then
    Exit;
  for I := 0 to GetArrayLength(Righe) - 1 do
  begin
    R := Righe[I];
    Log('  | ' + R);
    if (I > 0) and (Pos('  Log: ', R) = 9) then
      Result := Copy(Righe[I - 1], 11, 10000);
  end;
  if (Result = '') and (GetArrayLength(Righe) > 0) then
    Result := Copy(Righe[GetArrayLength(Righe) - 1], 11, 10000);
end;

function MessaggioInstalla(Codice: Integer; LogPresente: Boolean): String;
begin
  case Codice of
    10: Result := 'Il controllo di integrità non è riuscito: alcuni file del pacchetto non corrispondono alle impronte ' +
                  'SHA-256 (SHA256SUMS.txt). Non è stato installato nulla. Non usare questo Setup e avvisa i Sistemi Informativi.';
    20: Result := 'Rendiconto SW (o il verificatore, o l''assistente locale, o la raccolta di una giornata in corso) ' +
                  'è aperto. Chiudilo (con una giornata in corso premi prima «Pausa») e avvia di nuovo ' +
                  'l''installazione. Non è stato modificato nulla.';
    40: Result := 'Spazio su disco insufficiente: durante l''installazione servono circa il doppio della dimensione del ' +
                  'programma (circa 3 GB liberi). Libera spazio e riprova. Non è stato modificato nulla.';
    50: Result := 'Sul computer è già installata una versione di Rendiconto SW più recente di questa. ' +
                  'L''installazione è stata annullata e la versione presente resta com''è.';
  else
    if not LogPresente then
      Result := 'Windows PowerShell non ha eseguito lo script di installazione (criteri di esecuzione o blocco di ' +
                'sicurezza). Non è stato modificato nulla. Non aggirare il blocco: avvisa i Sistemi Informativi.'
    else
      Result := 'L''installazione non è riuscita per un errore imprevisto; la versione precedente, se c''era, è stata ' +
                'ripristinata. Avvisa i Sistemi Informativi allegando il registro indicato qui sotto.';
  end;
end;

{ AfterInstall dell'ultimo file del pacchetto: esegue installa.ps1 del pacchetto, nascosto. }
procedure EseguiInstalla;
var
  Origine, Parametri, LogPrima, LogDopo, Dettaglio, Msg: String;
  Codice: Integer;
  Avviato: Boolean;
begin
  Origine := ExpandConstant('{tmp}\pacchetto');
  Parametri := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + Origine + '\installa.ps1"' +
               ' -Origine "' + Origine + '" -Destinazione "' + CartellaApp + '" -Reinstalla';
  WizardForm.StatusLabel.Caption := 'Verifica delle impronte SHA-256 e installazione di Rendiconto SW…';
  WizardForm.FilenameLabel.Caption := 'Può richiedere alcuni minuti: non chiudere questa finestra.';
  WizardForm.ProgressGauge.Style := npbstMarquee;
  WizardForm.CancelButton.Enabled := False;
  LogPrima := UltimoLog('rsw_installa_');
  PreparaAmbientePowerShell;
  Log('Esecuzione di installa.ps1: ' + PowerShellExe + ' ' + Parametri);
  try
    Avviato := Exec(PowerShellExe, Parametri, Origine, SW_HIDE, ewWaitUntilTerminated, Codice);
  finally
    WizardForm.ProgressGauge.Style := npbstNormal;
    WizardForm.CancelButton.Enabled := True;
  end;
  if not Avviato then
  begin
    CodiceInstalla := 99;
    EsitoInstalla := 'Impossibile avviare Windows PowerShell (' + SysErrorMessage(Codice) + '). Non è stato modificato ' +
                     'nulla. Non aggirare il blocco: avvisa i Sistemi Informativi.';
    Log('Installazione non riuscita: ' + EsitoInstalla);
    SuppressibleMsgBox(EsitoInstalla, mbCriticalError, MB_OK, IDOK);
    Exit;
  end;
  LogDopo := UltimoLog('rsw_installa_');
  if CompareText(LogDopo, LogPrima) = 0 then
    LogDopo := '';
  Log('installa.ps1: codice di uscita ' + IntToStr(Codice) + '; registro: ' + LogDopo);
  Dettaglio := DettaglioDalLog(LogDopo);
  CodiceInstalla := Codice;
  if Codice <> 0 then
  begin
    EsitoInstalla := MessaggioInstalla(Codice, LogDopo <> '');
    Msg := EsitoInstalla;
    if Dettaglio <> '' then
      Msg := Msg + A_CAPO + A_CAPO + 'Dettaglio: ' + Dettaglio;
    if LogDopo <> '' then
      Msg := Msg + A_CAPO + 'Registro: ' + LogDopo;
    Msg := Msg + A_CAPO + '(codice ' + IntToStr(Codice) + ')';
    Log('Installazione non riuscita: ' + Msg);
    SuppressibleMsgBox(Msg, mbCriticalError, MB_OK, IDOK);
  end;
end;

procedure AggiungiPoweredBy(Modulo: TForm);
var
  L: TNewStaticText;
begin
  L := TNewStaticText.Create(Modulo);
  L.Parent := Modulo;
  L.Caption := 'powered by Accorsi Luca';
  L.Font.Size := 7;
  L.Font.Color := $00887C6B;   { #6b7c88 come nei mockup approvati }
  L.Left := Modulo.ClientWidth - L.Width - ScaleX(10);
  L.Top := Modulo.ClientHeight - L.Height - ScaleY(2);
  L.Anchors := [akRight, akBottom];
end;

procedure InitializeWizard;
begin
  { Pulsanti un poco più in alto per lasciare spazio a «powered by Accorsi Luca» in basso a destra (mockup 08a) }
  WizardForm.BackButton.Top := WizardForm.BackButton.Top - ScaleY(5);
  WizardForm.NextButton.Top := WizardForm.NextButton.Top - ScaleY(5);
  WizardForm.CancelButton.Top := WizardForm.CancelButton.Top - ScaleY(5);
  AggiungiPoweredBy(WizardForm);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  { Senza la pagina «Pronto» l'ultima pagina prima dell'installazione è l'informativa: il pulsante diventa «Installa» }
  if CurPageID = wpInfoBefore then
    WizardForm.NextButton.Caption := SetupMessage(msgButtonInstall)
  else if CurPageID = wpFinished then
  begin
    WizardForm.NextButton.Caption := SetupMessage(msgButtonFinish);
    if not InstallaRiuscita then
    begin
      WizardForm.FinishedHeadingLabel.Caption := 'Installazione non completata';
      WizardForm.FinishedLabel.Caption := 'Rendiconto SW non è stato installato e il computer è rimasto com''era.' +
        A_CAPO + A_CAPO + EsitoInstalla + A_CAPO + A_CAPO + 'Codice: ' + IntToStr(CodiceInstalla) +
        '. Il registro dettagliato è in %TEMP% (rsw_installa_*.log e Setup Log *.txt).';
      WizardForm.RunList.Visible := False;
    end;
  end
  else
    WizardForm.NextButton.Caption := SetupMessage(msgButtonNext);
end;

procedure InitializeUninstallProgressForm;
begin
  UninstallProgressForm.CancelButton.Top := UninstallProgressForm.CancelButton.Top - ScaleY(5);
  AggiungiPoweredBy(UninstallProgressForm);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  App: String;
begin
  Result := '';
  App := CartellaApp;
  if (Copy(App, 1, 2) = '\\') or (GetDriveTypeW(ExtractFileDrive(App) + '\') = 4) then   { 4 = DRIVE_REMOTE }
  begin
    Result := 'Cartella di installazione non ammessa: ' + App + ' (niente unità di rete).';
    Exit;
  end;
  if not FileExists(PowerShellExe) then
  begin
    Result := 'Windows PowerShell non trovato (' + PowerShellExe + '): l''installazione non può proseguire. ' +
              'Avvisa i Sistemi Informativi.';
    Exit;
  end;
  SetupGiaPresente := FileExists(CartellaApp + '_setup\unins000.dat');
  if not AppChiusaOppureAnnulla('l''installazione si interrompe senza modificare nulla.') then
    Result := 'Rendiconto SW è aperto: chiudilo e avvia di nuovo l''installazione. Non è stato modificato nulla.';
end;

{ Codice d'uscita del Setup (anche con /SILENT o /VERYSILENT): 0 installato; altrimenti lo stesso codice di
  installa.ps1 (10 impronte, 20 app aperta, 40 spazio, 50 versione più recente già installata); 91 = errore generico
  dello script (installa.ps1 ha restituito 1); 99 = PowerShell non avviato o codice inatteso. I codici 1–8 restano
  quelli di Inno per i suoi errori (es. 2 = annullato dall'utente prima dell'installazione). }
function GetCustomSetupExitCode: Integer;
begin
  case CodiceInstalla of
    -1, 0: Result := 0;
    10, 20, 40, 50: Result := CodiceInstalla;
    1: Result := 91;
  else
    Result := 99;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Posizione: String;
begin
  if (CurStep = ssPostInstall) and not InstallaRiuscita then
  begin
    { Inno può aver creato la cartella (vuota) del programma: la togliamo solo se è vuota }
    if RemoveDir(CartellaApp) then
      Log('Rimossa la cartella vuota ' + CartellaApp);
    if not SetupGiaPresente then
    begin
      DeleteFile(CartellaApp + '_setup\unins000.exe');
      DeleteFile(CartellaApp + '_setup\unins000.dat');
      if RemoveDir(CartellaApp + '_setup') then
        Log('Rimossi i file del disinstallatore appena creati (installazione non riuscita).');
    end;
  end
  else if CurStep = ssPostInstall then
  begin
    { Una sola voce in «App installate»: resta quella del Setup (con unins000.exe). }
    if RegQueryStringValue(HKEY_CURRENT_USER, CHIAVE_LEGACY, 'InstallLocation', Posizione) and
       SameText(RemoveBackslashUnlessRoot(Posizione), CartellaApp) then
    begin
      if RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, CHIAVE_LEGACY) then
        Log('Rimossa la voce HKCU «RendicontoSW» di installa.ps1: resta quella del Setup.')
      else
        Log('Impossibile rimuovere la voce HKCU «RendicontoSW» di installa.ps1.');
    end;
  end;
end;

{ ---------------------------------------------------------------- disinstallazione }

function InitializeUninstall: Boolean;
begin
  Result := AppChiusaOppureAnnulla('la disinstallazione si interrompe senza rimuovere nulla.');
end;

function EseguiDisinstalla(const Extra: String; var Codice: Integer): Boolean;
var
  Parametri: String;
begin
  Parametri := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + CopiaDisinstalla + '"' +
               ' -Destinazione "' + CartellaApp + '"' + Extra;
  PreparaAmbientePowerShell;
  Log('Esecuzione di disinstalla.ps1: ' + PowerShellExe + ' ' + Parametri);
  Result := Exec(PowerShellExe, Parametri, GetTempDir, SW_HIDE, ewWaitUntilTerminated, Codice);
  if Result then
    Log('disinstalla.ps1: codice di uscita ' + IntToStr(Codice))
  else
    Log('disinstalla.ps1 non avviato: ' + SysErrorMessage(Codice));
end;

function MessaggioDisinstalla(Codice: Integer): String;
begin
  case Codice of
    20: Result := 'Rendiconto SW, oppure un altro programma (per esempio Acrobat), sta usando file della cartella ' +
                  'del programma. Chiudilo e ripeti la disinstallazione da «App installate». Non è stato rimosso nulla.';
    30: Result := 'Disinstallazione incompleta: alcuni file non si sono potuti eliminare perché in uso. Chiudi gli ' +
                  'altri programmi (Acrobat, browser…) e ripeti la disinstallazione da «App installate».';
  else
    Result := 'La disinstallazione non è riuscita per un errore imprevisto. Avvisa i Sistemi Informativi ' +
              'allegando il registro indicato qui sotto.';
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Codice: Integer;
  LogPrima, LogDopo, Dettaglio, Msg: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    CopiaDisinstalla := '';
    if not DirExists(CartellaApp) then
    begin
      Log('Cartella del programma assente: rimuovo solo la voce del Setup.');
      Exit;
    end;
    { disinstalla.ps1 rinomina ed elimina la cartella del programma: si esegue da una copia temporanea }
    CopiaDisinstalla := AddBackslash(GetTempDir) + 'rsw_uninst_' + GetDateTimeString('yyyymmddhhnnss', #0, #0) + '.ps1';
    if not CopyFile(CartellaApp + '\disinstalla.ps1', CopiaDisinstalla, False) then
    begin
      Msg := 'Nella cartella del programma manca disinstalla.ps1: disinstallazione interrotta, non è stato rimosso ' +
             'nulla. Avvisa i Sistemi Informativi.';
      Log(Msg);
      if not UninstallSilent then
        MsgBox(Msg, mbCriticalError, MB_OK);
      Abort;
    end;
    UninstallProgressForm.StatusLabel.Caption := 'Rimozione di Rendiconto SW (i tuoi dati restano)…';
    UninstallProgressForm.ProgressBar.Style := npbstMarquee;
    LogPrima := UltimoLog('rsw_disinstalla_');
    if not EseguiDisinstalla('', Codice) then
    begin
      Msg := 'Impossibile avviare Windows PowerShell (' + SysErrorMessage(Codice) + '). Non è stato rimosso nulla.';
      if not UninstallSilent then
        MsgBox(Msg, mbCriticalError, MB_OK);
      DeleteFile(CopiaDisinstalla);
      Abort;
    end;
    UninstallProgressForm.ProgressBar.Style := npbstNormal;
    LogDopo := UltimoLog('rsw_disinstalla_');
    if CompareText(LogDopo, LogPrima) = 0 then
      LogDopo := '';
    Dettaglio := DettaglioDalLog(LogDopo);
    if Codice <> 0 then
    begin
      Msg := MessaggioDisinstalla(Codice);
      if Dettaglio <> '' then
        Msg := Msg + A_CAPO + A_CAPO + 'Dettaglio: ' + Dettaglio;
      if LogDopo <> '' then
        Msg := Msg + A_CAPO + 'Registro: ' + LogDopo;
      Msg := Msg + A_CAPO + '(codice ' + IntToStr(Codice) + ')';
      Log('Disinstallazione interrotta: ' + Msg);
      if not UninstallSilent then
        MsgBox(Msg, mbCriticalError, MB_OK);
      DeleteFile(CopiaDisinstalla);
      { La voce resta in «App installate» per poter riprovare }
      Abort;
    end;
  end
  else if CurUninstallStep = usPostUninstall then
  begin
    if (CopiaDisinstalla <> '') and (not UninstallSilent) and DirExists(CartellaDati) then
    begin
      if MsgBox('Rendiconto SW è stato rimosso.' + A_CAPO + A_CAPO +
                'Vuoi eliminare anche i resoconti salvati?' + A_CAPO + A_CAPO +
                'Verrebbero cancellati definitivamente i dati dell''app in ' + CartellaDati + ': giornate e resoconti ' +
                'sigillati, registro di lavoro e chiave di firma di questa postazione. I PDF in ' +
                'Documenti\Rendiconti lavoro agile NON vengono toccati.' + A_CAPO + A_CAPO +
                'Se non sei sicuro rispondi «No»: i dati restano e, reinstallando, ritrovi tutto.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        if EseguiDisinstalla(' -RimuoviDati -Forza', Codice) and (Codice = 0) then
          Log('Dati dell''app eliminati su richiesta dell''utente.')
        else
          MsgBox('Non è stato possibile eliminare tutti i dati in ' + CartellaDati + ' (codice ' + IntToStr(Codice) +
                 '). Puoi eliminarli a mano.', mbError, MB_OK);
      end
      else
        Log('Dati dell''app conservati (risposta «No»).');
    end;
    if CopiaDisinstalla <> '' then
      DeleteFile(CopiaDisinstalla);
  end;
end;
