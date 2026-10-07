"""Collaudo ALFA 05/10/2026 — B3: la lettura «a consuntivo» è limitata all'orario della giornata (Avvia→Chiudi, escluse le pause)."""
import datetime as dt
import json
import os

import pytest

from applicazione.servizio import Servizio
from collector import giornata as cg
from collector.stato import FUSO

TZ = FUSO()


def T(h, m):
    return dt.datetime(2026, 10, 5, h, m, tzinfo=TZ)


class Orologio:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def test_eventi_prima_di_avvia_giornata_non_entrano_nel_resoconto(tmp_path, monkeypatch):
    oro = Orologio(T(14, 0))
    monkeypatch.setattr(cg, "_adesso", oro)
    base = str(tmp_path / "base")
    imp = {"modalita": "consuntivo", "server_ai": str(tmp_path / "x"), "modelli_ai": str(tmp_path / "m"), "cache_ai": str(tmp_path / "c"),
           "thread_ai": 2, "profilo_ai": None, "cartella_pdf": str(tmp_path / "pdf"), "profili_siti": [], "browser": True, "posta": False}

    def lettore(giorno):
        return {"eventi": [("web", T(9, 58), {"sito": "halley"}), ("web", T(14, 3), {"sito": "halley"})],
                "copertura": {"sessione": "parziale", "browser": "parziale", "attivita": "non_installato", "app": "non_installato",
                              "rete": "non_installato"}, "stato_iniziale": "attiva"}
    s = Servizio(base, imp, adesso=oro, lettore=lettore)
    s.registra_informativa("Prova (ESEMPIO)", "Ufficio")
    s.avvia()
    oro.t = T(14, 10)
    s.chiudi()
    with open(os.path.join(base, "giorni", "2026-10-05.json"), encoding="utf-8") as f:
        d = json.load(f)
    attive = [f["ora"] for f in d["fasce"] if f["stato"] == "attivita_rilevata"]
    assert attive == ["14:00"], attive           # oggi risulta ["09:45", "14:00"]
