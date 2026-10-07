"""Test delle modifiche approvate il 02/10/2026: «Pausa raccolta» (stato raccolta_sospesa), Halley come servizio web
(dominio in whitelist), siti riconosciuti per fascia, osservazioni ≤ 500 caratteri."""
import json

import pytest

from aggregatore import aggrega, mappa, modelli
from aggregatore.cli import validate
from test_aggregatore import A, G, S, meta, run, stato, ts

HALLEY = "gestionale.esempio.test"


def P(hm, ev):
    return {"tipo": "raccolta", "ts": ts(hm), "evento": ev}


def W(hm, **kw):
    return {"tipo": "web", "ts": ts(hm), **kw}


def fascia(doc, hm):
    return next(f for f in doc["fasce"] if f["ora"] == hm)


# ------------------------------------------------------------------------------------- pausa della raccolta
def test_pause_slots_are_raccolta_sospesa_and_summarised():
    doc = run([meta(), S("08:00", "accesso"), A("08:05"), P("09:00", "pausa"), P("09:40", "ripresa"), A("09:50")])
    assert stato(doc, "09:00") == stato(doc, "09:15") == "raccolta_sospesa"
    assert stato(doc, "09:30") == "raccolta_sospesa"           # 10 minuti di pausa su 15: prevale la pausa
    assert stato(doc, "09:45") == "attivita_rilevata"
    assert doc["raccolta"] == {"pause": [{"inizio": ts("09:00"), "fine": ts("09:40"), "dalle": "09:00", "alle": "09:40"}]}
    assert doc["totali"]["rilevati"]["fasce_per_stato"]["raccolta_sospesa"] == 3
    assert "inattiv" not in json.dumps(doc)


def test_short_pause_and_evidence_before_pause_keep_normal_rules():
    doc = run([meta(), S("08:00", "accesso"), A("08:02"), P("08:05", "pausa"), P("08:20", "ripresa"),
               P("09:10", "pausa"), P("09:15", "ripresa")])
    assert stato(doc, "08:00") == "attivita_rilevata"           # evidenza prima della pausa nella stessa fascia
    assert stato(doc, "09:00") == "nessuna_attivita_informatica_rilevata"   # 5 minuti: meno di metà fascia


def test_events_during_pause_are_discarded_with_warning():
    doc = run([meta(copertura_fonti={"sessione": "completa", "app": "parziale", "rete": "completa"}),
               S("08:00", "accesso"), P("09:00", "pausa"), A("09:05", "excel"), {"tipo": "rete", "ts": ts("09:10")},
               P("09:30", "ripresa")])
    assert stato(doc, "09:00") == "raccolta_sospesa"
    assert fascia(doc, "09:00")["app"] == [] and fascia(doc, "09:00")["rete"] == 0
    assert any("durante la pausa" in a for a in doc["avvisi"])
    assert doc["totali"]["rilevati"]["per_applicazione"] == []


def test_pause_open_until_midnight_and_from_previous_day():
    aperta = run([meta(), S("08:00", "accesso"), P("22:00", "pausa")])
    assert stato(aperta, "23:45") == "raccolta_sospesa" and aperta["raccolta"]["pause"][0]["alle"] == "24:00"
    ieri = run([meta(), {"tipo": "raccolta", "ts": "2026-10-04T20:00:00+02:00", "evento": "pausa"}, P("07:30", "ripresa")])
    assert stato(ieri, "00:00") == "raccolta_sospesa" and stato(ieri, "07:30") == "sessione_chiusa"
    assert ieri["raccolta"]["pause"][0]["dalle"] == "00:00"
    assert ieri["raccolta"]["pause"][0]["alle"] == "07:30"
    assert not any("fuori dalla giornata" in a for a in ieri["avvisi"])


def test_pause_does_not_alter_session_timeline():
    a = run([meta(), S("08:00", "accesso"), S("10:00", "chiusura")])
    b = run([meta(), S("08:00", "accesso"), P("08:30", "pausa"), P("09:00", "ripresa"), S("10:00", "chiusura")])
    assert a["sessione"] == b["sessione"]


