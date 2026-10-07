# Setup guidato di Rendiconto SW 5.0.0 (Inno Setup)

Un solo file `Setup_RendicontoSW_5.0.0.exe`: doppio clic, quattro pagine, nessun comando PowerShell da digitare.
Si disinstalla da **Impostazioni › App › App installate** (o con `unins000.exe`). powered by Accorsi Luca.

## File

| File | A cosa serve |
|---|---|
| `RendicontoSW.iss` | script Inno Setup 6 (italiano, per utente, `PrivilegesRequired=lowest`) |
| `compila_setup.ps1` | verifica il pacchetto, trova/installa ISCC, compila, scrive lo SHA-256 |
| `informativa_breve.rtf` | pagina «Informativa breve»: cosa registra la modalità collector (predefinita) solo a giornata avviata / cosa NON registra mai |
| `wizard_*.bmp`, `wizard_piccola_*.bmp` | immagini del wizard (100/150/200 % DPI), token centrali e nome dell'Ente (config/ente.json), segnaposto ENTE, «powered by Accorsi Luca» |
| `genera_immagini.py` | rigenera le BMP (Pillow; Titillium Web da `applicazione/assets`, nome e colori da `config/ente.json`) |
| `anteprime/*.png` | anteprime delle immagini |

## Scelta tecnica: Inno come «guscio» di installa.ps1 / disinstalla.ps1

