# README 5.0.0: riferimenti verificati sul codice

Questa mappa separa il comportamento operativo /5 da commenti, PoC e fixture storici. Nessuna frase del README è un’attestazione di conformità normativa.

| Affermazione | Fonte nel codice |
|---|---|
| Collector attivo soltanto nella giornata avviata e fuori dalle pause | `collector/giornata.py`, `collector/demone.py`, `applicazione/servizio.py` |
| Sessione/input sì-no e filtraggio dei programmi prima della scrittura | `collector/campionatore.py`, `collector/registro.py`, `collector/win.py` |
| SMB non istanziato e Halley/estensione forzati disabilitati | `collector/demone.py` (smb=None), `applicazione/servizio.py` (carica_impostazioni), `config/app.json` |
| JSON /5: fasce e conteggi di segnali, non durate aggregate/classifiche | `schema/giornaliero.schema.json`, `aggregatore/aggrega.py`, `aggregatore/modelli.py` |
| Snapshot con cinque campi, flag letto prima del rilevamento | `collector/postazione.py`, `aggregatore/aggrega.py`, `config/ente.json` |
| Hardware escluso dai fatti AI e testo standard | `redattore/fatti.py`, `redattore/sintesi.py`; minimizzazione profilo in `_profilo_pubblico` di `applicazione/servizio.py` |
| Snapshot sigillato ed escluso dalla pagina 1 | `aggregatore/sigillo.py`, `resoconto/pdf.py`, regressioni `tests/test_postazione_tecnica.py` |
| Niente account/hostname propagati nei sigilli nuovi | `aggregatore/sigillo.py`, `tests/test_revisione_sigillo.py` |
| Fatti con provenienza e AI opzionale; messaggi modello/runtime/RAM/permessi | `redattore/fatti.py`, `redattore/profilo.py`, `applicazione/servizio.py` (diagnostica_ai) |
| Motore vincolato a HTTP 127.0.0.1, no proxy/redirect | `redattore/motore.py` (_valida_url, _SenzaRedirect, _apri) |
| Quattro esiti e degradazione a INTEGRO senza confronto grafico | `resoconto/verifica.py`, `aggregatore/sigillo.py` |
| Un codice, base neutra e overlay selezionato/materializzato | `resoconto/edizione.py`, `tools/configura_edizione.py`, `docs/EDIZIONI.md` |
| Movimento <=30 fps, inattività/background e preferenza Windows | `applicazione/movimento.py`, `verificatore/gui.py`, `docs/MOVIMENTO.md` |
| Installazione per utente, versione Setup e controllo spazio | `tools/pacchetto/setup/RendicontoSW.iss`, `tools/pacchetto/setup/compila_setup.ps1`, `tools/pacchetto/installa.ps1` |
| Conservazione default null e policy raw limitata | `config/raccolta.json`, `collector/retention.py`, `applicazione/servizio.py` (conferma) |

Le etichette dei vecchi PDF e i commenti del PoC non vanno copiati nella descrizione della versione 5.0.0. Le durate nelle attività dichiarate sono orari indicativi del dipendente; non vengono presentate come durate misurate del lavoro. Per le limitazioni del Verificatore si usa il codice effettivo, non il solo nome dell’esito.
