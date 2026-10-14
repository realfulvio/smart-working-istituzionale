# Confronto Qwen3-1.7B / Qwen3.5-2B per la «Sintesi della giornata» — 14/10/2026

**Decisione: Qwen3.5-2B NON adottato.** Sta negli 8 GB ed è più veloce, ma inventa più fatti: il controllo anti-invenzione ha intercettato 33 errori di tipo invenzione contro 18 di Qwen3-1.7B. Per la regola fissata per questa versione («se inventa più fatti, non adottarlo») la 5.0.2 resta su **Qwen3-1.7B**.

## Metodo

- **Dati:** 20 giornate **sintetiche** del banco M5 (`tools/m5_giornate_sintetiche.py`), nessun dato reale. I casi coperti:
  - giornata normale, solo mattina, solo pomeriggio, mattina e sera;
  - molte pause, riunioni e sopralluoghi senza segnali, molte dichiarazioni;
  - giornata quasi vuota e giornata breve;
  - segnalazioni e osservazioni con numeri e nomi propri («Richiesta urgente del sindaco», «delibera n. 45/2026», «ordine 1234»);
  - tentativo di prompt injection, VDI con disconnessioni, sospensione, sblocco implicito.
- **Pipeline:** quella dell'app (`redattore.sintesi.genera`), per entrambi i modelli:
  - stessi fatti, stesso prompt e stesso esempio;
  - temperatura 0, top_k 1, seme 42, 4 thread;
  - uscita vincolata da JSON Schema e controllo anti-invenzione;
  - secondo tentativo se il primo è respinto, testo standard se anche il secondo fallisce.
- **Template:** Qwen3.5 usa il template ufficiale (`<think>` vuoto solo nel turno da generare, ragionamento spento). L'uscita viene comunque ripulita da eventuali blocchi `<think>`. Nessun blocco di ragionamento è comparso.
- **Strumento:** `tools/confronta_modelli.py`. Lo strumento rigenera i risultati grezzi (testi e motivi dei rifiuti) in JSON.
- **Runtime:** llama.cpp b11386 (build `b11386-6716df694`), lo stesso della 5.0.0/5.0.1. Carica anche l'architettura `qwen35`, quindi non serve aggiornarlo.
- **Profilo 8 GB:** tutto il banco, compreso `llama-server`, è girato **dentro un Job Object di Windows con limite di 8 GB** (JobMemoryLimit, come nella simulazione della 5.0). Il limite è stato impostato e nessuna generazione è fallita.
- **Macchina:** PC di sviluppo, 6 CPU logiche, 12 GB. Non è la VDI fisica.
- **Modelli:**
  - `Qwen3-1.7B-Q4_K_M.gguf`: 1.282.439.584 byte, SHA-256 `72c5c3cb…250b24fb`, bartowski/Qwen_Qwen3-1.7B-GGUF, Apache-2.0. È quello già distribuito.
  - `Qwen3.5-2B-Q4_K_M.gguf`: 1.280.835.840 byte, SHA-256 `aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223`, https://huggingface.co/unsloth/Qwen3.5-2B-GGUF, revisione `f6d5376b`, conversione di Qwen/Qwen3.5-2B, Apache-2.0. Solo testo: il `mmproj` non è stato scaricato.

## Totali

| Totali | Qwen3-1.7B | Qwen3.5-2B |
|---|---|---|
| Giornate | 20 | 20 |
| Sintesi AI accettate dal controllo | 14 | 12 |
| … al primo tentativo | 11 | 9 |
| Ripiego sul testo standard | 6 | 8 |
| Versioni respinte dal controllo | 15 | 19 |
| Problemi segnalati dal controllo (totale) | 37 | 51 |
| Controllo finale superato | 20 | 20 |
| Tempo mediano per giornata (s) | 14.9 | 11.4 |
| Tempo massimo (s) | 27.64 | 21.3 |
| Generazione mediana (s) | 12.9 | 9.3 |
| Caricamento mediano (s) | 1.1 | 1.6 |
| RAM di picco del motore, working set max (MB) | 1442 | 1545 |
| RAM privata di picco max (MB) | 466 | 771 |

**Errori intercettati dal controllo, per tipo** (nelle versioni respinte):

| Tipo | Qwen3-1.7B | Qwen3.5-2B |
|---|---:|---:|
| Orari o attività abbinati male, intervalli composti da fatti diversi | 3 | **16** |
| Parola o nome assente dai fatti (es. «Gestione Halley», «verbale», «pausa») | 6 | 9 |
| Orario assente dai fatti (es. 17:35 al posto di 17:30) | 3 | 5 |
| Numero assente dai fatti | 6 | 3 |
| **Totale invenzioni** | **18** | **33** |
| Provenienze mescolate (rilevato e dichiarato nella stessa frase) | 8 | 8 |
| Osservazione citata senza dire che è del dipendente | 2 | 5 |
| Forma (frase incompleta, numero in lettere, termine valutativo) | 7 | 5 |

## Per giornata

Ogni cella: esito (AI accettata oppure ripiego sul testo standard) · tentativi · problemi segnalati · secondi · MB di picco del motore.

