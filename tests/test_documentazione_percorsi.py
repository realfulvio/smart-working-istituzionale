"""Nessun percorso di un profilo reale nelle catture documentali."""
import tkinter as tk
from pathlib import Path

import pytest

from tools.demo_documentazione import testo_esempio as _testo_esempio, prepara_cattura, PDF, REGISTRO, GENERIC


@pytest.mark.parametrize("raw,expected", [
    (r"C:\Users\persona\AppData\Local\Temp\rendiconti", PDF),
    (r"C:\Users\PROFIL~1\AppData\Local\Temp\registro", REGISTRO),
    (r"\\server\riservato\cartella", GENERIC),
    ("/home/persona/documento.pdf", PDF + r"\resoconto_esempio.pdf"),
    (r"…\AppData\Local\Temp\registro", REGISTRO),
    ("/tmp/sessione", GENERIC),
    ("/radice-sconosciuta/persona/segreto", GENERIC),
    ("~/documenti", GENERIC),
])
def test_percorso_sconosciuto_diventa_esempio(raw, expected):
    assert _testo_esempio(raw) == expected
    assert _testo_esempio(expected) == expected


def test_cattura_copre_widget_variabili_e_canvas():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("Tk non disponibile")
    try:
        root.withdraw()
        raw = r"C:\Users\PROFIL~1\AppData\Local\Temp\registro"
        variable = tk.StringVar(root, raw)
        entry = tk.Entry(root); entry.insert(0, raw)
        label = tk.Label(root, textvariable=variable)
        text = tk.Text(root); text.insert("1.0", raw); text.configure(state="disabled")
        canvas = tk.Canvas(root); item = canvas.create_text(20, 20, text=raw)
        listbox = tk.Listbox(root); listbox.insert("end", raw)
        prepara_cattura(root)
        assert entry.get() == variable.get() == text.get("1.0", "end-1c") == REGISTRO
        assert canvas.itemcget(item, "text") == listbox.get(0) == REGISTRO
        assert str(text.cget("state")) == "disabled"
    finally:
        root.destroy()


def test_entrambi_gli_script_usano_solo_cattura_con_guardia():
    root = Path(__file__).resolve().parents[1]
    for name in ("schermate_documentazione.py", "crea_gif_documentazione.py"):
        source = (root / "tools" / name).read_text(encoding="utf-8")
        assert "tools.demo_documentazione import cattura_demo" in source
        assert "_printwindow" not in source
        assert "ImageGrab" not in source


def test_etichette_sanificate_prima_del_primo_disegno(monkeypatch):
    from tkinter import ttk
    from tools.demo_documentazione import installa_guardia_testi
    for cls in (tk.Label, ttk.Label, tk.Message):
        for name in ("__init__", "configure", "config"):
            monkeypatch.setattr(cls, name, getattr(cls, name))
        monkeypatch.setattr(cls, "_guardia_demo", False, raising=False)
    installa_guardia_testi()
    installa_guardia_testi()  # idempotente
    try:
        root = tk.Tk(); root.withdraw()
    except tk.TclError:
        pytest.skip("Tk non disponibile")
    try:
        for cls in (tk.Label, ttk.Label, tk.Message):
            label = cls(root, text=r"C:\Users\PROFIL~1\Temp\registro")
            assert label.cget("text") == REGISTRO
            label.configure(text=r"C:\Users\persona\documento.pdf")
            assert label.cget("text") == PDF + r"\resoconto_esempio.pdf"
            raw = r"C:\Users\PROFIL~1\Temp\registro"
            original = tk.StringVar(root, raw)
            bound = cls(root, textvariable=original)
            assert bound.getvar(str(bound.cget("textvariable"))) == REGISTRO
            assert original.get() == raw  # impostazioni del servizio intatte
            original.set(r"C:\Users\persona\documento.pdf")
            bound.configure(textvariable=original)
            assert bound.getvar(str(bound.cget("textvariable"))) == PDF + r"\resoconto_esempio.pdf"
    finally:
        root.destroy()
