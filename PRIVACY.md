# PRIVACY — Smart Working Istituzionale 5.0.0

Dettaglio tecnico per l’Ente, aggiornato al 07/10/2026 sullo schema giornaliero /5. Non è un’informativa, una DPIA o una dichiarazione di conformità. I prerequisiti organizzativi del [README](README.md) restano da validare.

## Lettura e raccolta

| Fonte | Dato ammesso | Attivazione | Codice |
|---|---|---|---|
| Sessione | Eventi di accesso, blocco/sblocco, disconnessione/riconnessione, sospensione/ripresa e chiusura con ora | Solo giornata avviata; notifiche del processo locale | `collector/demone.py`, `collector/win.py` |
| Attività informatica | Presenza sì/no nella fascia, senza tasti, testo o movimenti | Campionatore, fuori dalle pause | `collector/campionatore.py` |
| Applicazioni | Solo nome dell’eseguibile previsto dall’elenco CED | Finestra attiva, filtro prima della scrittura | `collector/campionatore.py`, `collector/win.py` |
| Dichiarazioni | Categoria, orari indicativi e breve descrizione forniti dal dipendente | Inserimento volontario nel resoconto | `applicazione/servizio.py`, `aggregatore/modelli.py` |
| Osservazioni | Nota generale e segnalazioni su dati tecnici | Inserimento del dipendente | `applicazione/servizio.py` |

Il processo parte con Avvia/Riprendi e si ferma con Pausa/Chiudi o alla chiusura della sessione. Nessun servizio, task pianificato o avvio automatico al login. Non legge il registro eventi di Windows. Il lettore storico «a consuntivo» è conservato per compatibilità e test, non estende la V1.

**Rete e Halley disabilitati.** Il sensore SMB non viene istanziato. L’estensione browser non viene distribuita né abilitata tramite impostazioni utente. I moduli e fixture del PoC rimangono separati; non sono prova di affidabilità sull’infrastruttura reale.

Mai titoli delle finestre, nomi/percorsi o contenuti dei file, schermate, testo/tasti, movimenti del mouse, conteggi/contenuti/destinatari della posta, cronologia/URL o applicazioni fuori elenco nel raw. `collector/registro.py` applica un elenco chiuso dei campi. Il collector applica l’allowlist prima della scrittura; un programma sconosciuto non viene conservato come nuova voce.

## Dati scritti e minimizzazione

Il raw locale contiene gli eventi tecnici consentiti; l’aggregatore normalizza, ordina e deduplica. Le fasce sono centralizzate in `config/raccolta.json`, con default 15 minuti e alternative 20/30/60. Le applicazioni simultanee restano nella stessa fascia, senza sommare durate.

Il JSON `rendiconto-sw/giornaliero/5` è il confine di minimizzazione: data/fuso, identità funzionale minima (nome, ufficio, eventuale matricola), contesto di sessione, fasce, segnali/categorie, dichiarazioni, osservazioni, avvisi e sigilli. Le aggregazioni riportano conteggi di fasce, non durate di lavoro dedotte o classifiche. Specifica: `schema/giornaliero.schema.json`; produzione: `aggregatore/aggrega.py`.

Il solo livello tecnico può includere `dati_tecnici_postazione` con **nome_macchina**, **tipo** (VDI/PC fisso, euristica), **sistema_operativo** (nome e versione/build), **processore** (denominazione), **ram_gb** (RAM totale; null se non disponibile). `collector/postazione.py` legge lo snapshot alla chiusura dai dati locali del sistema; nessun campionamento nuovo, WMI o inventario dei processi. Niente IP, MAC, SID, account, numero di serie o percorsi. `config/ente.json` → `dati_tecnici_postazione: false` evita anche la lettura; default true. Il CED configura l'interruttore, non il dipendente.

Questi cinque campi sono coperti sia dal sigillo tecnico sia da quello finale, presenti nel JSON allegato e nel riquadro della nota metodologica del PDF; mai in pagina 1. Non entrano nei fatti di `redattore/fatti.py`, nei prompt, nel testo standard o nella sintesi AI. Il Verificatore non legge l'hardware corrente per verificarli: usa lo snapshot sigillato.

