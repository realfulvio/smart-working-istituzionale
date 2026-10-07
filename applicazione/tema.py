"""Tema grafico Tk dell'applicazione: palette configurabile dell'Ente (config/ente.json), Titillium Web, componenti semplici.

I font si caricano per la sola applicazione (Windows: AddFontResourceExW con FR_PRIVATE, nessuna installazione nel
sistema, nessun diritto di amministratore). Se non disponibili si usa Segoe UI.
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import font as tkfont

from .movimento import gestore, mescola
from resoconto import ente
from resoconto.formati import COLORI_STATO

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_col = ente.carica()["colori"]
from resoconto.tokens import palette
C = palette()
C.update({"primary": _col["primario"], "primary_h": _col["primario_scuro"], "dark": _col["scuro"], "tint": _col["tenue"],
          "gold": _col["accento"]})
FAMIGLIA = "Segoe UI"
FAMIGLIA_SB = "Segoe UI Semibold"
SCALA = 1.0


def carica_font(root: tk.Tk) -> str:
    """Rende disponibili i font dell'applicazione e imposta la scala per lo schermo. → famiglia usata."""
    global FAMIGLIA, FAMIGLIA_SB, SCALA
    cartella = os.path.join(ASSETS, "fonts")
    if sys.platform == "win32":
        try:
            import ctypes
            for f in sorted(os.listdir(cartella)):
                if f.lower().endswith(".ttf"):
                    ctypes.windll.gdi32.AddFontResourceExW(os.path.join(cartella, f), 0x10, 0)   # FR_PRIVATE
        except Exception:   # noqa: BLE001
            pass
    fam = set(tkfont.families(root))
    if "Titillium Web" in fam:
        FAMIGLIA = "Titillium Web"
        FAMIGLIA_SB = "Titillium Web SemiBold" if "Titillium Web SemiBold" in fam else "Titillium Web"
    elif sys.platform != "win32":
        FAMIGLIA = FAMIGLIA_SB = "DejaVu Sans"
    try:
        SCALA = max(1.0, root.winfo_fpixels("1i") / 96.0)
    except tk.TclError:
        SCALA = 1.0
    return FAMIGLIA


def px(n: float) -> int:
    return int(round(n * SCALA))


def F(dim: float, peso: str = "normal", corsivo: bool = False) -> tuple:
    """Font in pixel. peso: normal | semi | bold."""
    fam = FAMIGLIA_SB if peso == "semi" else FAMIGLIA
    stile = ["bold"] if peso == "bold" else []
    if corsivo:
        stile.append("italic")
    return (fam, -px(dim), " ".join(stile) or "normal")


# ------------------------------------------------------------------------------------------------ componenti
class Scheda(tk.Frame):
    """Card bianca con bordo sottile."""
    def __init__(self, master, bg=None, bordo=None, **kw):
        super().__init__(master, bg=bg or C["white"], highlightthickness=1,
                         highlightbackground=bordo or C["bordo"], highlightcolor=bordo or C["bordo"], **kw)
        self._bordo_base=bordo or C["bordo"]
        # Angoli disegnati, controlli e focus restano widget nativi.
        r=px(10);outer=master.cget("bg");inner=bg or C["white"]
        for ax,ay,ox,oy in ((0,0,0,0),(1,0,-r,0),(0,1,0,-r),(1,1,-r,-r)):
            corner=tk.Canvas(self,width=r,height=r,bg=outer,highlightthickness=0,takefocus=0)
            corner.place(relx=ax,rely=ay,x=-r if ax else 0,y=-r if ay else 0)
            corner.create_oval(ox,oy,ox+2*r,oy+2*r,fill=inner,outline=self._bordo_base)
            self.tk.call("lower",str(corner))
        self.bind("<Enter>",lambda e:self._eleva(True),add="+")
        self.bind("<Leave>",lambda e:self._eleva(False),add="+")

    def _eleva(self,on):
        g=gestore(self)
        target=C["primary"] if on else self._bordo_base
        start=self.cget("highlightbackground")
        if g:g.effetto(self,lambda n:self.configure(highlightbackground=mescola(start,target,n)),.16,chiave=(str(self),"hover"))
        else:self.configure(highlightbackground=target)


