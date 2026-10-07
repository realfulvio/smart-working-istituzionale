# Presentazione della pagina pubblica

Gli otto PNG in `docs/img/` sono prodotti offline da `tools/genera_presentazione.py` con Pillow e Titillium Web già nel repository. Palette neutra AgID, grafica geometrica originale; hero e social usano le catture sintetiche della vera app. Non si legge nome del PC, profilo o directory dell’operatore. Ogni PNG è indicizzato, ottimizzato, senza EXIF e inferiore a 500.000 byte. Il generatore interrompe l’esecuzione se supera la soglia.

```powershell
python tools/schermate_documentazione.py --edizione neutra --uscita docs/screenshots
python tools/crea_gif_documentazione.py --edizione neutra --uscita docs/screenshots
python tools/genera_presentazione.py
```

Hero: 1600×800. Social preview: 1280×640, `docs/img/social-preview.png`. La galleria deve precedere gli asset perché questi ultimi ne incorporano alcune immagini; orologio/postazione/nome e percorsi sono sintetici. I sigilli di esempio cambiano con la nuova chiave, quindi le rigenerazioni della giornata non sono identiche byte per byte; a parità di screenshot e Pillow il generatore grafico è deterministico. Il rendering alpha DWM dello splash non è interamente ripreso da PrintWindow: non si presenta la GIF come registrazione fedele di ogni effetto.

## Descrizione breve suggerita

Resoconti del lavoro agile per enti pubblici: segnali minimizzati, revisione del dipendente, AI locale opzionale e PDF sigillati. Windows · EUPL-1.2.

## Topics suggeriti

`public-administration`, `italy`, `windows`, `python`, `tkinter`, `reportlab`, `local-ai`, `data-minimization`, `digital-signatures`, `eupl`, `privacy-by-design`, `remote-work`.

## Caricare la social preview (solo dopo autorizzazione)

1. Nel repository GitHub: **Settings → General → Social preview → Edit → Upload an image**.
2. Selezionare `docs/img/social-preview.png` (1280×640).
3. Controllare anteprima e ritaglio prima di confermare. L’immagine include titolo, versione, app e PDF con dati inventati.

La preview non si aggiorna automaticamente perché il PNG è nel codice. Description, topics e preview sono proposte; non sono stati modificati sul repository remoto. Documentazione GitHub: [social preview](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/customizing-your-repositorys-social-media-preview).
