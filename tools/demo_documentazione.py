"""Guardia obbligatoria prima delle catture di documentazione: percorsi solo fittizi.

La destinazione reale degli artefatti e le impostazioni del servizio non cambiano:
si sostituiscono solo i valori dei widget immediatamente prima di catturarli.
"""
from __future__ import annotations

import re
import sys

_PERCORSO = re.compile(
    r"(?i)(?:[a-z]:[\\/]|\\\\|(?:…|\.{3}|~)[\\/]|(?<![\w:/])/(?![/\s]))[^\r\n]*"
)
PDF = r"C:\Users\utente\Documents\Rendiconti lavoro agile"
REGISTRO = r"C:\Users\utente\Documents\Registro chiavi"
GENERIC = r"C:\Users\utente\Documents\Esempio"


def testo_esempio(testo: str) -> str:
    """Ogni percorso assoluto/abbreviato viene sostituito, anche se sconosciuto."""
    def replace(m):
        value = m.group().lower()
        if "registro" in value or "chiavi" in value:
            return REGISTRO
        if ".pdf" in value:
            return PDF + r"\resoconto_esempio.pdf"
        if "rendicont" in value or "pdf" in value:
            return PDF
        return GENERIC
    return _PERCORSO.sub(replace, str(testo))


def prepara_cattura(win) -> None:
    """Sanifica tutto l'albero Tk, inclusi Entry, Text, Canvas e variabili."""
    def walk(widget):
        yield widget
        for child in widget.winfo_children():
            yield from walk(child)

    def replace_widget(w):
        keys = w.keys()
        if "text" in keys:
            value = w.cget("text"); clean = testo_esempio(value)
            if clean != value:
                w.configure(text=clean)
        if "textvariable" in keys and w.cget("textvariable"):
            name = str(w.cget("textvariable"))
            value = w.getvar(name); clean = testo_esempio(value)
            if clean != str(value):
                w.setvar(name, clean)
        kind = w.winfo_class()
        if kind in ("Entry", "TEntry", "TCombobox", "Spinbox", "TSpinbox") and not ("textvariable" in keys and w.cget("textvariable")):
            value = w.get(); clean = testo_esempio(value)
            if clean != value:
                state = str(w.cget("state")); w.configure(state="normal")
                w.delete(0, "end"); w.insert(0, clean); w.configure(state=state)
        elif kind == "Text":
            value = w.get("1.0", "end-1c"); clean = testo_esempio(value)
            if clean != value:
                state = str(w.cget("state")); w.configure(state="normal")
                w.delete("1.0", "end"); w.insert("1.0", clean); w.configure(state=state)
        elif kind == "Canvas":
            for item in w.find_all():
                if w.type(item) == "text":
                    w.itemconfigure(item, text=testo_esempio(w.itemcget(item, "text")))
        elif kind == "Listbox":
            for i, value in enumerate(w.get(0, "end")):
                clean = testo_esempio(value)
                if clean != value:
                    w.delete(i); w.insert(i, clean)
        elif kind == "Treeview":
            def rows(parent=""):
                for item in w.get_children(parent):
                    info = w.item(item)
                    w.item(item, text=testo_esempio(info["text"]), values=tuple(testo_esempio(x) for x in info["values"]))
                    rows(item)
            rows()

    # Aggiornamenti pendenti prima della sanificazione, mai dopo il controllo finale.
    win.update()
    for w in walk(win):
        replace_widget(w)
    win.update_idletasks()
    for w in walk(win):
        replace_widget(w)
    win.update_idletasks()


def cattura_demo(win, path: str) -> None:
    """Unica via di cattura degli script screenshot/GIF, senza bypass configurabile."""
    prepara_cattura(win)
    if sys.platform == "win32":
        import ctypes
        hwnd = int(win.wm_frame(), 16)
        # PrintWindow può riusare pixel vecchi accanto al nuovo testo più corto.
        # Invalida e ridisegna anche tutti i controlli figli prima di acquisire.
        ctypes.windll.user32.RedrawWindow(hwnd, None, None, 0x0001 | 0x0004 | 0x0080 | 0x0100)
        ctypes.windll.user32.UpdateWindow(hwnd)
        from tools.cattura_finestra import _printwindow
        _printwindow(hwnd, str(path))
    else:
        from PIL import ImageGrab
        x, y, w, h = win.winfo_rootx(), win.winfo_rooty(), win.winfo_width(), win.winfo_height()
        ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(path)


def installa_guardia_testi() -> None:
    """Nei soli processi demo sanifica le etichette prima del primo disegno.

    Il controllo finale copre gli altri widget; questa guardia impedisce
    anche ai controlli trasparenti di conservare pixel di vecchi percorsi.
    """
    import tkinter as tk
    from tkinter import ttk
    for cls in (tk.Label, ttk.Label, tk.Message):
        if getattr(cls, "_guardia_demo", False):
            continue
        original_init = cls.__init__
        original_configure = cls.configure
        def init(self, master=None, cnf=None, _original=original_init, **kw):
            opts = dict(cnf or {}); opts.update(kw)
            if "text" in opts:
                opts["text"] = testo_esempio(opts["text"])
            demo_variable = None
            if opts.get("textvariable"):
                owner = master or tk._get_default_root()
                raw = owner.getvar(str(opts["textvariable"]))
                clean = testo_esempio(raw)
                if clean != raw:
                    demo_variable = tk.StringVar(owner, clean)
                    opts["textvariable"] = demo_variable
            _original(self, master, **opts)
            if demo_variable is not None:
                self._demo_variables = [demo_variable]
        def configure(self, cnf=None, _original=original_configure, **kw):
            if isinstance(cnf, str):
                return _original(self, cnf, **kw)
            opts = dict(cnf or {}); opts.update(kw)
            if "text" in opts:
                opts["text"] = testo_esempio(opts["text"])
            if opts.get("textvariable"):
                raw = self.getvar(str(opts["textvariable"]))
                clean = testo_esempio(raw)
                if clean != raw:
                    variable = tk.StringVar(self, clean)
                    opts["textvariable"] = variable
                    self._demo_variables = getattr(self, "_demo_variables", []) + [variable]
            return _original(self, **opts)
        cls.__init__ = init
        cls.configure = configure
        cls.config = configure
        cls._guardia_demo = True
