# Contribuire

Grazie dell'interesse. Questo software tratta dati personali di lavoratori: le regole qui sotto sono **vincolanti**.

## Regola d'oro

> **Non aggiungere raccolte invasive e non raccogliere di più del necessario.**

Una modifica che amplia ciò che il programma legge, registra o conserva **non viene accettata** senza che sia
dimostrata la necessità, descritta in [PRIVACY.md](PRIVACY.md) e [README.md](README.md) (tabella dei dati) e
accompagnata da test. In particolare **non si accettano**: lettura di tasti, mouse, schermate, titoli di finestre,
nomi di file o percorsi, contenuto o metadati della posta, cronologia e indirizzi del browser, nomi di server o
cartelle di rete, posizione, elenchi di processi/programmi installati, telemetria o invio automatico di dati,
conservazione di durate o sequenze fini, elaborazioni in cloud, analisi del «rendimento» o punteggi sulle persone.

## Prima di aprire una pull request

1. **Una modifica = un obiettivo.** Niente riprogettazioni non richieste.
2. Se tocca i dati: aggiorna `collector/registro.py` (elenco chiuso di campi), `schema/giornaliero.schema.json`,
   [PRIVACY.md](PRIVACY.md), la tabella del README e il [CHANGELOG](CHANGELOG.md), e spiega nel testo della PR
   *perché serve* e *perché non basta meno*.
3. **Test**: esegui almeno `python -m pytest -q tests/test_bonifica.py tests/test_collector_predefinito.py`
   (controllano che non compaiano API vietate) e i test dell'area che modifichi. Aggiungi test per ogni correzione.
4. **Solo dati inventati**: negli esempi, nei test e nelle schermate non devono comparire persone, enti, macchine,
   reti, indirizzi o domini reali. Usa nomi come «Rossi Maria (ESEMPIO)», domini `.test`/`.invalid`, indirizzi
   `198.51.100.0/24`.
5. **Mai chiavi, certificati, token o password** nel repository (`.pem`, `.key`, `privata.bin`…). Le chiavi di prova
   si generano al momento e non si committano.
6. Niente modelli AI, zip di llama.cpp o eseguibili compilati nel repository.
7. Rispetta lo stile del codice circostante (italiano per nomi di dominio e commenti, come nei moduli esistenti).
8. Non aggirare Defender/ASR/EDR e non aggiungere esclusioni; non avviare Outlook o Office dai test.

## Licenza

Contribuendo accetti che il tuo contributo sia distribuito con licenza **EUPL-1.2** (vedi [LICENSE](LICENSE)).
Problemi di sicurezza: vedi [SECURITY.md](SECURITY.md), non aprire una issue pubblica.