def test_invalid_raccolta_event():
    with pytest.raises(modelli.ErroreIngresso):
        modelli.parse_records([meta(), {"tipo": "raccolta", "ts": ts("08:00"), "evento": "stop"}])


# ------------------------------------------------------------------------------------- Halley e siti
def test_halley_is_a_web_site_not_an_exe():
    mp = mappa.Mappa.predefinita()
    assert "HALLEY.EXE" not in mp.per_exe and mp.da_dominio(HALLEY) == "halley"
    assert mp.sito("halley") == ("Halley", "halley")


def test_domain_resolution_subdomain_and_unknown_dropped():
    doc = run([meta(), S("08:00", "accesso"), W("08:05", dominio=HALLEY), W("08:20", dominio="servizi.inps.it"),
               W("08:35", dominio="www.social-esempio.com")])
    assert fascia(doc, "08:00")["siti"] == ["halley"] and fascia(doc, "08:00")["categorie"] == ["halley"]
    assert fascia(doc, "08:15")["siti"] == []                     # bonifica B6: solo Halley in elenco
    assert fascia(doc, "08:30")["siti"] == [] and fascia(doc, "08:30")["categorie"] == ["web_generico"]
    s = json.dumps(doc)
    assert "social-esempio" not in s and "gestionale.esempio" not in s and "servizi.inps" not in s
    assert doc["classificazione"]["siti"]["halley"] == {"etichetta": "Halley", "categoria": "halley"}
    assert doc["totali"]["rilevati"]["per_sito"] == [{"sito": "halley", "fasce": 1}]


def test_browser_with_recognised_site_is_not_generic_navigation():
    doc = run([meta(), S("08:00", "accesso"), A("08:05", "browser"), W("08:05", dominio=HALLEY),
               A("08:20", "browser")])
    assert fascia(doc, "08:00")["categorie"] == ["halley"] and fascia(doc, "08:00")["app"] == ["browser"]
    assert fascia(doc, "08:15")["categorie"] == ["web_generico"]


def test_site_on_locked_session_not_recognised():
    doc = run([meta(), S("08:00", "accesso"), S("08:10", "blocco"), W("08:20", dominio=HALLEY)])
    assert fascia(doc, "08:15")["siti"] == [] and stato(doc, "08:15") == "sessione_bloccata"


@pytest.mark.parametrize("dom", ["https://gestionale.esempio.test", "gestionale.esempio.test/login", "halley"])
def test_mapping_rejects_urls_as_domains(dom):
    with pytest.raises(mappa.ErroreMappa):
        mappa.Mappa.da_dict({"siti": {"halley": {"etichetta": "Halley", "categoria": "halley", "domini": [dom]}}})


# ------------------------------------------------------------------------------------- osservazioni
def test_observations_max_500_with_warning():
    doc = aggrega.apply_review(run([meta()]), [], "o" * 700)
    assert len(doc["osservazioni_dipendente"]) == 500
    assert any("500" in a for a in doc["avvisi_revisione"])
    ok = aggrega.apply_review(run([meta()]), [], "breve")
    assert ok["avvisi_revisione"] == []


def test_schema_rejects_long_observations_and_accepts_new_fields():
    pytest.importorskip("jsonschema")
    doc = run([meta(), S("08:00", "accesso"), P("09:00", "pausa"), W("08:05", dominio=HALLEY)])
    assert validate(doc) == []
    doc["osservazioni_dipendente"] = "x" * 501
    assert validate(doc)


def test_istante_del_sigillo_valido():
    """Il sigillo rifiuta un istante non ISO 8601 e gli esempi hanno istanti validi."""
    import datetime as _dt
    import glob
    import os
    import json as _json
    import pytest as _pytest
    from aggregatore import sigillo as _s
    with _pytest.raises(ValueError):
        _s._seal({"a": 1}, "tecnico", None, "2026-10-05T14:1030:00+02:00")
    for p in glob.glob(os.path.join(os.path.dirname(__file__), "..", "examples", "*", "finale.json")):
        d = _json.load(open(p, encoding="utf-8"))
        for k in ("sigillo_tecnico", "sigillo_finale"):
            _dt.datetime.fromisoformat(d["integrita"][k]["creato_il"])