def etichetta(master, testo="", dim=15, peso="normal", colore=None, bg=None, wrap=None, corsivo=False, adatta=False,
              **kw):
    """adatta=True: il testo va a capo alla larghezza del contenitore (solo se il contenitore è esteso dal suo
    genitore, es. pack(fill="x"): altrimenti la larghezza dipenderebbe dal testo stesso)."""
    bg = bg if bg is not None else master.cget("bg")
    kw.setdefault("justify", "left"); kw.setdefault("anchor", "w")
    lab = tk.Label(master, text=testo, font=F(dim, peso, corsivo), fg=colore or C["text"], bg=bg, **kw)
    if wrap and adatta:
        massimo = px(wrap)
        lab.configure(wraplength=massimo)

        def adatta_a(e, lab=lab):
            # il testo va a capo alla larghezza disponibile (colonne strette, finestre piccole)
            try:
                lab.configure(wraplength=max(px(80), min(massimo, e.width - px(6))))
            except tk.TclError:
                pass
        master.bind("<Configure>", adatta_a, add="+")
    elif wrap:
        lab.configure(wraplength=px(wrap))
    return lab


class Bottone(tk.Frame):
    """Pulsante piatto: primario (blu), secondario (bordo blu), link, pericolo; supporta lo stato disattivato."""
    STILI = {"primario": (C["primary"], C["white"], C["primary"], C["primary_h"]),
             "secondario": (C["white"], C["dark"], C["primary"], C["tint2"]),
             "tenue": (C["white"], C["text"], C["bordo"], C["tint2"]),
             "link": (None, C["primary"], None, None),
             "oro": (C["decl_bg"], C["decl_txt"], C["decl"], C["tint2"]),
             "pericolo": (C["white"], C["err"], C["err"], C["err_bg"])}

    def __init__(self, master, testo, comando=None, stile="primario", dim=15, padx=18, pady=9, larghezza=None):
        bg, fg, bordo, hover = self.STILI[stile]
        pbg = master.cget("bg")
        self._bg = bg or pbg
        super().__init__(master, bg=self._bg, takefocus=1, highlightthickness=2, highlightcolor=C["white"] if stile == "primario" else C["dark"],
                         highlightbackground=bordo or pbg, cursor="hand2")
        self.stile, self.comando, self._attivo = stile, comando, True
        self._colori = (self._bg, fg, bordo or pbg, hover or self._bg)
        f = F(dim, "semi")
        self.lab = tk.Label(self, text=testo, font=f, fg=fg, bg=self._bg, padx=px(padx) if stile != "link" else 0,
                            pady=px(pady) if stile != "link" else 0, cursor="hand2")
        if stile == "link":
            self.lab.configure(font=(f[0], f[1], (f[2] if f[2] != "normal" else "") + " underline"))
        if larghezza:
            self.lab.configure(width=larghezza)
        self.lab.pack(fill="both", expand=True)
        for w in (self, self.lab):
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>", lambda e: self._hover(True))
            w.bind("<Leave>", lambda e: self._hover(False))

        self.bind("<Return>", self._click)
        self.bind("<space>", self._click)
        self.bind("<FocusIn>", lambda e: rendi_visibile(self))

    def _hover(self, on):
        if not self._attivo or self.stile == "link":
            return
        c = self._colori[3] if on else self._colori[0]
        g=gestore(self)
        start=self.cget("bg")
        def draw(n):
            color=mescola(start,c,n);self.configure(bg=color);self.lab.configure(bg=color)
        if g:g.effetto(self,draw,.12,chiave=(str(self),"bouton"))
        else:draw(1)

    def _click(self, _e=None):
        if self._attivo and self.comando:
            self.focus_set()
            original=self.lab.cget("pady")
            self.lab.configure(pady=int(original)+1)
            g=gestore(self)
            if g:g.effetto(self,lambda n:self.lab.configure(pady=original if n>=1 else int(original)+1),.08)
            else:self.lab.configure(pady=original)
            self.comando()
        return "break"

    def attiva(self, si: bool = True):
        self._attivo = si
        self.configure(takefocus=int(si))
        bg, fg, bordo, _ = self._colori
        if si:
            self.configure(bg=bg, highlightbackground=bordo, cursor="hand2"); self.lab.configure(bg=bg, fg=fg, cursor="hand2")
        else:
            grigio = "#c4ccd4" if self.stile == "primario" else "#9aa6b1"
            fondo = "#e3e8ee" if self.stile == "primario" else bg
            self.configure(bg=fondo, highlightbackground="#d0d7de", cursor="arrow")
            self.lab.configure(bg=fondo, fg="#7b8794" if self.stile == "primario" else grigio, cursor="arrow")

    def testo(self, t):
        self.lab.configure(text=t)


