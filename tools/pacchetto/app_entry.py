"""Punto di ingresso di RendicontoSW.exe (PyInstaller).

Opzione di collaudo (senza finestra, senza dati utente): --smoke-pdf FILE_JSON FILE_PDF [--esito FILE]
genera il PDF da un JSON finale con lo stesso runtime congelato dell'app (ALFA3).

«RendicontoSW.exe _esegui»: processo di raccolta della modalità collector. collector/giornata.py lo lancia con
[sys.executable, "_esegui"] a «Avvia giornata»/«Riprendi» (cartella dati in RSW_BASE); senza questo ramo l'argomento
finiva all'argparse dell'interfaccia (argomento sconosciuto, uscita 2 senza messaggi in un exe --windowed) e dopo
10 s l'app mostrava «il processo di raccolta non è partito».
"""
import sys


def _raccolta() -> int:
    """Processo di raccolta senza finestra: un errore va in diagnostica/collector.log, mai in una finestra di dialogo."""
    try:
        from collector.cli import main
        return main(["_esegui"])
    except Exception:  # noqa: BLE001 - processo nascosto: l'interfaccia segnala «il processo di raccolta non è partito»
        try:
            import traceback
            from collector.percorsi import Percorsi
            from collector.stato import Stato
            Stato(Percorsi.predefiniti()).log("errore del processo di raccolta: " + traceback.format_exc()[-1500:])
        except Exception:  # noqa: BLE001
            pass
        return 1


def _smoke_pdf(argv) -> int:
    import json
    import traceback
    i = argv.index("--smoke-pdf")
    sorgente, uscita = argv[i + 1], argv[i + 2]
    esito = argv[argv.index("--esito") + 1] if "--esito" in argv else None
    try:
        from resoconto.pdf import crea_pdf
        with open(sorgente, encoding="utf-8-sig") as f:
            doc = json.load(f)
        crea_pdf(doc, uscita)
        r, codice = {"ok": True, "pdf": uscita}, 0
    except Exception as e:  # noqa: BLE001 - collaudo: riportare qualunque errore nel file esito
        r, codice = {"ok": False, "errore": repr(e), "traccia": traceback.format_exc()}, 1
    if esito:
        with open(esito, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
    return codice


if __name__ == "__main__":
    if sys.argv[1:2] == ["_esegui"]:
        sys.exit(_raccolta())
    if "--smoke-pdf" in sys.argv:
        sys.exit(_smoke_pdf(sys.argv))
    from applicazione.gui import main
    sys.exit(main())
