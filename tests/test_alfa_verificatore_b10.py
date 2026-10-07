"""ALFA2 B10: motivi del verificatore — scrollbar visibile e 3º motivo non tagliato."""
from __future__ import annotations

import tkinter as tk

import pytest

from verificatore.gui import Verificatore


@pytest.fixture
def root():
    try:
        r = tk.Tk()
        r.withdraw()
    except tk.TclError:
        pytest.skip("Tk non disponibile")
    yield r
    try:
        r.destroy()
    except tk.TclError:
        pass


def test_motivi_hanno_scrollbar_visibile_con_tre_voci(root, monkeypatch):
    motivi = [
        "Il sigillo tecnico non corrisponde ai dati.",
        "Il sigillo finale non è presente.",
        "Il testo della pagina 2 non corrisponde ai dati sigillati (fascia oraria).",
    ]

    def fake_verifica(file, chiavi=None):
        return {
            "esito": "ALTERATO",
            "tipo": "pdf",
            "giorno": "2026-10-05",
            "dipendente": "Mario Rossi",
            "codice": "ABCD",
            "testo_pdf": "non corrispondente",
            "sigilli": {},
            "motivi": motivi,
        }

    monkeypatch.setattr("verificatore.gui.verifica_file", fake_verifica)
    v = Verificatore(root, chiavi=[], file="/tmp/fake.pdf")
    # cerca la Scrollbar nel corpo
    scrollbars = []
    canvases = []

    def walk(w):
        if isinstance(w, tk.Scrollbar):
            scrollbars.append(w)
        if isinstance(w, tk.Canvas):
            canvases.append(w)
        for c in w.winfo_children():
            walk(c)

    walk(v.corpo)
    assert scrollbars, "Scrollbar motivi assente"
    # la scrollbar deve essere mappata (pack/grid eseguito)
    assert any(sb.winfo_manager() for sb in scrollbars), "Scrollbar non visibile (non pack-ata)"
    # ALFA3 N3: area di testo a capo per parola, alta almeno 7 righe (3 motivi + spazio)
    t = v.testo_motivi
    assert t.cget("wrap") == "word" and int(t.cget("height")) >= 7