A dati automatici, B dichiarazioni, C osservazioni e D sintesi restano distinti. I dati tecnici sigillati non sono modificati dal dipendente; una segnalazione aggiunge una nota. La sintesi modificata dal dipendente è identificata come dichiarata, con eventuali avvisi confermati.

Dati operativi nella base locale dell’utente: raw, giorni aggregati, revisioni, finali, chiave e diagnostica. PDF nella cartella locale scelta. Preferenze personali: nome/ufficio nello stato, cartella PDF in `impostazioni.json`. Il file personale non è riempito con la policy CED.

La chiave privata è protetta da DPAPI su Windows. La chiave pubblica può essere copiata nel registro del Verificatore. I sigilli nuovi non propagano account o PC. Metadati tecnici delle chiavi preesistenti restano locali per compatibilità; non sono stati eliminati.

## AI e connessioni

L’AI è opzionale e viene richiesta dalla revisione. Il testo standard non avvia alcun motore. La scelta del profilo usa diagnostica locale, senza modificare la raccolta o i fatti e senza esportare RAM o path nel resoconto (`_profilo_pubblico` in `applicazione/servizio.py`).

`redattore/fatti.py` costruisce soltanto fatti minimizzati; ogni fatto ha provenienza. `redattore/controllo.py` rifiuta frasi che mescolano origini e verifica riferimenti/numeri. Se il controllo fallisce o il modello manca, `redattore/sintesi.py` usa il fallback. Questo controllo riduce errori, non certifica la correttezza di ogni frase.

`redattore/motore.py` accetta solo HTTP su **127.0.0.1**, senza proxy, credenziali o redirect esterni. Nessuna telemetria, cloud, download di font/modelli o invio del PDF a runtime. Runtime e modelli, se necessari, sono predisposti separatamente. La consegna del PDF è manuale.

## PDF e verifica

Il PDF contiene nome/ufficio/data, sintesi con origine, categorie, dichiarazioni, tutte le fasce, osservazioni, nota metodologica, conferma e codice del sigillo; non mostra identificativi tecnici inutili. Metadati: titolo, autore funzionale e versione dell’impaginatore; lingua `it`. Il JSON minimizzato è allegato come `resoconto.json`.

Sigilli Ed25519 in due fasi: tecnico sui dati automatici, finale sul resoconto confermato. Il Verificatore verifica sigilli e corrispondenza testuale/grafica del PDF. Non attesta qualità o contenuto del lavoro. Il confronto grafico è limitato dalla versione del renderer e dalla configurazione dell’Ente disponibile.

Schema /3 e renderer storici restano isolati. I vecchi documenti possono contenere campi oggi esclusi: non vengono migrati, riscritti o cancellati automaticamente. La loro verifica non reintroduce quei campi nel flusso /5.

## Conservazione

`retention_raw_giorni` e `retention_da_data` sono null: nessuna cancellazione automatica finché l’Ente non valida periodo e decorrenza. `collector/retention.py` offre anteprima ed esecuzione. Il Servizio lo chiama dopo aver salvato PDF e JSON finale.

Quando configurata, la policy ammette solo raw nuovi marcati all’avvio, dopo decorrenza/scadenza, con resoconto /5 finale confermato e integro. Include la copia `.prima_della_chiusura`. Conserva storico non marcato, giornate non confermate, finali alterati, symlink e percorsi fuori base. Non elimina JSON, revisioni, PDF o chiavi: policy separate da validare. Non opera come servizio periodico; un raw scaduto può restare fino alla successiva esecuzione della policy.

Nessun dato reale è stato cancellato durante lo sviluppo. Test e schermate usano soltanto dati inventati in cartelle temporanee. I dati storici sono stati inventariati, senza conversione automatica.

## Decisioni dell’Ente ancora necessarie

Informativa e trasparenza, DPO/DPIA e adempimenti applicabili dell’art. 4 L. 300/1970; ruoli/accessi ai resoconti; periodi di conservazione dei diversi livelli; firma del codice e pilota; autorizzazione all’identità grafica. Sono requisiti forniti dall’utente, non decisioni normative prese dal software.
