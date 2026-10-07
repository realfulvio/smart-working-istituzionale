"""Collaudo ALFA3 B10/N3: tutti i motivi del verificatore leggibili (testo a capo, altezza, scorrimento) e rotella del
mouse attiva sull'area dei motivi (delta/120 su Windows, Button-4/5 su X11)."""
from __future__ import annotations

import tkinter as tk
from types import SimpleNamespace

import pytest

from verificatore import gui as vgui
from verificatore.gui import Verificatore, scatti_rotella

MOTIVI = [f"Motivo {i}: il testo della pagina {i} non corrisponde ai dati sigillati; contenuto aggiunto, coperto o "
          f"sostituito dopo il sigillo finale del dipendente (fascia {i})." for i in range(1, 13)]


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


def _verificatore(root, monkeypatch, motivi):
    monkeypatch.setattr(vgui, "verifica_file", lambda file, chiavi=None: {
        "esito": "ALTERATO", "tipo": "pdf", "giorno": "2026-10-06", "dipendente": "Mario Rossi", "codice": "ABCD",
        "testo_pdf": "non corrispondente", "sigilli": {}, "motivi": motivi})
    v = Verificatore(root, chiavi=[], file="/tmp/finto.pdf")
    v.win.deiconify()
    v.win.update()
    return v


@pytest.mark.parametrize("ev,atteso", [
    (SimpleNamespace(delta=-120, num=None), 1), (SimpleNamespace(delta=120, num=None), -1),
    (SimpleNamespace(delta=-360, num=None), 3), (SimpleNamespace(delta=-30, num=None), 1),
    (SimpleNamespace(delta=40, num=None), -1), (SimpleNamespace(delta=0, num=None), 0),
    (SimpleNamespace(delta=0, num=4), -1), (SimpleNamespace(delta=0, num=5), 1)])
def test_scatti_rotella(ev, atteso):
    assert scatti_rotella(ev) == atteso


def test_tutti_i_motivi_nel_testo_e_tre_visibili(root, monkeypatch):
    v = _verificatore(root, monkeypatch, MOTIVI[:4])
    t = v.testo_motivi
    contenuto = t.get("1.0", "end")
    assert all(m in contenuto for m in MOTIVI[:4]), "un motivo manca o è troncato nel testo"
    assert t.cget("wrap") == "word"
    # le prime tre righe logiche (motivi) sono visibili per intero senza scorrere
    t.update()
    for riga in (1, 2, 3):
        assert t.bbox(f"{riga}.0") is not None, f"motivo {riga} non visibile"
        assert t.bbox(f"{riga}.end - 1c") is not None, f"motivo {riga} tagliato"


def test_rotella_scorre_i_motivi(root, monkeypatch):
    v = _verificatore(root, monkeypatch, MOTIVI)
    t = v.testo_motivi
    t.update()
    assert t.yview()[1] < 1.0, "con 12 motivi lunghi serve lo scorrimento"
    prima = t.yview()[0]
    t.event_generate("<Enter>", x=5, y=5)
    for _ in range(3):
        t.event_generate("<MouseWheel>", delta=-120, x=5, y=5)
    t.update()
    assert t.yview()[0] > prima, "la rotella non scorre"
    # anche con l'evento consegnato a un altro widget (Windows: finestra col fuoco) mentre il puntatore è sull'area
    t.yview_moveto(0)
    altro = v.corpo
    altro.event_generate("<MouseWheel>", delta=-240, x=5, y=5)
    t.update()
    assert t.yview()[0] > 0, "bind_all della rotella non attivo con il puntatore sull'area"
    t.event_generate("<Leave>")
    t.yview_moveto(0)
    altro.event_generate("<MouseWheel>", delta=-240, x=5, y=5)
    t.update()
    assert t.yview()[0] == 0, "fuori dall'area la rotella non deve scorrere i motivi"


def test_testo_in_sola_lettura(root, monkeypatch):
    v = _verificatore(root, monkeypatch, MOTIVI[:3])
    assert v.testo_motivi.cget("state") == "disabled"
