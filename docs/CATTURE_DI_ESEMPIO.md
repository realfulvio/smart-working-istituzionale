# Catture della documentazione

La galleria viene rigenerata dall'app Tk con una giornata sintetica: Rossi Maria (ESEMPIO), PC-ESEMPIO, account ESEMPIO\m.rossi. I crediti Luca Accorsi/Accorsi Luca identificano l'autore del software, non una persona osservata nella giornata.

Ogni percorso visibile è fittizio, sotto `C:\Users\utente\Documents\…`. Gli artefatti si scrivono in cartelle temporanee reali, ma queste non devono apparire nelle immagini. `tools/demo_documentazione.py` sostituisce percorsi assoluti, UNC e abbreviazioni nei widget, comprese Entry, variabili, Text e testi Canvas, immediatamente prima della cattura. Screenshot e ogni frame GIF usano obbligatoriamente `cattura_demo`; non esiste un'opzione per disabilitare la guardia. Le impostazioni del servizio e la destinazione effettiva dei PDF non cambiano.

```powershell
python tools/genera_icona_neutra.py
python tools/schermate_documentazione.py --edizione neutra --uscita docs/screenshots
python tools/crea_gif_documentazione.py --edizione neutra --uscita docs/screenshots
python -m pytest tests/test_documentazione_percorsi.py -q
```

L'icona rappresenta un documento geometrico con spunta, senza araldica; ICO a 16, 24, 32, 48, 64, 128 e 256 px. La cattura registra soltanto la finestra dell'app. Rivedere comunque tutte le immagini, tutti i frame GIF e tutte le dimensioni ICO dopo rigenerazione: i controlli sui testi e sugli hash non sostituiscono l'esame visivo. Verificare anche metadati delle immagini e allegati/metadati dei PDF. Le fixture dei documenti storici servono ai test del Verificatore, non descrivono la UI attuale.
