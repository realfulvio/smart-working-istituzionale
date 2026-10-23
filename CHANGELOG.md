# Changelog

## Non rilasciato

- **PDF/A-3b**: il PDF del resoconto ha profilo colore sRGB (OutputIntent), metadati XMP con identificazione PDF/A-3B e `resoconto.json` come file associato (MIME, `AFRelationship /Data`). Date del documento uguali a quelle del sigillo finale. Pagine invariate: impaginatore 5.0.0, esiti del Verificatore invariati. Controllato con veraPDF 1.28 (PDF/A-3B conforme, anche con logo e filigrana). Nuovo modulo `resoconto/pdfa.py`.
- **Metadati AgID**: accanto a ogni PDF confermato, `<nome>.metadati.xml` con i metadati del documento informatico (Linee guida AgID, allegato 5) noti alla creazione, compresa l'impronta SHA-256 del PDF. Nuovo campo facoltativo `codice_ipa` in `ente.json`.
- Build: `--hidden-import PIL.ImageCms` per il profilo colore. Nuovi test in `tests/test_pdfa.py`.

## 5.0.3 — 15/10/2026

- **Timeline della giornata in corso**: l'anteprima dei segnali rilevati (attività al computer e programmi) non compariva mai, perché il file dei dati grezzi riceve il record «meta» solo alla chiusura e l'anteprima lo richiedeva. Ora ne usa uno minimo, senza leggere i dati tecnici della postazione e senza scrivere nulla. Nuovo test in `tests/test_anteprima.py`.
- Versione del programma 5.0.3; impaginatore PDF invariato (5.0.0), quindi i resoconti già creati restano verificabili.

## 5.0.2 — 2026-10-14

- Intestazione: logo ricampionato alla scala reale, mai ingrandito, su un riquadro proporzionato; ritaglio facoltativo solo per l’interfaccia (`ritaglio_logo_interfaccia`). Il file del logo sigillato non cambia.
- Icona unica per finestra, barra delle applicazioni, collegamenti, eseguibile e Setup (tolta l’icona separata del Setup); `iconbitmap` più `iconphoto` a 8 formati, applicata alla prima comparsa della finestra.
- AI: confronto Qwen3-1.7B / Qwen3.5-2B su 20 giornate sintetiche entro un limite di 8 GB (`docs/CONFRONTO_QWEN35_2B.md`, `tools/confronta_modelli.py`). Qwen3.5-2B non adottato: più errori di tipo invenzione intercettati (33 contro 18). Il motore riconosce il template di Qwen3.5 e toglie i blocchi di ragionamento.
- `THIRD_PARTY_NOTICES`: corretta la provenienza del Qwen3-1.7B; README con modello, dimensione, memoria, fonte, SHA-256 e licenza.
- Versione del programma 5.0.2; impaginatore PDF invariato (5.0.0).

## 5.0.1 — 2026-10-14

- Collegamenti: il Setup crea «Resoconto lavoro agile» e «Verifica resoconto» nel menu Start e, con opzione già spuntata, sul Desktop; la disinstallazione li rimuove (Inno e `disinstalla.ps1`).
- Area di notifica: con una giornata avviata la chiusura della finestra lascia un’icona accanto all’orologio con un avviso. Menu Apri, Pausa/Riprendi, Chiudi giornata ed Esci, con conferma; uscire con la giornata in corso la mette in pausa. Tre stati distinti da colore e forma; istanza unica per cartella dati.
- Ripresa dopo un riavvio: una giornata di oggi avviata e rimasta in corso riprende all’apertura o all’accesso (`--avvio-sessione`, opzione del Setup già spuntata). Mai senza «Avvia giornata», mai in pausa o per un altro giorno; la home non indica più «Raccolta in corso» se il processo non è attivo.
- Icone ridisegnate (programma, Verificatore, Setup, area di notifica), .ico da 16 a 256 px generate dai token; rimossa la vecchia icona.
- Versione del programma 5.0.1; impaginatore PDF invariato (5.0.0) per mantenere il confronto grafico dei PDF già emessi.
- Nuovi test mirati in `tests/test_area_notifica.py`.

## 5.0.0 — 2026-10-07

- Pagina pubblica riscritta sul comportamento /5: otto PNG di presentazione riproducibili con Titillium Web, galleria neutra rigenerata, GIF del flusso, badge locali e istruzioni social preview. Prerequisiti, provenienze e limiti del Verificatore espliciti; mappa delle affermazioni al codice.

- Bonifica della documentazione: icona neutra in sette formati ICO; screenshot e GIF rigenerati, guardia obbligatoria dei percorsi fittizi prima delle catture, regressioni dedicate. I crediti autore restano distinti dai dati inventati della giornata.

- JSON sigillato /5 incompatibile con i formati precedenti: identità documentale obbligatoria e snapshot tecnico opzionale, mai inviati all’AI. Nessuna migrazione automatica.
- Un codice, overlay locali, edizione pubblica neutra. Percorsi runtime/modello corretti, AI facoltativa con cause in italiano; fallback invariato.
- UI Tk e PDF ReportLab moderni, provenienze esplicite; effetti brevi riducibili, limitati a meno di 30 fps e sospesi senza interazione/in background.
- Setup Inno 5.0.0 senza bootstrapper: immagini dell’edizione scelta, controllo spazio disco prima della build.
- UTF-8 esplicito, regressioni di privacy e sigilli, screenshot/GIF neutri con dati inventati; nessun nuovo sensore o misura della persona.