Il Setup **non reimplementa** l'installazione (principio della minima modifica). Contiene il pacchetto collaudato
(la stessa cartella prodotta da `prepara_alfa.ps1`: `app\`, `ai\`, `licenze\`, `installa.ps1`, `disinstalla.ps1`,
`SHA256SUMS.txt`, `VERSIONE.txt`, …), lo estrae in `{tmp}\pacchetto` ed esegue, a finestra nascosta:

```
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{tmp}\pacchetto\installa.ps1"
               -Origine "{tmp}\pacchetto" -Destinazione "{app}" -Reinstalla
```

Prima di ogni avvio di `powershell.exe` (installazione e disinstallazione) il Setup imposta, solo per sé e per i
processi figli, il `PSModulePath` standard di Windows PowerShell 5.1 (`Documenti\WindowsPowerShell\Modules;
%ProgramFiles%\WindowsPowerShell\Modules;%SystemRoot%\System32\WindowsPowerShell\v1.0\Modules`, riga
`PSModulePath per Windows PowerShell 5.1:` nel log). Motivo: lanciato da PowerShell 7 il Setup ne eredita il
`PSModulePath`, `powershell.exe` 5.1 caricava i moduli di PS 7 e `installa.ps1` usciva con 1 (codice 91 del Setup).
`-NoProfile` esclude i profili.

Così restano invariati e già collaudati: verifica delle impronte SHA-256, rifiuto con app aperta (20),
staging + scambio con rollback, cartella dati separata, collegamenti Start, log `%TEMP%\rsw_installa_*.log`.
La copia nativa di Inno è stata scartata perché avrebbe duplicato (e da ricollaudare) tutta questa logica.

Perché non Inno «puro»: la logica di `installa.ps1` (rollback, regole sulla cartella dati, chiave legacy, collegamenti)
è il punto già collaudato; rifarla in Pascal Script avrebbe significato un nuovo installer da collaudare da zero.

### Codici d'uscita e messaggi

| installa.ps1 | Messaggio del Setup (finestra + pagina «Installazione non completata») | Uscita di Setup.exe |
|---|---|---|
| 0 | pagina «Rendiconto SW è installato», casella «Avvia Rendiconto SW» | 0 |
| 10 | pacchetto danneggiato o incompleto (impronte SHA-256): scaricare di nuovo il Setup | 10 |
| 20 | Rendiconto SW (o verificatore/assistente) aperto: chiuderlo e riprovare | 20 |
| 40 | cartella di destinazione non valida (unità di rete, OneDrive…) | 40 |
| 50 | installazione non riuscita, versione precedente ripristinata | 50 |
| 1 / altro | errore imprevisto (con riga di dettaglio dal log) | 91 / 99 |
| (app aperta prima di iniziare) | «Rendiconto SW è aperto…» (Riprova/Annulla nel wizard) | 7 (solo silenzioso / annullato) |

Con codice ≠ 0 `installa.ps1` ha già lasciato tutto com'era; il Setup **non crea** la voce «App installate»
(`CreateUninstallRegKey` è valutata dopo [Files]), toglie i propri `unins000.*` se nuovi, e termina con il codice
della tabella (`GetCustomSetupExitCode`, valido anche con `/SILENT` e `/VERYSILENT`). Il log di `installa.ps1`
viene copiato nel log del Setup (righe `  | `).

Nota provata sotto wine: `Abort` dentro `AfterInstall` **non** annulla l'installazione di Inno (dà «Errore interno»
e crea comunque la voce): per questo si usa la logica a flag descritta sopra.

### Prima della copia

`PrepareToInstall` rifiuta destinazioni di rete (UNC o unità mappata) e l'assenza di Windows PowerShell; se l'app,
il verificatore o l'assistente sono aperti (controllo WMI sui processi della cartella) chiede «Riprova/Annulla»
(con `/SILENT` o `/VERYSILENT` mostra il messaggio «Rendiconto SW è aperto…» e termina con il codice **7** di Inno,
«preparazione non riuscita», senza toccare nulla; con `/SUPPRESSMSGBOXES` niente messaggio, stesso codice 7).
Anche la disinstallazione, se l'app è aperta, chiede «Riprova/Annulla» (in silenzioso si ferma e la voce resta).

**Processo di raccolta (modalità collector).** A giornata avviata gira `RendicontoSW.exe _esegui` (senza finestra).
In installazione/aggiornamento è indicato come «raccolta attività della giornata in corso» e il messaggio chiede di
premere «Pausa» (o «Chiudi giornata») in Rendiconto SW; `installa.ps1` lo rifiuterebbe comunque con 20. In
disinstallazione **non** blocca: `disinstalla.ps1` gli chiede di fermarsi come con «Pausa» (`stato\comando.json`
nella cartella dati, solo se `stato\demone.json` riporta lo stesso PID), aspetta fino a 20 s e, se serve, lo chiude;
tutto annotato in `%TEMP%\rsw_disinstalla_*.log`. I dati della giornata restano.

### Una sola voce in «App installate»

`installa.ps1` scrive la sua chiave HKCU `…\Uninstall\RendicontoSW`. Dopo un'installazione riuscita il Setup la
toglie **solo se** `InstallLocation` è la stessa cartella; resta la voce di Inno `{FC51784D-B044-4431-8137-2EF754774F4B}_is1`.
I file del disinstallatore (`unins000.exe/.dat`) stanno in `{app}_setup` (es. `…\Programs\RendicontoSW_setup`), fuori
dalla cartella che `installa.ps1` sostituisce a ogni aggiornamento.

### Disinstallazione guidata (i dati restano)

Conferma («I resoconti salvati restano sul computer…») → `disinstalla.ps1 -Destinazione "{app}"` eseguito nascosto
da una copia in `%TEMP%` (codici 0/20/30/1; con 20/30/1 messaggio e la voce resta per poter riprovare) →
domanda facoltativa **«Vuoi eliminare anche i resoconti salvati?»** con **No predefinito**. Solo con «Sì» viene
eseguito `disinstalla.ps1 -RimuoviDati -Forza` (giornate, resoconti sigillati, registro, chiave di firma; i PDF in
Documenti non vengono mai toccati). In modalità silenziosa la domanda non viene posta e i dati restano.

### Cartella dati

Come `installa.ps1`: cartella predefinita `%LOCALAPPDATA%\Programs\RendicontoSW` → dati in `%LOCALAPPDATA%\RendicontoSW`;
con `/DIR=<x>` diverso → dati in `<x>_dati` (utile per il collaudo in sandbox).
**Attenzione nel collaudo**: anche con `/DIR=` `installa.ps1` riscrive i collegamenti Start e la chiave legacy
`RendicontoSW`, e l'AppId è lo stesso dell'installazione reale: prima di provare in sandbox salvare chiave e collegamenti.

## Compressione, dimensioni, DiskSpanning

* `Compression=lzma2/max`, `SolidCompression=no` (il modello GGUF ~1,1 GB è già compresso: la compressione solida
  costerebbe molta RAM e tempo senza guadagno), `LZMAUseSeparateProcess=yes`, `LZMANumBlockThreads=2`.
* Il pacchetto (circa 1,4 GB, con il modello AI-Light) dà un Setup di circa 1,2–1,4 GB: sotto il limite di ~4,2 GB di un exe
  senza DiskSpanning → **un solo file**. `/DDividi=1` (o `compila_setup.ps1 -Dividi`) abilita `DiskSpanning`
  (`Setup.exe` + `Setup-1.bin` … da tenere nella stessa cartella) solo se servisse.
* Durante l'installazione servono temporaneamente circa 3× la dimensione del pacchetto (estrazione in `{tmp}` +
  staging di `installa.ps1`); `compila_setup.ps1` passa `ExtraDiskSpaceRequired` = 1,3 × pacchetto.

## Compilare

```powershell
# Inno Setup 6 per utente (nessun diritto di amministratore), se manca:
winget install --id JRSoftware.InnoSetup -e --scope user
# compilazione (verifica SHA256SUMS.txt, poi ISCC; scrive Setup_RendicontoSW_5.0.0.exe + .sha256)
powershell -NoProfile -ExecutionPolicy Bypass -File tools\pacchetto\setup\compila_setup.ps1 `
    -Pacchetto C:\Users\<utente>\Downloads\PACCHETTO -Uscita C:\Users\<utente>\Downloads\SETUP
```

Codici di `compila_setup.ps1`: 0 ok · 10 pacchetto non integro · 2 ISCC non trovato/non installabile ·
3 compilazione fallita · 1 altro. Opzioni: `-Iscc <percorso>`, `-Dividi`, `-NonInstallareInno`, `-SoloVerifica`.
Richiede Inno Setup ≥ 6.4 (lo script si ferma con un errore chiaro se più vecchio).

## Installare / collaudare da riga di comando (facoltativo)

```
Setup_RendicontoSW_5.0.0.exe                         wizard
Setup_RendicontoSW_5.0.0.exe /SILENT /LOG=<file>     solo barra di avanzamento; codice d'uscita come da tabella
Setup_RendicontoSW_5.0.0.exe /DIR=<cartella>         sandbox (dati in <cartella>_dati, disinstallatore in <cartella>_setup)
<cartella>_setup\unins000.exe [/SILENT]              disinstallazione (silenziosa: i dati restano)
(unins000.exe si copia in %TEMP% e termina subito: la cartella <cartella>_setup sparisce qualche secondo dopo)
```

## Firma e Defender

Il Setup non è firmato. Su postazioni con la regola ASR **C1DB55AB** (protezione avanzata dal ransomware) l'avvio
di un eseguibile non firmato e poco diffuso può essere bloccato: non si aggira, si annota e si chiede ai Sistemi
Informativi l'esclusione o la firma (vedi il README: la firma del codice è un prerequisito).

## Prova di compilazione (Linux)

ISCC 6.7.3 sotto wine 10 su pacchetto finto (PowerShell finto che simula i codici 0/10/20/40/50/1):
compilazione 0 errori / 0 avvisi; provati wizard, installazione silenziosa con tutti i codici, aggiornamento rifiutato
con 20 (versione precedente intatta), reinstallazione, sandbox `/DIR`, disinstallazione con e senza rimozione dati,
disinstallazione rifiutata con 20 (voce conservata), finestra Riprova/Annulla con app aperta.

4.3.0 (06/10/2026), stessa prova: compilazione 0 errori / 0 avvisi; Setup e `unins000.exe` avviati con il
`PSModulePath` di PowerShell 7 → il `powershell.exe` finto riceve `-NoProfile` e il `PSModulePath` di Windows
PowerShell 5.1 (controllo: lo stesso `powershell.exe` avviato direttamente eredita quello di PS 7). Non verificabile
sotto wine il riconoscimento del processo di raccolta (la WMI di wine non restituisce la riga di comando degli altri
processi: lì il processo risulta «aperto» come prima): va collaudato su una postazione Windows reale.
