# Componenti di terze parti — Smart Working Istituzionale

Smart Working Istituzionale © 2026 Luca Accorsi (il titolare definitivo dei diritti va confermato con l'Ente che adotta il programma).
Il codice di questo repository è distribuito con licenza **EUPL-1.2** (file `LICENSE`, testo ufficiale inglese scaricato
da interoperable-europe.ec.europa.eu; la EUPL ha uguale valore in tutte le lingue ufficiali dell'UE).

La build locale usa Python **3.12.10**, Tcl/Tk 8.6, pywin32 **312** e PyInstaller **6.22.3**; Python 3.13 è il riferimento upstream non provato in questo ambiente. Versioni delle librerie principali confermate qui: cryptography 50.0.2, cffi 2.1.1, jsonschema 4.26.0, ReportLab 5.0.1, pypdf 6.19.0, Pillow 12.3.0. Il manifest della build registra gli altri componenti.



## Distribuiti con l'applicazione (esecuzione)

| Componente | Versione verificata | Licenza | Uso |
|---|---|---|---|
| Python | 3.12.10 | PSF-2.0 | interprete |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | firma Ed25519 dei sigilli |
| cffi | 2.1.1 | MIT-0 | dipendenza di cryptography |
| pycparser | 3.0 | BSD-3-Clause | dipendenza di cffi |
| jsonschema | 4.26.0 | MIT | validazione del JSON giornaliero |
| attrs | 26.1.0 | MIT | dipendenza di jsonschema |
| referencing | 0.37.0 | MIT | dipendenza di jsonschema |
| jsonschema-specifications | 2025.9.1 | MIT | dipendenza di jsonschema |
| rpds-py | 2026.6.3 | MIT | dipendenza di referencing |
| pywin32 | (solo Windows) | PSF-2.0 | protezione della chiave privata con DPAPI |
| **llama.cpp** (`llama-server`, build b11386, commit 6716df6) | b11386 | **MIT** (`licenze/llama.cpp-MIT.txt`: lo zip Windows ufficiale non contiene il file di licenza, va distribuito a parte) | runtime dei modelli AI-LIGHT e AI-STANDARD su CPU, avviato solo a «Genera resoconto» su 127.0.0.1 e chiuso subito dopo (M5) |
| LLVM OpenMP (`libomp.dll`, incluso nello zip Windows di llama.cpp) | — | Apache-2.0 WITH LLVM-exception (`licenze/LLVM-OpenMP-Apache-2.0-with-LLVM-exception.txt`) | parallelismo CPU di llama.cpp (solo Windows) |
| **Modello Qwen3-1.7B**, GGUF Q4_K_M (`Qwen3-1.7B-Q4_K_M.gguf`, 1 107 409 472 byte, SHA-256 `b139949c…fa181897`, conversione unsloth/Qwen3-1.7B-GGUF) | — | **Apache-2.0** (Alibaba Cloud / Qwen team; `licenze/Qwen3-1.7B-Apache-2.0.txt`) | redattore della «Sintesi della giornata» (AI-LIGHT, M5); file del modello non incluso nel repository |
| **Modello Qwen3-4B**, GGUF Q4_K_M (`Qwen3-4B-Q4_K_M.gguf`, 2 497 281 312 byte, SHA-256 `f6f85177…a2195813a`, conversione unsloth/Qwen3-4B-GGUF) | — | **Apache-2.0** (Alibaba Cloud / Qwen team; `licenze/Qwen3-4B-Apache-2.0.txt`) | redattore della «Sintesi della giornata» sui PC da ≥ 16 GB (AI-STANDARD, M6); file del modello non incluso nel repository |
| Modello di riserva Qwen2.5-1.5B-Instruct, GGUF Q4_K_M (`qwen2.5-1.5b-instruct-q4_k_m.gguf`, SHA-256 `6a1a2eb6…a9e407e`, repository ufficiale Qwen) | — | Apache-2.0 | riserva provata in M5 (qualità inferiore) |
| Titillium Web (font) | — | SIL Open Font License 1.1 (`applicazione/assets/fonts/OFL-TitilliumWeb.txt`) | carattere dell'interfaccia e del PDF (caricato solo per l'applicazione, senza installarlo nel sistema) |
| Roboto Mono (font) | — | SIL Open Font License 1.1 (`applicazione/assets/fonts/LICENSE-RobotoMono.txt`) | codici di verifica e impronte nel PDF |
| ReportLab | 5.0.1 | BSD-3-Clause | impaginazione del PDF del resoconto e QR code (M7) |
| pypdf | 6.19.0 | BSD-3-Clause | allegato `resoconto.json` nel PDF e lettura nel verificatore (M7) |
| Pillow | 12.3.0 | MIT-CMU (HPND) | dipendenza di ReportLab (immagini) |
| charset-normalizer | 3.5.2 | MIT | dipendenza di ReportLab |
| Tcl/Tk (tkinter, incluso in Python per Windows) | 8.6 | licenza Tcl/Tk (BSD-like) | interfaccia grafica (M7) |

## Solo per sviluppo (non distribuiti)

| Componente | Licenza | Uso |
|---|---|---|
| pytest | MIT | test |
| llama.cpp per Linux (build b11386) | MIT | prove sul computer di sviluppo |

## Previsti nelle prossime milestone (non ancora inclusi)

| Componente | Licenza | Nota |
|---|---|---|
| Ollama (alternativa al runtime, solo se già installato) | MIT | supportato dal codice M5 (`--motore ollama`), non distribuito |
| PyInstaller (solo per creare l'eseguibile; il bootloader è distribuito) | GPL-2.0 con eccezione per il bootloader | da usare quando ci sarà il certificato di firma dell'Ente |

## Esclusioni

- **Nome, logo e marchi dell'Ente** che adotta il programma: gli overlay specifici gli overlay specifici non sono inclusi nel repository pubblico pubblico e non sono coperti dalla EUPL; si configurano in `config/ente.json` e restano dell'Ente.
- I dati di esempio (`examples/`) sono inventati.
