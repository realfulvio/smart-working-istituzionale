"""Verificatore con interfaccia: scegli il file (PDF o JSON), vedi l'esito e i motivi.

Il registro delle chiavi (cartella con le chiavi pubbliche registrate dai Sistemi Informativi) distingue VALIDO da
INTEGRO. Nessuna rete: tutto avviene su questo computer.
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import filedialog

from applicazione import tema
from applicazione.tema import C, F, Bottone, Scheda, etichetta, percorso_breve, px
from resoconto.formati import data_lunga
from resoconto.verifica import verifica_file

COLORI = {"VALIDO": (C["ok"], C["ok_bg"], "✓"), "INTEGRO": (C["primary"], C["tint"], "✓"),
          "ALTERATO": (C["err"], C["err_bg"], "✕"), "NON SIGILLATO": (C["warn_txt"], C["warn_bg"], "!")}
SPIEGAZIONE = {
    "VALIDO": "I dati e il testo del PDF corrispondono ai sigilli e la chiave della postazione è registrata dai "
              "Sistemi Informativi.",
    "INTEGRO": "I dati e il testo del PDF corrispondono ai sigilli, ma la chiave non è nel registro indicato: non è "
               "confermato da quale postazione provenga.",
    "ALTERATO": "Il resoconto è stato modificato dopo il sigillo, oppure il testo del PDF non corrisponde ai dati: "
                "non va accettato.",
    "NON SIGILLATO": "Il resoconto non è stato confermato e sigillato dal dipendente (o manca il file dati allegato)."}


def scatti_rotella(e) -> int:
    """Scatti della rotella: Windows/macOS delta multipli di 120 (anche frazioni dai touchpad: almeno 1 scatto),
    X11 Button-4 (su) / Button-5 (giù)."""
    num = getattr(e, "num", None)
    if num == 4:
        return -1
    if num == 5:
        return 1
    d = int(getattr(e, "delta", 0) or 0)
    if d == 0:
        return 0
    n = int(-d / 120)
    return n if n else (-1 if d > 0 else 1)


class Verificatore:
    def __init__(self, master=None, chiavi=None, file=None):
        self.radice = master is None
        if self.radice:
            self.win = tk.Tk()
            tema.carica_font(self.win)
        else:
            self.win = tk.Toplevel(master)
        from applicazione.movimento import Movimento
        self.movimento = Movimento(self.win, getattr(master,"s",None).imp.get("riduci_animazioni","sistema") if master is not None and getattr(master,"s",None) else "sistema")
        self.win.title("Verifica resoconto")
        self.win.configure(bg=C["bg"])
        self.win.geometry(f"{px(780)}x{px(700)}")
        self.win.minsize(px(640), px(560))
        self.chiavi = [c for c in (chiavi or []) if c]
        t = tk.Frame(self.win, bg=C["primary"], height=px(56)); t.pack(fill="x"); t.pack_propagate(False)
        from resoconto import ente
        identity = ente.carica()
        self.img_stemma = None
        if identity["logo"]:
            from PIL import Image, ImageTk
            im = Image.open(identity["logo"]).convert("RGBA")
            im.thumbnail((px(42), px(42)), Image.Resampling.LANCZOS)
            self.img_stemma = ImageTk.PhotoImage(im, master=self.win)
            tk.Label(t, image=self.img_stemma, bg=C["primary"]).pack(side="left", padx=(px(18), 0))
        tk.Frame(self.win, bg=C["gold"], height=px(3)).pack(fill="x")
        etichetta(t, identity["nome"] + " · Verifica resoconto", 18, "bold", colore="white").pack(side="left", padx=px(16))
        self.corpo = tk.Frame(self.win, bg=C["bg"]); self.corpo.pack(fill="both", expand=True, padx=px(24), pady=px(18))
        pw = tk.Frame(self.win, bg=C["bg"]); pw.pack(side="bottom", anchor="e", padx=px(10))
        etichetta(pw, "powered by Accorsi Luca", 11, colore="#8a99a6").pack()
        self.mostra(file)

    def scegli(self):
        f = filedialog.askopenfilename(parent=self.win, title="Scegli il resoconto",
                                       filetypes=[("Resoconto PDF o JSON", "*.pdf *.json"), ("Tutti i file", "*.*")])
        if f:
            self.mostra(f)

    def scegli_registro(self):
        d = filedialog.askdirectory(parent=self.win, title="Cartella del registro delle chiavi")
        if d:
            self.chiavi = [d]
            if getattr(self, "file", None):
                self.mostra(self.file)

    def mostra(self, file=None):
        self.file = file
        for w in self.corpo.winfo_children():
            w.destroy()
        sc = Scheda(self.corpo); sc.pack(fill="both", expand=True)
        p = tk.Frame(sc, bg="white"); p.pack(fill="both", expand=True, padx=px(24), pady=px(20))
        b = tk.Frame(p, bg="white"); b.pack(side="bottom", fill="x", pady=(px(12), 0))
        Bottone(b, "Scegli un file…", self.scegli).pack(side="left")
        Bottone(b, "Registro delle chiavi…", self.scegli_registro, "secondario").pack(side="left", padx=px(10))
        Bottone(b, "Chiudi", self.win.destroy, "link").pack(side="right")
        reg = self.chiavi[0] if self.chiavi else "non indicato"
        etichetta(p, f"Registro delle chiavi: {percorso_breve(reg)}", 12, colore=C["muted"], wrap=680).pack(side="bottom", anchor="w")
        if not file:
            etichetta(p, "Scegli il PDF del resoconto (oppure il file JSON).", 16, "semi", colore=C["dark"]).pack(anchor="w")
            etichetta(p, "Il controllo legge il file dati allegato al PDF, verifica i due sigilli (tecnico e del "
                         "dipendente) e confronta il testo di ogni pagina con i dati sigillati.", 14,
                      colore=C["muted"], wrap=660).pack(anchor="w", pady=(px(6), 0))
            return
        r = verifica_file(file, self.chiavi)
        self.risultato = r
        fg, bg, sim = COLORI.get(r["esito"], COLORI["ALTERATO"])
        top = tk.Frame(p, bg="white"); top.pack(fill="x")
        cv = tk.Canvas(top, width=px(64), height=px(64), bg="white", highlightthickness=0)
        cv.create_oval(3, 3, px(61), px(61), fill=fg, outline=bg, width=px(4))
        cv.create_text(px(32), px(33), text=sim, fill="white", font=F(26, "bold"))
        cv.pack(side="left")
        if r["esito"] in ("VALIDO","ALTERATO"):
            from applicazione.movimento import sigillo
            sigillo(cv,r["esito"]=="VALIDO",fg)
        tx = tk.Frame(top, bg="white"); tx.pack(side="left", padx=px(16))
        etichetta(tx, r["esito"], 28, "bold", colore=fg).pack(anchor="w")
        spiegazione = SPIEGAZIONE.get(r["esito"], "")
        if r["esito"] == "INTEGRO" and r["tipo"] == "pdf" and r.get("testo_pdf") != "corrisponde ai dati":
            spiegazione = "I sigilli sono integri; testo e grafica del PDF non sono stati verificati completamente. Consulta i motivi."
        etichetta(tx, spiegazione, 14, colore=C["muted"], wrap=560).pack(anchor="w")
        tk.Frame(p, bg=C["line"], height=1).pack(fill="x", pady=px(14))
        righe = [("File", os.path.basename(file)),
                 ("Giornata", data_lunga(r["giorno"]) if r.get("giorno") else "—"),
                 ("Dipendente", r.get("dipendente") or "—"),
                 ("Codice di verifica", r.get("codice") or "—"),
                 ("Testo del PDF", r.get("testo_pdf") or ("non applicabile (file JSON)" if r["tipo"] == "json" else "—"))]
        for s in ("tecnico", "finale"):
            x = (r.get("sigilli") or {}).get(s)
            if x:
                righe.append((f"Sigillo {s}", ("integro" if x["valido"] else "NON corrisponde") if x["presente"] else "assente"))
        for a, v in righe:
            rr = tk.Frame(p, bg="white"); rr.pack(fill="x", pady=px(1))
            etichetta(rr, a, 14, "semi", width=18).pack(side="left")
            etichetta(rr, v, 14, wrap=480).pack(side="left")
        if r.get("motivi"):
            self.area_motivi(p, r["motivi"], fg, bg)
            self.adatta_altezza()

    def area_motivi(self, master, motivi, fg, bg):
        """Motivi dell'esito in un'area di testo a scorrimento (collaudo ALFA3 B10/N3: il 3º motivo era tagliato e la
        rotella non scorreva). Testo a capo per parola, altezza per almeno 3 motivi, barra sempre visibile, rotella
        attiva sul testo e su tutta l'area (su Windows la rotella va alla finestra col fuoco: bind_all all'ingresso
        del puntatore, delta/120 scatti)."""
        box = tk.Frame(master, bg=bg)
        box.pack(fill="both", expand=True, pady=(px(12), 0))
        righe = sum(max(1, -(-len(x) // 78)) for x in motivi) + len(motivi)        # a capo stimati + spazio
        testo = tk.Text(box, wrap="word", bg=bg, fg=fg, font=F(13), relief="flat", borderwidth=0, highlightthickness=0,
                        padx=px(10), pady=px(6), height=max(7, min(12, righe)), cursor="arrow",
                        spacing1=px(2), spacing3=px(4))
        sb = tk.Scrollbar(box, orient="vertical", command=testo.yview)
        testo.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")                  # sempre visibile (ALFA2 B10)
        testo.pack(side="left", fill="both", expand=True)
        testo.insert("end", "\n".join("• " + x for x in motivi))
        testo.configure(state="disabled")                # sola lettura, ma selezionabile/copiabile
        self.testo_motivi, self.barra_motivi = testo, sb

        def ruota(e):
            testo.yview_scroll(scatti_rotella(e), "units")
            return "break"

        def attiva(on):
            if on:
                self.win.bind_all("<MouseWheel>", ruota)
                self.win.bind_all("<Button-4>", ruota)
                self.win.bind_all("<Button-5>", ruota)
            else:
                for k in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                    self.win.unbind_all(k)
        for w in (box, testo, sb):
            w.bind("<Enter>", lambda _e: attiva(True), add="+")
            w.bind("<Leave>", lambda _e: attiva(False), add="+")
        for w in (testo, box):
            for k in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                w.bind(k, ruota)
        return testo

    def adatta_altezza(self):
        """La finestra cresce (fino all'85 % dello schermo) se il contenuto non ci sta: niente motivi tagliati."""
        try:
            self.win.update_idletasks()
            serve = self.win.winfo_reqheight()
            ora = self.win.winfo_height() if self.win.winfo_ismapped() else px(650)
            massimo = int(self.win.winfo_screenheight() * 0.85)
            if serve > ora:
                self.win.geometry(f"{max(self.win.winfo_width(), px(780))}x{min(serve, massimo)}")
        except tk.TclError:
            pass

    def avvia(self):
        if self.radice:
            self.win.mainloop()


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="VerificaRendiconto")
    ap.add_argument("file", nargs="?")
    ap.add_argument("--chiavi", action="append", default=[], help="cartella del registro delle chiavi")
    ns = ap.parse_args(argv)
    chiavi = ns.chiavi or [x for x in (os.environ.get("RSW_REGISTRO_CHIAVI"),) if x]
    Verificatore(None, chiavi, ns.file).avvia()
    return 0


if __name__ == "__main__":
    sys.exit(main())