def badge(master, testo, tipo="info", dim=12):
    col = {"info": (C["primary"], C["tint"]), "ok": (C["ok"], C["ok_bg"]), "decl": (C["decl_txt"], "#f6e7c4"),
           "warn": (C["warn_txt"], C["warn_bg"]), "err": (C["err"], C["err_bg"]), "ai": (C["ai"], C["ai_bg"]),
           "grigio": (C["muted"], "#e9edf1")}[tipo]
    label=tk.Label(master, text=testo, font=F(dim, "semi"), fg=col[0], bg=col[1], padx=px(9), pady=px(3))
    from .icone import icona,categoria_da_testo
    label.image=icona(label,categoria_da_testo(testo),col[0],px(18))
    label.configure(image=label.image,compound="left")
    g=gestore(master)
    if g:
        root=master.winfo_toplevel();index=getattr(root,"_chip_index",0);root._chip_index=index+1
        if index<18:g.effetto(label,lambda n:label.configure(fg=mescola(C["muted"],col[0],n)),.18,ritardo=min(index*.03,.15))
    return label


class Casella(tk.Frame):
    """Casella di spunta disegnata (stessa resa su ogni sistema)."""
    def __init__(self, master, testo, variabile: tk.BooleanVar, comando=None, dim=15, peso="semi", wrap=None):
        bg = master.cget("bg")
        super().__init__(master, bg=bg, cursor="hand2", takefocus=1, highlightthickness=2,
                         highlightbackground=bg, highlightcolor=C["dark"])
        self.var, self.comando = variabile, comando
        s = px(20)
        self.cv = tk.Canvas(self, width=s, height=s, bg=bg, highlightthickness=0, cursor="hand2")
        self.cv.pack(side="left", anchor="n", pady=px(2))
        self.lab = etichetta(self, testo, dim, peso, bg=bg, wrap=wrap, cursor="hand2")
        self.lab.pack(side="left", padx=(px(9), 0), anchor="w")
        for w in (self, self.cv, self.lab):
            w.bind("<Button-1>", self._click)
        self.bind("<space>", self._click)
        self.bind("<Return>", self._click)
        self.bind("<FocusIn>", lambda e: rendi_visibile(self))
        self._disegna()

    def _click(self, _e=None):
        self.focus_set()
        self.var.set(not self.var.get())
        self._disegna()
        if self.comando:
            self.comando()
        return "break"

    def _disegna(self):
        s = px(20)
        self.cv.delete("all")
        if self.var.get():
            self.cv.create_rectangle(1, 1, s - 1, s - 1, fill=C["primary"], outline=C["primary"])
            self.cv.create_line(px(5), px(10), px(9), px(14), px(15), px(6), fill="white", width=max(2, px(2.4)))
        else:
            self.cv.create_rectangle(1, 1, s - 1, s - 1, fill="white", outline="#7b8794", width=max(1, px(1.5)))