Storia del programma *Smart Working Istituzionale* (modulo interno: Rendiconto SW), ricostruita a parole dalla
versione 4.0 alla 4.1.1. Le date sono quelle di sviluppo; in questo repository la storia git non è inclusa.

- Validazione locale finale dell’edizione neutra: 549 test superati; nel worktree pubblico 548 superati e uno skip Tcl/Tk intermittente, superato nel rilancio isolato. Setup installato con sintesi standard e AI locale, PDF VALIDO e modifica rifiutata come ALTERATO. CPU aggiuntiva degli effetti: 2,60 punti di un core sul PC e 2,09 in una simulazione del profilo 8 GB, non VDI fisico. Eseguibili non firmati; nessuna pubblicazione automatica.

## 4.1.1 — 6 ottobre 2026

**La modalità «collector» diventa quella predefinita e arriva il Setup guidato.**

- La modalità predefinita è ora `collector` (anche se il valore in configurazione manca o non è valido): dopo
  «Avvia giornata» e fino a «Pausa» o «Chiudi giornata» un processo di raccolta registra solo eventi di sessione,
  attività sì/no e programmi dell'elenco dell'Ente per fasce di 15 minuti, più un numero per fascia per la rete. La
  modalità `consuntivo` resta come alternativa.
- Il processo di raccolta parte dall'eseguibile installato (`RendicontoSW.exe _esegui`) senza aprire una seconda
  finestra; prova end-to-end della modalità collector fino al PDF.
- Testi per il dipendente allineati alla modalità collector: informativa del primo avvio, schermata «Oggi»,
  «Cosa viene registrato», informativa breve del Setup.
- **Setup guidato** (Inno Setup 6, per utente, senza amministratore): quattro pagine, rifiuto delle destinazioni di
  rete, codici d'uscita documentati, disinstallazione guidata con domanda facoltativa sull'eliminazione dei resoconti
  (i dati restano per impostazione predefinita).
- Installazione: Windows PowerShell 5.1 viene avviato con il `PSModulePath` standard anche se il Setup parte da
  PowerShell 7; il processo di raccolta in esecuzione viene rilevato in installazione (chiede di fermarlo) e fermato
  in disinstallazione.

## 4.1.0 — 6 ottobre 2026

**Bonifica per la privacy (privacy-first): meno dati, meno funzioni invasive.**

- Rimossa la lettura della cronologia del browser e ogni indirizzo di sito dai dati raccolti.
- Rimossa l'analisi della posta (Outlook/Graph): Outlook resta solo la categoria «Posta elettronica» del programma in
  primo piano; il programma non avvia mai Outlook.
- Rimosse le parti invasive del prototipo precedente (lettura di titoli di finestra, simulazione di input, documenti
  recenti) e il consuntivo retroattivo dal registro di sicurezza di Windows.
- I programmi **non presenti nell'elenco** non vengono registrati: contano solo come attività della fascia.
- Elenco dei siti di lavoro ridotto al minimo indispensabile e documentato come configurazione locale dell'Ente;
  eliminati indicatori non compatibili dall'applicazione e dal PDF.
- Il formato 4.0.0 dei PDF resta verificabile (`resoconto/storico`).

## 4.0.x — 2 ottobre – 5 ottobre 2026 (dalla 4.0.0 al pacchetto di prova)

**Dal solo aggregatore all'applicazione completa.**

- *Aggregatore e sigillo* (4.0.0): da eventi grezzi normalizzati a un JSON giornaliero a fasce fisse di 15 minuti;
  stati di sessione, categorie, totali ricalcolabili; **sigillo in due fasi con Ed25519** (tecnico e finale), JSON
  canonico, verifica con esiti VALIDO / INTEGRO / ALTERATO / NON SIGILLATO; schema JSON, riga di comando, tre
  giornate sintetiche di esempio.
- *Raccolta*: processo di raccolta Windows senza amministratore (eventi di sessione, input sì/no per fascia, programma
  in primo piano dell'elenco, richieste SMB della sola sessione dell'utente), registro con elenco chiuso di campi.
- *Sintesi AI locale*: redattore con fatti numerati, modello Qwen3 su llama.cpp in locale (profili AI-Light e
  AI-Standard), **controllo anti-invenzione** sempre più severo (numeri, orari, quantità, nomi propri, caratteri
  invisibili), testo standard di riserva, «Riscrivi» e modifica del testo da parte del dipendente.
- *Applicazione*: interfaccia Tk (giornata, pausa, revisione, attività dichiarate, segnalazioni, sintesi, conferma),
  PDF di 7 pagine con JSON allegato, **Verificatore** con confronto del testo e dell'aspetto grafico, chiusura
  transazionale con «Riprova la chiusura», giornate a cavallo della mezzanotte.
- *Estensione del browser* opzionale e disattivata, senza permesso `tabs`, solo siti dell'elenco.
- *Pacchetto*: installazione e disinstallazione per utente con staging, controllo SHA-256, rollback e voce in «App
  installate»; pacchetto con solo `llama-server` e DLL.
- *Sicurezza dei test*: i test non possono avviare Outlook né Office; controlli statici sugli script.
- Licenza EUPL-1.2 e avvisi sulle componenti di terze parti.
