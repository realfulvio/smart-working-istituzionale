# Sicurezza

## Come segnalare una vulnerabilità

**Non aprire una issue pubblica** per problemi di sicurezza o di privacy che possano esporre dati dei dipendenti.

Usa la segnalazione privata di GitHub: scheda **Security → Report a vulnerability** di questo repository
(*private vulnerability reporting*). Indica versione, passi per riprodurre, impatto e, se possibile, una proposta di
correzione. Non allegare dati reali di persone: usa dati inventati.

Cosa puoi aspettarti: una prima risposta entro alcuni giorni lavorativi, una valutazione dell'impatto e, per le
vulnerabilità confermate, una correzione e un avviso (changelog/advisory). Il progetto è mantenuto da una sola
persona, senza garanzie di tempi.

Rientrano in ambito, per esempio: falsificazione o aggiramento della verifica del sigillo; raccolta di dati non
previsti dall'elenco chiuso di campi; invio involontario di dati verso l'esterno; esposizione del modello AI locale a
processi di altri utenti; esecuzione di codice tramite file di configurazione o dati d'ingresso; problemi negli
script di installazione/disinstallazione.

## Come funziona il sigillo

Ogni resoconto è un **JSON** (schema `schema/giornaliero.schema.json`) protetto da **due sigilli Ed25519**
(`aggregatore/sigillo.py`):

1. **Sigillo tecnico**, subito dopo l'aggregazione: copre la parte tecnica (tutto tranne attività dichiarate,
   osservazioni, segnalazioni, avvisi di revisione, sintesi e integrità).
2. **Sigillo finale**, alla conferma del dipendente: copre l'**intero** rendiconto rivisto, compreso il sigillo
   tecnico (quindi il suo hash), escluso soltanto sé stesso.

Per ciascun sigillo: il payload viene serializzato in **JSON canonico** (chiavi ordinate, UTF-8, nessuno spazio), se
ne calcola l'**SHA-256**, e si firma con la chiave privata Ed25519 il piccolo documento
`{tipo, sha256, creato_il, impronta_chiave}`. Nel sigillo restano l'hash, la firma, la **chiave pubblica**,
l'**impronta** della chiave, un codice di controllo leggibile (`XXXX-XXXX-XXXX`) e `account`/`pc` di chi ha firmato
(controllati incrociando i due sigilli, perché non sono nella firma del sigillo stesso).

Il PDF contiene il JSON come allegato. Il **Verificatore** (`resoconto/verifica.py`, `aggregatore/sigillo.py`):
estrae il JSON, ricalcola gli hash, controlla le firme, **ricalcola i totali dalle fasce** (un totale ritoccato con
sigillo rifatto a mano non passa), rifiuta JSON con chiavi duplicate o sigilli malformati, rigenera il PDF dallo
stesso JSON e confronta **testo e contenuto grafico** pagina per pagina (un rettangolo bianco sopra un dato, un'annotazione
o contenuti attivi rendono il PDF «ALTERATO»). Esiti:

| Esito | Significato |
|---|---|
| **VALIDO** | sigilli integri e chiave pubblica presente nel **registro delle chiavi** dell'Ente (cartella con le chiavi pubbliche, `--chiavi` o variabile `RSW_REGISTRO_CHIAVI`), con l'account coerente |
| **INTEGRO** | sigilli integri, ma la chiave non è nel registro: non è confermato a chi appartiene |
| **ALTERATO** | contenuto, totali, sigilli o aspetto del PDF non coerenti |
| **NON SIGILLATO** | manca il sigillo tecnico |

### Gestione delle chiavi

- La **chiave privata** è generata sul PC del dipendente alla prima sigillatura, salvata in
  `%LOCALAPPDATA%\RendicontoSW\chiave\privata.bin` e protetta con **DPAPI** di Windows (legata all'account utente).
  Su sistemi non Windows (solo test) il formato è `PLAIN`, **da non usare mai davvero**.
- La **chiave pubblica** è nei sigilli; l'Ente può **registrarla** (file JSON con algoritmo, chiave, impronta,
  account, PC) nel proprio registro, ottenendo l'esito VALIDO. Come e quando registrarla è una scelta dell'Ente.
- **Una chiave privata di sigillo non deve mai finire nel repository.** Il repository non ne contiene (gli esempi in
  `examples/` sono sigillati con una chiave di prova generata al momento e scartata: resta solo la chiave pubblica) e
  `.gitignore` esclude `*.pem`, `*.key`, `privata.bin`, `chiave/`. Se ne trovi una, segnalalo subito in privato.

### Limiti (da conoscere prima di fidarsi del sigillo)

- Il sigillo prova che il documento **non è stato modificato dopo la firma** e che è stato firmato da chi possiede
  quella chiave. **Non prova che i dati siano veri**: la chiave sta sul PC del dipendente, che potrebbe manipolare
  l'ambiente prima della generazione.
- `creato_il` è l'orologio del PC: **non c'è marcatura temporale qualificata**.
- Senza registro delle chiavi l'esito massimo è INTEGRO.
- Finché gli eseguibili e i file `SHA256SUMS.txt` del pacchetto non sono firmati con un certificato dell'Ente, gli
  SHA-256 dell'installazione non sono autenticati.

## Altre scelte di sicurezza

- Nessun diritto di amministratore, nessun servizio, nessuna scrittura in HKLM, nessuna attività pianificata;
  il programma **non aggiunge né rimuove esclusioni** di Defender/ASR/EDR e non disattiva protezioni.
- Nessun invio di dati verso l'esterno. L'assistente AI (`llama-server`) ascolta solo su `127.0.0.1`, su una porta
  libera scelta a ogni avvio e con una **chiave API casuale** per ogni avvio (sulle postazioni virtuali condivise
  `127.0.0.1` è comune alle sessioni dello stesso PC); viene terminato a fine uso e non lascia processi orfani.
- Il registro di raccolta ha un **elenco chiuso di campi** e rifiuta tutto il resto (`collector/registro.py`).
- I test non possono avviare Outlook o Office né usare COM reali (`tests/conftest.py`).