class TestoLimitato(tk.Frame):
    """Campo di testo multi-riga con limite di caratteri e contatore «n / max caratteri»."""
    def __init__(self, master, massimo: int, righe: int = 3, testo: str = "", segnaposto: str = "", al_cambio=None):
        bg = master.cget("bg")
        super().__init__(master, bg=bg)
        self.massimo, self.al_cambio = massimo, al_cambio
        self.t = tk.Text(self, height=righe, wrap="word", font=F(15), relief="flat", highlightthickness=1,
                         highlightbackground="#b8c4cf", highlightcolor=C["primary"], padx=px(10), pady=px(8),
                         fg=C["text"], bg="white", insertbackground=C["text"], undo=True)
        self.t.pack(fill="both", expand=True)
        self.cont = etichetta(self, "", 12, colore=C["muted"], bg=bg)
        self.cont.pack(anchor="e", pady=(px(3), 0))
        if testo:
            self.t.insert("1.0", testo[:massimo])
        self.t.bind("<<Modified>>", self._mod)
        self.t.bind("<Tab>", lambda e: (self.t.tk_focusNext().focus_set(), "break")[1])
        self.t.bind("<Shift-Tab>", lambda e: (self.t.tk_focusPrev().focus_set(), "break")[1])
        self.t.bind("<FocusIn>", lambda e: rendi_visibile(self.t))
        self._aggiorna()

    def valore(self) -> str:
        return self.t.get("1.0", "end-1c")

    def imposta(self, s: str):
        self.t.delete("1.0", "end"); self.t.insert("1.0", s[: self.massimo])

    def _mod(self, _e=None):
        if not self.t.edit_modified():
            return
        v = self.valore()
        if len(v) > self.massimo:
            self.t.delete(f"1.0+{self.massimo}c", "end")
        self.t.edit_modified(False)
        self._aggiorna()
        if self.al_cambio:
            self.al_cambio()

    def _aggiorna(self):
        n = len(self.valore())
        self.cont.configure(text=f"{n} / {self.massimo} caratteri", fg=C["warn_txt"] if n >= self.massimo else C["muted"])


class Scorrevole(tk.Frame):
    """Contenitore con barra di scorrimento verticale (rotellina del mouse compresa)."""
    def __init__(self, master, bg=None):
        bg = bg or master.cget("bg")
        super().__init__(master, bg=bg)
        self.cv = tk.Canvas(self, bg=bg, takefocus=1, highlightthickness=2, highlightbackground=bg, highlightcolor=C["dark"])
        for key, step in (("<Next>", 1), ("<Prior>", -1)):
            self.cv.bind(key, lambda e, n=step: (self.cv.yview_scroll(n, "pages"), "break")[1])
        self.cv.bind("<Home>", lambda e: self.cv.yview_moveto(0))
        self.cv.bind("<End>", lambda e: self.cv.yview_moveto(1))
        self.sb = tk.Scrollbar(self, orient="vertical", command=self.cv.yview)
        self.dentro = tk.Frame(self.cv, bg=bg)
        self._id = self.cv.create_window((0, 0), window=self.dentro, anchor="nw")
        self.cv.configure(yscrollcommand=self.sb.set)
        self.cv.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")
        self.dentro.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.cv.bind("<Configure>", lambda e: self.cv.itemconfigure(self._id, width=e.width))
        for w in (self.cv, self.dentro):
            w.bind("<Enter>", lambda e: self._ruota(True))
            w.bind("<Leave>", lambda e: self._ruota(False))

    def _ruota(self, on):
        if on:
            self.cv.bind_all("<MouseWheel>", lambda e: self.cv.yview_scroll(int(-e.delta / 120), "units"))
            self.cv.bind_all("<Button-4>", lambda e: self.cv.yview_scroll(-2, "units"))
            self.cv.bind_all("<Button-5>", lambda e: self.cv.yview_scroll(2, "units"))
        else:
            for k in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                self.cv.unbind_all(k)


def _hm(s: str) -> int:
    return int(s[:2]) * 60 + int(s[3:5])


