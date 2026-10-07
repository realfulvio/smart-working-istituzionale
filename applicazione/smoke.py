"""Collaudo end-to-end senza intervento (--smoke-giornata): Avvia giornata → attività dichiarata → Chiudi giornata →
«Ho verificato la sintesi» → «Conferma e crea il PDF».

Nato dal collaudo ALFA3 (N1): «Chiudi giornata» falliva solo nell'eseguibile congelato e nessun test lo esercitava.
Qui si percorre lo STESSO codice dei pulsanti, non una scorciatoia:
  - modalità «finestra» (predefinita): crea la vera finestra App (nascosta) e preme i pulsanti veri
    (Bottone._click / Casella._click): «Avvia giornata», «+ Aggiungi attività» → «+ Aggiungi»,
    «Chiudi giornata – Genera resoconto», la casella «Ho verificato la sintesi», «Conferma e crea il PDF»;
  - modalità «senza finestra» (ripiego se Tk non è disponibile): chiama le funzioni che quei pulsanti eseguono nel
    thread di lavoro: Servizio.avvia, Servizio.aggiungi_manuale, Servizio.chiudi_e_genera, Servizio.conferma.
Dati: SOLO la cartella --base indicata (mai %LOCALAPPDATA%\\RendicontoSW), Outlook mai toccato,
estensione spenta, registri FINTI (eventi di sessione e una visita «halley» dentro l'orario della giornata, nessun
registro eventi né browser reale letto), PDF in <base>\\pdf. Esito in JSON (--esito); codice 0 = PDF creato.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
import traceback

from collector.stato import FUSO, Stato

ATTESA_TRA_AVVIO_E_CHIUSURA_S = 4


def impostazioni_collaudo(base: str, testo_standard: bool = False) -> dict:
    from .servizio import carica_impostazioni
    imp = carica_impostazioni(base)
    imp.update(modalita="consuntivo", estensione_browser=False,
               cartella_pdf=os.path.join(base, "pdf"), cache_ai=os.path.join(base, "cache_ai"))
    if testo_standard:
        imp["server_ai"] = os.path.join(base, "assistente_assente", "llama-server.exe")
    return imp


def lettore_finto(p):
    """Eventi sintetici di collaudo (accesso, sblocco, sito «halley»): il prodotto a consuntivo non legge più registri
    (bonifica B6b); qui servono solo a esercitare aggregazione, PDF e verificatore con dati finti."""
    def leggi(giorno: dt.date) -> dict:
        g = Stato(p).giornata()
        avvio = dt.datetime.fromisoformat(g["fasi"][0]["avvio"])
        ev = [("sessione", avvio - dt.timedelta(minutes=20), {"evento": "accesso"}),
              ("sessione", avvio + dt.timedelta(seconds=1), {"evento": "sblocco"}),
              ("web", avvio + dt.timedelta(seconds=2), {"sito": "halley"})]
        return {"eventi": [e for e in ev if e[1].date() == giorno],
                "copertura": {"sessione": "completa", "attivita": "non_installato", "app": "non_installato",
                              "rete": "non_installato", "browser": "parziale"},
                "stato_iniziale": "chiusa"}
    return leggi


def _servizio(base: str, testo_standard: bool):
    from collector import postazione
    postazione.rileva = lambda: {"nome_macchina": "PC-ESEMPIO", "tipo": "VDI",
                                 "sistema_operativo": "Windows 11 (ESEMPIO)", "processore": "CPU di esempio", "ram_gb": 8}
    from .servizio import Servizio
    os.makedirs(base, exist_ok=True)
    s = Servizio(base, impostazioni=impostazioni_collaudo(base, testo_standard))
    s._lettore = lettore_finto(s.p)
    if s.serve_informativa():
        s.registra_informativa("Collaudo Automatico (ESEMPIO)", "Sistemi Informativi")
    return s


ATTIVITA = ("riunione", "Riunione di collaudo automatico")


def _ore_attivita(s) -> tuple[str, str]:
    a = s.adesso().replace(second=0) - dt.timedelta(minutes=50)
    if a.date() != s.adesso().date():
        return "00:00", "00:15"
    return a.strftime("%H:%M"), (a + dt.timedelta(minutes=30)).strftime("%H:%M")


def _senza_finestra(s, passi: list) -> dict:
    t0 = time.monotonic()
    giorno = s.avvia()
    passi.append({"passo": "avvia", "fase": s.stato()["fase"], "s": round(time.monotonic() - t0, 2)})
    dalle, alle = _ore_attivita(s)
    s.aggiungi_manuale(giorno, ATTIVITA[0], dalle, alle, ATTIVITA[1])
    passi.append({"passo": "attivita_dichiarata", "dalle": dalle, "alle": alle})
    time.sleep(ATTESA_TRA_AVVIO_E_CHIUSURA_S)
    v = s.chiudi_e_genera(None, True)
    passi.append({"passo": "chiudi_giornata", "fase": s.stato()["fase"], "json": v["chiusura"]["json"],
                  "origine_sintesi": (v.get("sintesi") or {}).get("origine_testo"), "s": round(time.monotonic() - t0, 2)})
    r = s.conferma(giorno, True)
    passi.append({"passo": "conferma_pdf", "pdf": r["pdf"], "s": round(time.monotonic() - t0, 2)})
    return r


def _bottoni(w, testo: str):
    from .tema import Bottone
    out = []

    def giro(x):
        if isinstance(x, Bottone) and testo in str(x.lab.cget("text")) and x.winfo_exists():
            out.append(x)
        for c in x.winfo_children():
            giro(c)
    giro(w)
    return out


def _caselle(w):
    from .tema import Casella
    out = []

    def giro(x):
        if isinstance(x, Casella):
            out.append(x)
        for c in x.winfo_children():
            giro(c)
    giro(w)
    return out


def _con_finestra(s, passi: list, timeout_s: float, usa_ai: bool = False) -> dict:
    from .gui import App
    app = App(s)
    app.withdraw()
    t0 = time.monotonic()
    stato = {"fase": "avvia", "errori": [], "conferma": None, "eccezione": None, "attesa_da": None}
    errore_orig, conferma_orig = app.errore, app.mostra_conferma

    def errore(testo, titolo="Non è stato possibile completare l'operazione"):
        stato["errori"].append(testo)
        errore_orig(testo, titolo)

    def mostra_conferma(giorno, r):
        stato["conferma"] = r
        conferma_orig(giorno, r)
    app.errore, app.mostra_conferma = errore, mostra_conferma

    def premi(testo: str, dentro=None):
        b = _bottoni(dentro or app, testo)
        if not b:
            raise RuntimeError(f"pulsante «{testo}» non trovato nella schermata")
        if not b[0]._attivo:
            raise RuntimeError(f"pulsante «{testo}» disattivato")
        b[0]._click()

    def passo():
        try:
            if stato["errori"]:
                raise RuntimeError("errore mostrato dall'app: " + " | ".join(stato["errori"]))
            if time.monotonic() - t0 > timeout_s:
                raise TimeoutError(f"collaudo oltre {timeout_s:.0f} s (fase {stato['fase']})")
            f = stato["fase"]
            if f == "avvia":
                premi("Avvia giornata")
                passi.append({"passo": "avvia", "fase": s.stato()["fase"], "s": round(time.monotonic() - t0, 2)})
                stato["fase"] = "aggiungi"
            elif f == "aggiungi":
                premi("Aggiungi attività")
                e1, e2, desc = app._campi_attivita
                dalle, alle = _ore_attivita(s)
                e1.insert(0, dalle); e2.insert(0, alle); desc.insert(0, ATTIVITA[1])
                if app.velo is None:
                    raise RuntimeError("finestra «Aggiungi un'attività» non aperta")
                premi("+  Aggiungi", dentro=app.velo)
                man = s.revisione(s.stato()["giorno"])["manuali"]
                if not man:
                    raise RuntimeError("attività dichiarata non salvata")
                passi.append({"passo": "attivita_dichiarata", "dalle": dalle, "alle": alle, "voci": len(man)})
                stato["fase"], stato["attesa_da"] = "attendi_prima_di_chiudere", time.monotonic()
            elif f == "attendi_prima_di_chiudere":
                if time.monotonic() - stato["attesa_da"] >= ATTESA_TRA_AVVIO_E_CHIUSURA_S:
                    stato["giorno"] = s.stato()["giorno"]
                    premi("Chiudi e rivedi")
                    stato["fase"] = "attendi_revisione"
            elif f == "attendi_revisione":
                bt = getattr(app, "bt_conferma", None)
                if not app._occupato and bt is not None and bt.winfo_exists():
                    st = s.stato()
                    doc = s.documento(stato["giorno"])
                    if not doc.get("sintesi_ai"):
                        if usa_ai:
                            scelta = s.disponibilita_ai(doc)
                            passi.append({"passo": "scelta_ai", "disponibile": scelta["disponibile"],
                                          "profilo": scelta["profilo"], "causa": scelta["causa"]})
                            cas = [c for c in _caselle(app.corpo) if c.var is app.usa_ai]
                            if scelta["disponibile"] and cas and not app.usa_ai.get():
                                cas[0]._click()
                        app.azione_genera(stato["giorno"])
                        app.after(150, passo)
                        return
                    passi.append({"passo": "chiudi_giornata", "fase_dopo": Stato(s.p).giornata().get("fase"),
                                  "json": s.p.json_giorno(stato["giorno"]),
                                  "origine_sintesi": (doc.get("sintesi_ai") or {}).get("origine_testo"),
                                  "da_confermare": st["da_confermare"], "s": round(time.monotonic() - t0, 2)})
                    cas = [c for c in _caselle(app.corpo) if c.var is app.ho_verificato]
                    if not cas:
                        raise RuntimeError("casella «Ho verificato la sintesi» non trovata")
                    if not app.ho_verificato.get():
                        cas[0]._click()
                    premi("Conferma e crea il PDF")
                    stato["fase"] = "attendi_pdf"
            elif f == "attendi_pdf":
                if stato["conferma"] is not None and not app._occupato:
                    r = stato["conferma"]
                    passi.append({"passo": "conferma_pdf", "pdf": r["pdf"], "s": round(time.monotonic() - t0, 2)})
                    stato["fase"] = "fatto"
                    app.after(300, app.destroy)
                    return
            app.after(150, passo)
        except Exception as e:   # noqa: BLE001 - collaudo: qualunque errore chiude e finisce nell'esito
            stato["eccezione"] = e
            stato["traccia"] = traceback.format_exc()
            app.after(50, app.destroy)
    app.after(300, passo)
    app.mainloop()
    if stato["eccezione"] is not None:
        e = stato["eccezione"]
        e.traccia = stato.get("traccia")
        raise e
    if stato["conferma"] is None:
        raise RuntimeError("finestra chiusa prima della conferma")
    return stato["conferma"]


def esegui(base: str, esito: str | None = None, finestra: bool = True, testo_standard: bool = False,
           timeout_s: float = 600) -> int:
    base = os.path.abspath(base)
    passi: list = []
    r: dict = {"ok": False, "base": base, "modalita": "finestra" if finestra else "senza_finestra", "passi": passi}
    try:
        if os.path.isdir(base) and os.listdir(base):
            raise RuntimeError(f"la cartella di collaudo deve essere nuova o vuota: {base}")
        s = _servizio(base, testo_standard)
        if finestra:
            try:
                import tkinter
                tkinter.Tcl()
            except Exception as e:   # noqa: BLE001
                r["modalita"] = f"senza_finestra (Tk non disponibile: {e})"
                finestra = False
        conf = _con_finestra(s, passi, timeout_s, usa_ai=not testo_standard) if finestra else _senza_finestra(s, passi)
        g = Stato(s.p).giornata()
        fin = s.finale(conf.get("json") and os.path.basename(conf["json"])[:-5] or g.get("giorno"))
        r.update(ok=os.path.isfile(conf["pdf"]) and g.get("fase") == "conclusa", pdf=conf["pdf"],
                 codice=conf.get("codice"), json_finale=conf.get("json"), fase_finale=g.get("fase"),
                 origine_sintesi=(fin.get("sintesi_ai") or {}).get("origine_testo"),
                 manuali=len(fin.get("manuali") or []), dimensione_pdf=os.path.getsize(conf["pdf"])
                 if os.path.isfile(conf["pdf"]) else 0)
    except Exception as e:   # noqa: BLE001 - collaudo: riportare qualunque errore nel file esito
        r.update(ok=False, errore=f"{type(e).__name__}: {e}",
                 traccia=getattr(e, "traccia", None) or traceback.format_exc())
        try:
            with open(os.path.join(base, "stato", "giornata.json"), encoding="utf-8") as f:
                r["stato_giornata"] = json.load(f)
        except (OSError, ValueError):
            pass
    r["ora_fine"] = dt.datetime.now(FUSO()).replace(microsecond=0).isoformat()
    if esito:
        with open(esito, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1, default=str)
    return 0 if r["ok"] else 1
