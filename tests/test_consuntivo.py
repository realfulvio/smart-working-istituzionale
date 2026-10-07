"""M7 – chiusura «a consuntivo» con un lettore iniettato (dati sintetici). Bonifica: eliminati la cronologia dei
browser (B1) e la lettura retroattiva del registro eventi di Windows con il pacchetto ``consuntivo`` (B6b); il
meccanismo del lettore resta per i test e per il lettore dell'estensione."""
import datetime as dt
import json
import os
from zoneinfo import ZoneInfo

import pytest

from aggregatore.cli import validate
from aggregatore.mappa import Mappa
from collector import giornata
from collector.percorsi import Percorsi
from collector.registro import ErroreRegistro, controlla

TZ = ZoneInfo("Europe/Rome")
G = dt.date(2026, 10, 5)

def test_registro_web_solo_identificativo():
    assert controlla("web", {"sito": "halley"}) == {"sito": "halley"}
    for v in ("gestionale.esempio.test", "https://x/y", "Halley"):
        with pytest.raises(ErroreRegistro):
            controlla("web", {"sito": v})
    with pytest.raises(ErroreRegistro):
        controlla("web", {"dominio": "x.it"})


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("RSW_BASE", str(tmp_path))
    return Percorsi.predefiniti()


def T(hm):
    h, m = map(int, hm.split(":"))
    return dt.datetime.combine(G, dt.time(h, m), TZ)


def test_giornata_a_consuntivo_con_lettore(base, monkeypatch):
    orari = iter([T("08:00"), T("10:00"), T("10:30"), T("12:00")])
    monkeypatch.setattr(giornata, "_adesso", lambda: next(orari))
    giornata.avvia(base, presa_visione=True, lancia=False)
    giornata.pausa(base); giornata.riprendi(base, lancia=False)

    def lettore(g):
        assert g == G
        return {"eventi": [("sessione", T("08:01"), {"evento": "sblocco"}), ("web", T("08:20"), {"sito": "halley"}),
                           ("web", T("10:10"), {"sito": "halley"}), ("web", T("11:05"), {"sito": "halley"})],
                "copertura": {"sessione": "parziale", "browser": "parziale", "attivita": "non_installato",
                              "app": "non_installato", "rete": "non_installato"},
                "stato_iniziale": "bloccata"}
    r = giornata.chiudi(base, sigillo=False, lettore=lettore)
    doc = json.load(open(r["json"], encoding="utf-8"))
    assert validate(doc) == []
    assert doc["modalita"] == "consuntivo"
    assert doc["copertura_fonti"]["app"] == "non_installato" and doc["copertura_fonti"]["browser"] == "parziale"
    st = {f["ora"]: f["stato"] for f in doc["fasce"]}
    assert st["08:15"] == "attivita_rilevata" and st["10:00"] == "raccolta_sospesa"   # visita in pausa scartata
    assert st["11:00"] == "attivita_rilevata"
    assert "gestionale.esempio" not in json.dumps(doc)
