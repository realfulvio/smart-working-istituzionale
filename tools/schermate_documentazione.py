"""Schermate dell'interfaccia reale e pagine del PDF da dati di ESEMPIO (nessun dato personale).

Uso (computer di sviluppo, display virtuale):
  xvfb-run -a -s "-screen 0 1280x900x24 -dpi 96" python tools/schermate_documentazione.py --uscita docs/screenshots \
      [--server llama-server --modelli DIR]      # con l'assistente locale (altrimenti testo standard)

Ogni schermata è prodotta dall'applicazione vera (applicazione.gui.App) guidata con un orologio finto; i dati della
giornata arrivano da un lettore «a consuntivo» sintetico (eventi di sessione, attività sì/no e applicazioni dell’elenco inventate).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RADICE)
os.environ.update({"USERNAME": "m.rossi", "USERDOMAIN": "ESEMPIO", "COMPUTERNAME": "PC-ESEMPIO", "USER": "m.rossi"})

# Selezionare l'edizione prima degli import che memorizzano ente e token.
# L'import come helper conserva invece la selezione del banco chiamante.
if __name__ == "__main__":
    _early = argparse.ArgumentParser(add_help=False)
    _early.add_argument("--edizione", default="neutra")
    _edition, _ = _early.parse_known_args()
    os.environ["RENDICONTO_EDIZIONE"] = _edition.edizione

from aggregatore import mappa                  # noqa: E402
from collector import giornata as cg          # noqa: E402
from collector.stato import FUSO              # noqa: E402
from tools.demo_documentazione import cattura_demo as cattura, installa_guardia_testi  # noqa: E402

# mappatura di PROVA (applicazioni inventate): quella predefinita del programma ha i siti vuoti
mappa.PERCORSO_PREDEFINITO = os.path.join(RADICE, "tests", "dati", "applicazioni_prova.json")
TZ = FUSO()
LUN = dt.date(2026, 10, 5)


def T(hm, g=LUN):
    h, m = map(int, hm.split(":"))
    return dt.datetime.combine(g, dt.time(h, m), TZ)


class Orologio:
    def __init__(self):
        self.t = T("07:50")

    def __call__(self):
        return self.t


def lettore_esempio(g):
    """Giornata inventata: accesso 07:58, blocco 10:31–10:47, Word/Outlook dell’elenco, chiusura 14:02."""
    ev = [("sessione", T("07:58", g), {"evento": "accesso"}), ("sessione", T("10:31", g), {"evento": "blocco"}),
          ("sessione", T("10:47", g), {"evento": "sblocco"}), ("sessione", T("14:02", g), {"evento": "chiusura"})]
    piano = [("08:00", "10:30", "word"), ("10:47", "11:00", "outlook"), ("11:45", "12:30", "word"),
             ("12:45", "13:30", "word")]
    for a, b, sito in piano:
        t = T(a, g)
        while t < T(b, g):
            ev.append(("app", t, {"exe": "WINWORD.EXE" if sito == "word" else "OUTLOOK.EXE"}))
            ev.append(("attivita", t, {}))
            t += dt.timedelta(minutes=6)
    return {"eventi": sorted(ev, key=lambda x: x[1]),
            "copertura": {"sessione": "completa", "browser": "non_installato", "attivita": "parziale",
                          "app": "parziale", "rete": "non_installato"},
            "stato_iniziale": "chiusa"}


def servizio(base, pdf, oro, ns):
    from applicazione.servizio import Servizio
    imp = {"modalita": "consuntivo", "server_ai": ns.server or "/non/installato", "modelli_ai": ns.modelli or "/x",
           "cache_ai": os.path.join(base, "cache_ai"), "thread_ai": 4, "profilo_ai": "AI-LIGHT" if ns.server else None,
           "cartella_pdf": pdf, "profili_siti": [], "browser": True, "posta": False, "filigrana_pdf": "DATI DI ESEMPIO"}
    return Servizio(base, imp, adesso=oro, lettore=lettore_esempio)


def giornata_precedente(s, oro, g, manuale):
    oro.t = T("08:00", g); s.avvia()
    s.aggiungi_manuale(g.isoformat(), *manuale)
    oro.t = T("14:05", g); s.chiudi()
    s.genera(g.isoformat())
    s.conferma(g.isoformat(), True)


def main():
    installa_guardia_testi()
    ap = argparse.ArgumentParser()
    ap.add_argument("--uscita", default=os.path.join(RADICE, "docs", "screenshots"))
    ap.add_argument("--edizione",default="neutra")
    ap.add_argument("--server"); ap.add_argument("--modelli")
    ns = ap.parse_args()
    os.environ["RENDICONTO_EDIZIONE"]=ns.edizione
    from collector import postazione
    postazione.rileva=lambda:{"nome_macchina":"PC-ESEMPIO","tipo":"VDI","sistema_operativo":"Windows 11 (ESEMPIO)","processore":"CPU di esempio","ram_gb":8}
    os.makedirs(ns.uscita, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="rsw_schermate_")
    base, pdf = os.path.join(tmp, "base"), os.path.join(tmp, "Rendiconti lavoro agile")
    oro = Orologio()
    cg._adesso = oro
    s = servizio(base, pdf, oro, ns)
    # Galleria statica: mostra lo stato finale degli effetti; il GIF usa il movimento reale.
    s.imp["riduci_animazioni"] = "ridotte"
    from applicazione.gui import App
    app = App(s)
    tempi = {}

    def foto(nome, attesa=250):
        app.update(); app.after(attesa); app.update_idletasks(); app.update()
        cattura(app, os.path.join(ns.uscita, nome + ".png"))
        print("schermata", nome)

    def attendi_lavoro():
        while app._occupato:
            app.update(); app.after(100)
        app.update()

    foto("01_informativa_primo_avvio")
    s.registra_informativa("Rossi Maria (ESEMPIO)", "Ufficio Tributi")
    app._aggiorna_utente()
    # due giornate precedenti già confermate (per «Ultimi resoconti»)
    giornata_precedente(s, oro, dt.date(2026, 10, 1), ("telefonata", "12:00", "12:20", "Chiarimenti a un contribuente"))
    giornata_precedente(s, oro, dt.date(2026, 10, 2), ("riunione", "09:00", "09:40", "Riunione di ufficio"))
    oro.t = T("07:56"); app.vai_oggi(); foto("02a_home_giornata_da_avviare")
    oro.t = T("07:58"); s.avvia()
    s.aggiungi_manuale(LUN.isoformat(), "riunione", "11:00", "11:45", "Riunione di servizio sulle scadenze IMU")
    oro.t = T("11:47"); app.vai_oggi(); foto("02_home_giornata_in_corso")
    oro.t = T("12:30"); s.pausa()
    oro.t = T("12:38"); app.vai_oggi(); foto("02b_home_giornata_in_pausa")
    oro.t = T("12:45"); s.riprendi()
    oro.t = T("13:58"); app.vai_oggi(); app.mostra_aggiungi(LUN.isoformat())
    e1, e2, desc = app._campi_attivita
    app._campi_attivita[0].insert(0, "13:40"); e2.insert(0, "14:00"); desc.insert(0, "Chiarimenti a un contribuente sulla TARI")
    desc.event_generate("<KeyRelease>")
    foto("02c_aggiungi_attivita")
    s.aggiungi_manuale(LUN.isoformat(), "telefonata", "13:40", "14:00", "Chiarimenti a un contribuente sulla TARI")
    oro.t = T("14:02"); app.vai_oggi()
    import time
    t0 = time.monotonic()
    app.azione_chiudi()
    preso = False
    while app._occupato:
        app.update(); app.after(100)
        if not preso and app.t_passo3 is not None and time.monotonic() - app.t_passo3 > 4:
            foto("03_chiudi_giornata_generazione", 50); preso = True
    attendi_lavoro()
    tempi["chiusura_e_sintesi_s"] = round(time.monotonic() - t0, 1)
    if not preso:
        foto("03_chiudi_giornata_generazione")
    app.after(800); app.update(); app.update()
    g = LUN.isoformat()
    app.vai_revisione(g)
    app.mostra_segnala(g, "10:30", "10:45")
    app._nota_segnala.imposta("Stavo consultando una pratica cartacea: il blocco del computer è corretto ma ero al lavoro.")
    foto("04c_segnala_dato")
    s.segnala(g, "stato", "10:30", "10:45",
              "Stavo consultando una pratica cartacea: il blocco del computer è corretto ma ero al lavoro.")
    app.vai_impostazioni(); foto("07c_impostazioni")
    app.vai_revisione(g)
    s.imposta_osservazioni(g, "Mattinata con molte richieste allo sportello telefonico.")
    app.vai_revisione(g); foto("04a_revisione_sintesi_da_rigenerare")
    t0 = time.monotonic()
    app.azione_genera(g); attendi_lavoro()
    tempi["rigenerazione_s"] = round(time.monotonic() - t0, 1)
    app.after(800); app.update(); app.update()
    app.vai_revisione(g)
    foto("04_revisione")
    sint = s.documento(g)["sintesi_ai"]
    app.mostra_modifica(g, sint["testo"] + " Nel pomeriggio ho lavorato 3 ore su Microsoft Word.",
                        avvisi=s.controlla_testo(g, sint["testo"] + " Nel pomeriggio ho lavorato 3 ore su Microsoft Word.")["problemi"])
    foto("04b_modifica_sintesi_con_avvisi")
    app.vai_revisione(g)
    app.ho_verificato.set(True); app._verificato_per = (g, sint["testo"]); app.vai_revisione(g)
    foto("04d_revisione_verificata")
    oro.t = T("14:10")
    t0 = time.monotonic()
    app.azione_conferma(g); attendi_lavoro()
    tempi["sigillo_e_pdf_s"] = round(time.monotonic() - t0, 1)
    foto("05_conferma_pdf_salvato")
    pdf_lun = s.resoconti_salvati()[0]["pdf"]
    app.mostra_informazioni(); foto("07_informazioni")
    app.vai_salvati(); foto("08_resoconti_salvati")
    app.vai_aiuto(); foto("09_aiuto")
    # «Cosa viene registrato» nella modalità predefinita (collector): solo il testo, nessun processo di raccolta
    app.vai_oggi(); modalita = s.imp["modalita"]; s.imp["modalita"] = "collector"
    app.mostra_cosa(); foto("07b_cosa_viene_registrato_collector"); app.chiudi_velo(); s.imp["modalita"] = modalita
    # verificatore (registro = la chiave di questa postazione di esempio)
    from verificatore.gui import Verificatore
    reg = os.path.join(tmp, "registro"); os.makedirs(reg)
    shutil.copy(os.path.join(base, "chiave", "pubblica.json"), os.path.join(reg, "PC-ESEMPIO.json"))
    v = Verificatore(app, [reg], pdf_lun); app.update()
    _foto_win(v.win, os.path.join(ns.uscita, "10_verificatore_valido.png"))
    falso = os.path.join(tmp, "manomesso.pdf")
    _manometti(pdf_lun, falso)
    v.mostra(falso); app.update()
    _foto_win(v.win, os.path.join(ns.uscita, "10b_verificatore_alterato.png"))
    v.win.destroy()
    # giornata precedente non chiusa (seconda postazione di esempio)
    oro2 = Orologio()
    cg._adesso = oro2
    s2 = servizio(os.path.join(tmp, "base2"), pdf, oro2, argparse.Namespace(server=None, modelli=None))
    s2.registra_informativa("Rossi Maria (ESEMPIO)", "Ufficio Tributi")
    oro2.t = T("08:03", dt.date(2026, 10, 2)); s2.avvia()
    oro2.t = T("08:10")
    app.s = s2; app.vai_oggi(); foto("06_proposta_chiusura_giorno_precedente")
    shutil.copy(s._f_finale(g), os.path.join(ns.uscita, "finale_esempio.json"))
    # pagine del PDF
    try:                                  # pypdfium2 (solo per la documentazione): pagine del PDF in PNG
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(pdf_lun)
        for i in range(len(doc)):
            doc[i].render(scale=1.3).to_pil().save(os.path.join(ns.uscita, f"pdf_pagina-{i + 1}.png"))
    except ImportError:
        pass
    shutil.copy(pdf_lun, os.path.join(ns.uscita, "resoconto_esempio_2026-10-05.pdf"))
    with open(os.path.join(ns.uscita, "tempi_box.json"), "w", encoding="utf-8") as f:
        json.dump({**tempi, "piattaforma": sys.platform, "motore": "llama.cpp Qwen3-1.7B" if ns.server else "testo standard",
                   "origine_sintesi": s.finale(g)["sintesi_ai"]["origine_testo"]}, f, indent=1)
    print(json.dumps(tempi))
    app.destroy()
    shutil.rmtree(tmp, ignore_errors=True)


def _foto_win(win, path):
    cattura(win, path)
    print("schermata", os.path.basename(path))


def _manometti(src, dst):
    """Copia «manomessa»: stesso JSON allegato, ma testo visibile impaginato da dati con un orario cambiato."""
    import copy
    import io
    from pypdf import PdfReader, PdfWriter
    from resoconto.pdf import NOME_ALLEGATO, pdf_bytes
    r = PdfReader(src)
    orig = json.loads(r.attachments[NOME_ALLEGATO][0])
    falso = copy.deepcopy(orig)
    falso["manuali"][0]["descrizione"] = "Riunione di servizio (testo cambiato dopo la firma)"
    w = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf_bytes(falso, "DATI DI ESEMPIO"))))
    w.add_attachment(NOME_ALLEGATO, json.dumps(orig, ensure_ascii=False).encode("utf-8"))
    w.add_metadata({"/RendicontoSW": r.metadata.get("/RendicontoSW", "5.0.0|filigrana"), "/RendicontoSWFiligrana": "DATI DI ESEMPIO"})
    w.write(dst)


if __name__ == "__main__":
    main()
