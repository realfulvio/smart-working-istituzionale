# Un codice, più identità locali

`config/` è la base neutra: «Il tuo Ente», simbolo geometrico generico, palette #0066CC. L'overlay contiene solo `ente.json`, `design_tokens.json`, `identita.json` e logo: nessun fork della UI, PDF o Collector. La selezione è locale, mai inviata all'AI.

Avvio neutro: `$env:RENDICONTO_EDIZIONE='neutra'; python -m applicazione`.
Avvio personalizzato: impostare la stessa variabile al nome della cartella in `edizioni/`, oppure scrivere `config/edizione.json` con `{"overlay":"nome-cartella"}`. Senza selezione si usa la base neutra. I percorsi del logo sono relativi all'ente.json dell'overlay. Le impostazioni di raccolta condivise restano separate dall'identità.

La selezione precede gli import e viene letta all'avvio: dopo una modifica riavviare l'app. L'overlay può indicare `versione_informativa`; nessun codice o test deve contenere nomi specifici dell'Ente. Gli strumenti di cattura scelgono l'edizione prima di caricare i token.

Build: `powershell -NoProfile -File tools/pacchetto/build_app.ps1 -Edizione neutra` oppure il nome dell'overlay. `tools/configura_edizione.py` materializza **solo** la configurazione scelta in una cartella nuova `build/config-edizione-<id>`; rifiuta destinazioni non vuote per evitare residui tra edizioni. Il pacchetto non include gli altri overlay. La compilazione Inno genera le immagini e legge nome Ente dalla configurazione del pacchetto. Versione tecnica unica, indipendente dall'identità.

Il codice e il simbolo generico sono EUPL-1.2; nome e stemma dell'Ente adottante non sono coperti dalla licenza del software. Il titolare dell'overlay ne autorizza uso e diffusione. La pubblicazione del codice neutro non autorizza la pubblicazione di overlay privati.