| Giornata | Qwen3-1.7B: esito · tentativi · problemi respinti · s · MB | Qwen3.5-2B: esito · tentativi · problemi respinti · s · MB |
|---|---|---|
| g01_giornata_piena | AI · 1 · 0 · 22.22 · 1420 | AI · 1 · 0 · 12.5 · 1512 |
| g02_solo_mattina | standard · 2 · 2 · 19.05 · 1392 | standard · 2 · 2 · 11.38 · 1455 |
| g03_solo_pomeriggio | AI · 1 · 0 · 10.78 · 1393 | AI · 1 · 0 · 6.89 · 1450 |
| g04_vdi_disconnessioni | AI · 1 · 0 · 12.38 · 1399 | standard · 2 · 2 · 13.38 · 1462 |
| g05_nessuna_attivita | AI · 2 · 3 · 14.88 · 1402 | AI · 1 · 0 · 5.42 · 1439 |
| g06_solo_dichiarate | standard · 2 · 15 · 27.16 · 1442 | standard · 2 · 5 · 13.3 · 1465 |
| g07_molte_dichiarate | AI · 1 · 0 · 14.97 · 1417 | AI · 2 · 6 · 21.3 · 1545 |
| g08_segnalazioni | standard · 2 · 6 · 27.64 · 1438 | standard · 2 · 6 · 15.5 · 1510 |
| g09_molte_pause | AI · 1 · 0 · 12.55 · 1406 | standard · 2 · 13 · 15.8 · 1539 |
| g10_halley_lunga | AI · 1 · 0 · 10.34 · 1391 | standard · 2 · 6 · 10.94 · 1459 |
| g11_web_generico | AI · 1 · 0 · 10.27 · 1389 | AI · 1 · 0 · 5.75 · 1448 |
| g12_molta_posta | AI · 1 · 0 · 9.12 · 1389 | AI · 1 · 0 · 6.11 · 1447 |
| g13_posta_zero | standard · 2 · 2 · 20.2 · 1392 | AI · 1 · 0 · 6.66 · 1450 |
| g14_mattina_e_sera | standard · 2 · 2 · 19.97 · 1397 | standard · 2 · 2 · 11.98 · 1459 |
| g15_sospensione | AI · 1 · 0 · 9.89 · 1394 | AI · 1 · 0 · 7.06 · 1451 |
| g16_sblocco_implicito | AI · 2 · 3 · 19.12 · 1395 | AI · 2 · 1 · 11.52 · 1458 |
| g17_prompt_injection | standard · 2 · 3 · 22.48 · 1397 | standard · 2 · 6 · 13.88 · 1466 |
| g18_osservazioni_valutative | AI · 2 · 1 · 23.17 · 1397 | AI · 2 · 2 · 13.78 · 1461 |
| g19_giornata_breve | AI · 1 · 0 · 9.97 · 1389 | AI · 1 · 0 · 5.56 · 1447 |
| g20_sovrapposte | AI · 1 · 0 · 13.11 · 1397 | AI · 1 · 0 · 7.34 · 1455 |

## Qualità dell'italiano e aderenza ai fatti (giudizio)

- **Italiano:** i due modelli scrivono in modo molto simile, con lo stesso stile formale imposto dall'esempio.
  - Qwen3.5-2B è un po' più completo sulle attività dichiarate: in g07 e g20 riporta ogni attività con i suoi orari, mentre l'1.7B le riassume genericamente.
  - Entrambi producono talvolta forme poco naturali, come «Il dipendente ha dichiarato nessuna attività».
- **Aderenza ai fatti:** qui Qwen3.5-2B è peggiore.
  - Tende a usare gli orari degli eventi di sessione come orari dell'attività (17:35 / 16:10 invece di 17:30 / 10:00, in g07 e g10).
  - Attribuisce al dipendente le pause rilevate (g09).
  - Storpia i nomi delle categorie («Gestione Halley», g10).
  - In g18 la versione accettata contiene una frase vera nella forma, ma fuorviante: «Nessuna attività informatica rilevata è stata dichiarata dal dipendente».
- **Rete di sicurezza:** il controllo ha fermato tutte le invenzioni numeriche e di orario. Nessuna sintesi finale contiene orari o numeri inventati, e il controllo finale è superato in 20 giornate su 20 per entrambi. Il costo è più ripieghi sul testo standard (8 contro 6) e una sintesi meno affidabile.
- **Prompt injection (g17):** entrambi i modelli sono stati respinti («produttività», «ottima», «10 ore») e la giornata è passata al testo standard.

## Prestazioni e memoria

- **Tempo:** Qwen3.5-2B è più veloce, con una mediana di 11,4 s contro 14,9 s per giornata e una generazione mediana di 9,3 s contro 12,9 s. Il caricamento è un po' più lento (1,6 s contro 1,1 s).
- **Memoria:** il picco del working set del motore è 1.545 MB contro 1.442 MB; quello della memoria privata 771 MB contro 466 MB. Entrambi stanno ampiamente nel profilo 8 GB e sotto la soglia di memoria libera del profilo LIGHT (2,2 GB). Nessun errore con il limite del Job Object.

## Conclusione

Qwen3.5-2B non viene adottato nella 5.0.2. Resta Qwen3-1.7B. Nel codice restano:
- il supporto al template di Qwen3.5;
- la rimozione dei blocchi di ragionamento, utile anche come protezione;
- lo strumento di confronto, per poter ripetere la prova con un altro quantizzatore o con una versione successiva.

Una nuova prova avrebbe senso:
- con una quantizzazione più fedele (Q5_K_M/Q6_K: occupano più memoria, quindi va rimisurato il profilo 8 GB);
- con l'esempio del prompt aggiornato su orari di sessione e pause.

Entrambe sono modifiche fuori dal perimetro «minimo» di questa versione.
