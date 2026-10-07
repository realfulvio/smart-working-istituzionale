"""Collaudo ALFA 05/10/2026 — correzioni B2/B5/B8/B12."""
import datetime as dt
import json
import os
import subprocess
import sys

import pytest

from applicazione.servizio import ErroreApp, Servizio
from collector import giornata as cg
from collector.stato import FUSO
from estensione import host as hostmod
from aggregatore.mappa import Mappa
from redattore import controllo, fatti

TZ = FUSO()


def T(h, m, giorno=dt.date(2026, 10, 5)):
    return dt.datetime.combine(giorno, dt.time(h, m), TZ)


class Orologio:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def _srv(tmp_path, oro, lettore=None):
    base = str(tmp_path / "base")
    imp = {"modalita": "consuntivo", "server_ai": str(tmp_path / "x"), "modelli_ai": str(tmp_path / "m"),
           "cache_ai": str(tmp_path / "c"), "thread_ai": 2, "profilo_ai": None,
           "cartella_pdf": str(tmp_path / "pdf"), "profili_siti": []}
    return Servizio(base, imp, adesso=oro, lettore=lettore or (lambda g: {
        "eventi": [], "copertura": {"sessione": "parziale", "browser": "non_installato", "attivita": "non_installato",
                                    "app": "non_installato", "rete": "non_installato"}, "stato_iniziale": "attiva"}))


def test_b2_fallimento_pdf_non_marca_salvato(tmp_path, monkeypatch):
    """Se crea_pdf fallisce non deve restare il JSON finale né «oggi_concluso»."""
    oro = Orologio(T(9, 0))
    monkeypatch.setattr(cg, "_adesso", oro)
    s = _srv(tmp_path, oro)
    s.registra_informativa("Prova (ESEMPIO)", "Ufficio")
    s.avvia()
    oro.t = T(12, 0)
    s.chiudi()
    g = "2026-10-05"
    s.genera(g)
    def boom(*a, **k):
        raise RuntimeError("No module named 'reportlab.graphics.barcode.code128'")
    monkeypatch.setattr("resoconto.pdf.crea_pdf", boom)
    with pytest.raises(RuntimeError, match="reportlab"):
        s.conferma(g, True)
    assert not os.path.exists(s._f_finale(g))
    st = s.stato()
    assert st["oggi_concluso"] is False
    assert g in st["da_confermare"]


def test_b8_non_rilevata_non_e_falso_positivo():
    """«un'attività non rilevata…» non deve scattare «descritta come rilevata»."""
    from tests.test_redattore import rivisto
    fs = fatti.estrai(rivisto())
    # solo fatti dichiarati citati + testo con negazione
    dich = [f for f in fs if f["origine"] == "dichiarato"]
    assert dich, "servono fatti dichiarati nel campione"
    ids = [dich[0]["id"]]
    frasi = [{"testo": "Il dipendente ha dichiarato un'attività non rilevata dalle 14:20 alle 15:00.", "fatti": ids}]
    r = controllo.controlla(frasi, fs, min_frasi=1, max_frasi=8)
    assert not any("descritta come «rilevata»" in p for p in r["problemi"]), r["problemi"]


def test_b12_host_accetta_fascia_parziale_dopo_chiusura(tmp_path, monkeypatch):
    base_p = tmp_path / "rsw"
    monkeypatch.setenv("RSW_BASE", str(base_p))
    from collector.percorsi import Percorsi
    p = Percorsi.predefiniti()
    oro = Orologio(T(14, 0))
    monkeypatch.setattr(cg, "_adesso", oro)
    cg.avvia(p, presa_visione=True, lancia=False)
    oro.t = T(14, 38)
    # chiudi marca subito fase=chiusa
    g = __import__("collector.stato", fromlist=["Stato"]).Stato(p).giornata()
    g["fase"] = "chiusa"
    g["fasi"][-1]["chiusura"] = oro.t.replace(microsecond=0).isoformat()
    __import__("collector.stato", fromlist=["Stato"]).Stato(p).salva_giornata(g)
    h = hostmod.Host(p, {"estensione_browser": True}, Mappa.predefinita(), adesso=oro)
    # fascia 14:30–14:45 ancora aperta a 14:38
    ts = int(T(14, 30).timestamp())
    r = h.fascia({"cmd": "fascia", "ts": ts, "sito": "halley", "campioni": 12, "parziale": True})
    assert r.get("ok") is True, r
    # senza parziale la stessa fascia futura verrebbe rifiutata
    r2 = h.fascia({"cmd": "fascia", "ts": ts, "sito": "halley", "campioni": 12})
    assert r2.get("rifiutato") == "fascia_fuori_periodo"


def test_b5_termina_solo_eseguibile_nostro(tmp_path):
    from redattore import motore
    altro = tmp_path / "altro-llama-server"
    altro.write_text("x", encoding="utf-8")
    nostro = tmp_path / "llama-server"
    nostro.write_text("y", encoding="utf-8")
    # nessun processo reale con quel path: lista vuota
    assert motore.processi_con_eseguibile(str(nostro)) == []
    assert motore.termina_llama_orfani(str(nostro)) == []