def barra_giornata(master, giornata, larghezza=820, altezza=34, ora_corrente: str | None = None, manuali=None,
                   compatta=False):
    """Barra delle fasce di 15 minuti (stato) con le attività dichiarate in oro sotto; ore in basso."""
    from resoconto.formati import minuti_da
    h0, h1 = giornata.ore_estremi() if giornata else (8, 16)
    W, H = px(larghezza), px(altezza)
    alt_tot = H + px(10 if compatta else 14) + px(16)
    cv = tk.Canvas(master, width=W, height=alt_tot, bg=master.cget("bg"), highlightthickness=0)
    m0, m1 = h0 * 60, h1 * 60
    x = lambda m: (m - m0) / (m1 - m0) * (W - 2) + 1     # noqa: E731
    cv.create_rectangle(1, 0, W - 1, H, fill=COLORI_STATO["sessione_chiusa"], outline=C["line"])
    if giornata:
        for f in giornata.fasce:
            a = minuti_da(f["inizio"]); b = minuti_da(f["fine"]) or 1440
            if b <= m0 or a >= m1:
                continue
            col = COLORI_STATO.get(f["stato"], "#eeeeee")
            cv.create_rectangle(x(a), 1, x(b), H - 1, fill=col, outline=col)
            if f["stato"] == "raccolta_sospesa":
                for k in range(int(x(a)), int(x(b)), px(6)):
                    cv.create_line(k, H - 1, min(k + px(6), x(b)), 1, fill="#d9c79d")
    for m in (manuali if manuali is not None else (giornata.d.get("manuali", []) if giornata else [])):
        a = minuti_da(m["inizio"]) if "inizio" in m else _hm(m["dalle"])
        b = (minuti_da(m["fine"]) or 1440) if "fine" in m else _hm(m["alle"])
        if b <= m0 or a >= m1:
            continue
        y = H + px(3)
        cv.create_rectangle(x(max(a, m0)), y, x(min(b, m1)), y + px(6), fill=C["decl"], outline=C["decl"])
    if ora_corrente:
        mc = _hm(ora_corrente)
        if m0 <= mc <= m1:
            cv.create_line(x(mc), 0, x(mc), H + px(8), fill=C["dark"], width=px(2))
    passo = 1 if W / max(1, h1 - h0) >= px(46) else 2 if W / max(1, h1 - h0) >= px(23) else 3
    for h in range(h0, h1 + 1, passo):
        xx = x(h * 60)
        cv.create_line(xx, H, xx, H + px(4), fill="#b8c4cf")
        cv.create_text(min(max(xx, px(14)), W - px(14)), alt_tot - px(7), text=f"{h:02d}:00", font=F(12), fill=C["muted"])
    return cv


def legenda(master, voci):
    fr = tk.Frame(master, bg=master.cget("bg"))
    for col, testo in voci:
        s = tk.Canvas(fr, width=px(12), height=px(12), bg=fr.cget("bg"), highlightthickness=0)
        s.create_rectangle(0, 0, px(12), px(12), fill=col, outline=col)
        s.pack(side="left", padx=(0, px(5)))
        etichetta(fr, testo, 12.5, colore=C["muted"]).pack(side="left", padx=(0, px(16)))
    return fr


def _percorso_esteso(path: str) -> str:
    """Risolve anche gli alias 8.3 prima di oscurare la cartella personale."""
    if os.name == "nt":
        import ctypes
        buf = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.kernel32.GetLongPathNameW(str(path), buf, len(buf)):
            return buf.value
    return str(path)


def percorso_breve(path: str) -> str:
    """Percorso da mostrare: la cartella personale diventa «…» (il nome utente non compare a video)."""
    casa = os.path.normcase(os.path.normpath(_percorso_esteso(os.path.expanduser("~"))))
    norm = os.path.normpath(_percorso_esteso(path))
    if casa and os.path.normcase(norm).startswith(casa + os.sep):
        return "…" + norm[len(casa):]
    return norm


def rendi_visibile(widget):
    """Porta in vista il controllo raggiunto con Tab nei pannelli scorrevoli."""
    parent = widget.master
    while parent is not None:
        if isinstance(parent, Scorrevole):
            parent.update_idletasks()
            y = widget.winfo_rooty() - parent.dentro.winfo_rooty()
            total = max(1, parent.dentro.winfo_height())
            top = parent.cv.canvasy(0)
            bottom = top + parent.cv.winfo_height()
            if y < top or y + widget.winfo_height() > bottom:
                parent.cv.yview_moveto(max(0, (y - 12) / total))
        parent = getattr(parent, "master", None)
