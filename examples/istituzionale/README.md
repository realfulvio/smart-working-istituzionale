# Fixture istituzionali: solo dati inventati

Tre scenari: giornata ordinaria 08:00–14:00, sessione senza segnali informatici, Halley simulato per PoC.
Word e Outlook compaiono anche nella stessa fascia; lock/unlock e disconnect/reconnect sono espliciti.
Le attività dichiarate e l'osservazione non modificano le fasce automatiche. Halley è un identificativo simulato,
non un'estensione attiva. Nessun account, hostname o dato macchina nell'aggregato /4.

Rigenerare in una cartella **nuova** con `py tools/simula_edizione.py --output <cartella-nuova>`.
Il simulatore non sovrascrive fixture o dati operativi e non entra nel Collector. I file non sono sigillati:
i test generano chiavi temporanee e verificano INTEGRO, VALIDO e ALTERATO, senza commettere chiavi private.

## Banco AI italiano

Ogni scenario include `fatti-ai.json` e `fallback.json`: medesimo input minimizzato per ogni candidato.
Valutare separatamente: fedeltà ai fatti, provenienza per frase, italiano comprensibile, rispetto dei gap,
latenza di caricamento/generazione e picco di memoria su VDI 8 GB e PC 16+ GB.
Scartare testo che inventa azioni, unisce fonti diverse, calcola durate dai segnali o valuta la persona.
Il controllo esistente e il fallback restano obbligatori anche con un modello linguisticamente migliore.

Nessun benchmark con modelli reali è stato eseguito in questa milestone. I Qwen previsti upstream restano
candidati configurabili, non una scelta validata. Runtime llama.cpp mantenuto conservativamente.
