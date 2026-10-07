"""Test delle regole dell'aggregatore e dei casi limite (schema/giornaliero.schema.json)."""
import copy
import datetime as dt
import json
import os
import random

import pytest

from aggregatore import aggrega, modelli, sigillo
from aggregatore.cli import main, validate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G = "2026-10-05"


def ts(hm, g=G, off="+02:00"):
    return f"{g}T{hm}:00{off}"


def meta(**kw):
    m = {"tipo": "meta", "giorno": G, "copertura_fonti": {"sessione": "completa", "app": "parziale",
                                                          "posta": "completa"}, "stato_iniziale_sessione": "chiusa"}
    m.update(kw)
    return m


def run(recs, manuali=()):
    inp = modelli.parse_records(recs)
    doc = aggrega.aggregate(inp)
    if manuali:
        doc = aggrega.apply_review(doc, modelli.parse_records([{"tipo": "meta", "giorno": G}, *manuali]).manuali)
    return doc


def stato(doc, hm):
    return next(f["stato"] for f in doc["fasce"] if f["ora"] == hm)


def S(hm, ev):
    return {"tipo": "sessione", "ts": ts(hm), "evento": ev}


def A(hm, app="word"):
    return {"tipo": "app", "ts": ts(hm), "app": app}


@pytest.fixture
def key(tmp_path):
    return sigillo.load_or_create_key(str(tmp_path / "k"), {"account": "ENTE\\prova", "pc": "PC-1"})


# ------------------------------------------------------------------------------------------- ingresso
def test_ts_without_timezone_rejected():
    with pytest.raises(modelli.ErroreIngresso, match="fuso"):
        modelli.parse_records([meta(), {"tipo": "app", "ts": "2026-10-05T08:00:00", "app": "word"}])


def test_meta_required_and_unique():
    with pytest.raises(modelli.ErroreIngresso, match="meta"):
        modelli.parse_records([A("08:00")])
    with pytest.raises(modelli.ErroreIngresso, match="più di un"):
        modelli.parse_records([meta(), meta()])


@pytest.mark.parametrize("rec", [
    {"tipo": "sessione", "ts": ts("08:00"), "evento": "boh"},
    {"tipo": "manuale", "inizio": ts("09:00"), "fine": ts("08:00"), "categoria": "riunione"},
    {"tipo": "manuale", "inizio": ts("08:00"), "fine": ts("09:00"), "categoria": "pausa_caffe"},
    {"tipo": "app", "ts": ts("08:00")},
])
def test_invalid_records_rejected(rec):
    with pytest.raises(modelli.ErroreIngresso):
        modelli.parse_records([meta(), rec])


def test_unknown_type_is_warning_not_error():
    doc = run([meta(), {"tipo": "telemetria_x", "ts": ts("08:00")}])
    assert any("sconosciuto" in a for a in doc["avvisi"])


# ------------------------------------------------------------------------------------------- fasce
def test_96_slots_and_dst_days():
    assert len(run([meta()])["fasce"]) == 96
    autunno = run([meta(giorno="2026-10-25")])          # torna l'ora solare: 25 ore
    primavera = run([meta(giorno="2026-03-29")])        # ora legale: 23 ore
    assert len(autunno["fasce"]) == 100 and len(primavera["fasce"]) == 92
    ore = [f["ora"] for f in autunno["fasce"]]
    assert ore.count("02:00") == 2                      # ora ripetuta, ma inizio (con offset) distinto
    inizi = [f["inizio"] for f in autunno["fasce"] if f["ora"] == "02:00"]
    assert inizi[0].endswith("+02:00") and inizi[1].endswith("+01:00")
    assert autunno["totali"]["rilevati"]["numero_fasce"] == 100


def test_slot_states_basic_day():
    doc = run([meta(), S("08:00", "accesso"), A("08:05"), S("09:00", "blocco"), S("09:30", "sblocco"),
               A("10:40"), S("12:00", "chiusura")])
    assert stato(doc, "07:45") == "sessione_chiusa"
    assert stato(doc, "08:00") == "attivita_rilevata"
    assert stato(doc, "08:30") == "nessuna_attivita_informatica_rilevata"   # vuoto con sessione attiva
    assert stato(doc, "09:00") == "sessione_bloccata"
    assert stato(doc, "09:15") == "sessione_bloccata"
    assert stato(doc, "10:30") == "attivita_rilevata"
    assert stato(doc, "12:00") == "sessione_chiusa"


def test_gap_never_inactive_wording():
    doc = run([meta(), S("08:00", "accesso"), A("08:05"), A("11:00")])
    assert "inattiv" not in json.dumps(doc)
    assert set(doc["totali"]["rilevati"]["fasce_per_stato"]) == set(aggrega.STATI_FASCIA)


def test_unknown_session_without_evidence_is_not_available():
    doc = run([meta(stato_iniziale_sessione="sconosciuta"), A("10:05")])
    assert stato(doc, "09:00") == "dato_non_disponibile"
    assert stato(doc, "10:00") == "attivita_rilevata"
    assert stato(doc, "11:00") == "dato_non_disponibile"       # l'evidenza non «inventa» una sessione


def test_active_session_but_no_activity_sources_is_not_available():
    m = meta(copertura_fonti={"sessione": "completa", "app": "non_installato", "posta": "non_disponibile",
                              "attivita": "non_installato", "browser": "non_installato"})
    doc = run([m, S("08:00", "accesso"), S("12:00", "chiusura")])
    assert stato(doc, "09:00") == "dato_non_disponibile"
    assert stato(doc, "13:00") == "sessione_chiusa"


def test_majority_rule_and_tie_priority():
    # 08:00-08:15: 10 min attiva (senza evidenze) + 5 min bloccata -> prevale attiva
    doc = run([meta(), S("08:00", "accesso"), S("08:10", "blocco"), S("08:20", "sblocco")])
    assert stato(doc, "08:00") == "nessuna_attivita_informatica_rilevata"
    # 08:15-08:30: 5 min bloccata + 10 attiva -> nessuna_attivita
    assert stato(doc, "08:15") == "nessuna_attivita_informatica_rilevata"
    # parità 7,5/7,5 non possibile al minuto: uso secondi
    doc2 = run([meta(), {"tipo": "sessione", "ts": "2026-10-05T08:00:00+02:00", "evento": "accesso"},
                {"tipo": "sessione", "ts": "2026-10-05T08:07:30+02:00", "evento": "blocco"}])
    assert stato(doc2, "08:00") == "sessione_bloccata"         # a parità vince bloccata (PRIORITA)


def test_lock_vs_vdi_disconnect_vs_sleep():
    doc = run([meta(), S("08:00", "accesso"), A("08:01"), S("09:00", "blocco"), S("09:30", "sblocco"),
               S("10:00", "disconnessione"), S("10:30", "riconnessione"), S("11:00", "sospensione"),
               S("11:30", "ripresa"), S("11:31", "sblocco")])
    assert stato(doc, "09:00") == "sessione_bloccata"
    assert stato(doc, "10:00") == "sessione_disconnessa"       # disconnessione VDI: stato a sé (decisione M1)
    assert stato(doc, "11:00") == "sessione_chiusa"            # sospensione/ibernazione: postazione ferma
    assert "minuti_per_stato" not in doc["sessione"]
    fp = doc["totali"]["rilevati"]["fasce_per_stato"]
    assert fp["sessione_bloccata"] == fp["sessione_disconnessa"] == 2


def test_midnight_crossing_initial_state_from_previous_day():
    doc = run([meta(stato_iniziale_sessione="sconosciuta"),
               {"tipo": "sessione", "ts": "2026-10-04T23:30:00+02:00", "evento": "accesso"},
               {"tipo": "app", "ts": "2026-10-04T23:50:00+02:00", "app": "word"},
               S("00:20", "blocco")])
    assert doc["sessione"]["stato_iniziale"] == "attiva"
    assert stato(doc, "00:00") == "nessuna_attivita_informatica_rilevata"
    assert stato(doc, "00:30") == "sessione_bloccata"
    assert any("fuori dalla giornata" in a for a in doc["avvisi"])    # l'evento app del giorno prima
    assert all(e["ts"].startswith(G) for e in doc["sessione"]["eventi"])


def test_events_after_midnight_belong_to_next_day():
    doc = run([meta(), S("23:50", "accesso"), {"tipo": "app", "ts": "2026-10-06T00:05:00+02:00", "app": "word"}])
    assert stato(doc, "23:45") == "nessuna_attivita_informatica_rilevata"
    assert doc["totali"]["rilevati"]["fasce_per_stato"]["attivita_rilevata"] == 0


def test_other_offset_is_converted():
    # stesso istante scritto in UTC
    doc = run([meta(), S("08:00", "accesso"), {"tipo": "app", "ts": "2026-10-05T07:05:00+00:00", "app": "word"}])
    assert stato(doc, "09:00") == "attivita_rilevata"


def test_implicit_unlock_when_unlock_event_missing():
    doc = run([meta(), S("08:00", "accesso"), A("08:01"), S("09:00", "blocco"), A("10:10")])
    assert stato(doc, "09:30") == "sessione_bloccata"
    assert stato(doc, "10:00") == "attivita_rilevata"
    assert stato(doc, "10:30") == "nessuna_attivita_informatica_rilevata"   # dopo lo sblocco implicito
    ev = [e for e in doc["sessione"]["eventi"] if e.get("implicito")]
    assert len(ev) == 1 and ev[0]["ora"] == "10:10"
    assert any("sblocchi impliciti" in a for a in doc["avvisi"])


def test_multiple_sessions_in_a_day():
    doc = run([meta(), S("08:00", "accesso"), A("08:05"), S("10:00", "chiusura"), S("14:00", "accesso"),
               A("14:05"), S("16:00", "chiusura")])
    assert stato(doc, "11:00") == "sessione_chiusa"
    assert stato(doc, "14:00") == "attivita_rilevata"
    assert stato(doc, "16:00") == "sessione_chiusa"
    assert doc["sessione"]["primo_evento"] == "08:00" and doc["sessione"]["ultimo_evento"] == "16:00"


def test_old_mail_lines_ignored_and_network_is_not_activity():
    """Bonifica B2: le righe «posta» di vecchi grezzi non producono dati, categorie o attività."""
    doc = run([meta(copertura_fonti={"sessione": "completa", "app": "parziale", "posta": "completa", "rete": "completa"}),
               S("08:00", "accesso"),
               {"tipo": "posta", "ts": ts("08:20"), "direzione": "ricevuta", "categoria": "Re: ferie Rossi"},
               {"tipo": "rete", "ts": ts("08:50"), "byte": 50000},
               {"tipo": "posta", "ts": ts("09:20"), "direzione": "inviata"}])
    assert stato(doc, "08:15") == "nessuna_attivita_informatica_rilevata"
    assert stato(doc, "08:45") == "nessuna_attivita_informatica_rilevata"
    f = next(x for x in doc["fasce"] if x["ora"] == "08:45")
    assert f["rete"] == 1 and f["evidenze"] == {"rete": 1} and f["categorie"] == ["rete"]
    assert stato(doc, "09:15") == "nessuna_attivita_informatica_rilevata"
    assert "posta" not in doc and "Rossi" not in json.dumps(doc)
    assert sum("posta" in a for a in doc["avvisi"]) == 1


def test_clock_change_and_duplicates_warned():
    doc = run([meta(), S("08:00", "accesso"), A("08:05"), A("08:05"),
               {"tipo": "orologio", "ts": ts("09:00"), "delta_s": 3600}])
    assert any("duplicati" in a for a in doc["avvisi"])
    assert any("ora di sistema" in a for a in doc["avvisi"])
    small = run([meta(), {"tipo": "orologio", "ts": ts("09:00"), "delta_s": 5}])
    assert not any("ora di sistema" in a for a in small["avvisi"])


def test_missing_sources_marked_in_coverage():
    doc = run([{"tipo": "meta", "giorno": G}, A("08:00")])
    c = doc["copertura_fonti"]
    assert c["app"] == "parziale" and c["sessione"] == "non_disponibile" and "posta" not in c


# ------------------------------------------------------------------------------------------- applicazioni
def test_apps_counted_once_per_slot_and_totals():
    doc = run([meta(), S("08:00", "accesso")] + [A(f"08:{m:02d}") for m in range(0, 15)]
              + [A("08:20", "excel"), A("08:25", "word"), A("09:10", "excel")])
    f = next(x for x in doc["fasce"] if x["ora"] == "08:00")
    assert f["app"] == ["word"] and f["evidenze"]["app"] == 15
    pa = {x["app"]: x for x in doc["totali"]["rilevati"]["per_applicazione"]}
    assert pa["word"] == {"app": "word", "fasce": 2}
    assert pa["excel"] == {"app": "excel", "fasce": 2}
    # Segnali sovrapposti: nessuna durata e nessuna somma temporale.
    assert all("minuti" not in x for x in pa.values())
    assert doc["totali"]["rilevati"]["fasce_per_stato"]["attivita_rilevata"] == 3


def test_first_last_activity_and_24_00():
    doc = run([meta(), S("08:00", "accesso"), A("08:05"), A("23:50")])
    r = doc["totali"]["rilevati"]
    assert r["prima_attivita"] == "08:00" and r["ultima_attivita"] == "24:00"


# ------------------------------------------------------------------------------------------- manuali
def M(a, b, cat="riunione", d=""):
    return {"tipo": "manuale", "inizio": ts(a), "fine": ts(b), "categoria": cat, "descrizione": d}


def test_manual_union_counted_once():
    base = [meta(), S("08:00", "accesso"), A("08:05"), A("08:20"), S("12:00", "chiusura")]
    doc = run(base, [M("08:15", "09:00"), M("08:45", "09:30", "telefonata"), M("10:00", "10:30", "cartaceo")])
    c = doc["totali"]["con_manuali"]
    # Tre dichiarazioni distinte, senza totale combinato con i segnali.
    assert c == {"numero_attivita_dichiarate": 3}
    assert all(x["origine"] == "dichiarata" for x in doc["manuali"])
    assert [x["id"] for x in doc["manuali"]] == ["m1", "m2", "m3"]


def test_manual_does_not_change_slot_states():
    base = [meta(), S("08:00", "accesso"), A("08:05")]
    a = run(base)
    b = run(base, [M("09:00", "11:00")])
    assert a["fasce"] == b["fasce"] and a["totali"]["rilevati"] == b["totali"]["rilevati"]
    assert sigillo.parte_tecnica(a) == sigillo.parte_tecnica(b)


def test_manual_clipped_at_midnight_and_outside_dropped():
    doc = run([meta()], [{"tipo": "manuale", "inizio": ts("23:30"), "fine": "2026-10-06T00:30:00+02:00",
                          "categoria": "altro"},
                         {"tipo": "manuale", "inizio": "2026-10-06T09:00:00+02:00", "fine": "2026-10-06T10:00:00+02:00",
                          "categoria": "altro"}])
    assert len(doc["manuali"]) == 1 and doc["manuali"][0]["minuti"] == 30 and doc["manuali"][0]["ritagliata"]
    assert len(doc["avvisi_revisione"]) == 2


def test_manual_description_truncated():
    doc = run([meta()], [M("09:00", "10:00", d="x" * 500)])
    assert len(doc["manuali"][0]["descrizione"]) == modelli.MAX_DESCRIZIONE


# ------------------------------------------------------------------------------------------- privacy
SEGRETI = ["C:\\Users\\x\\stipendi.xlsx", "Oggetto riservato", "https://www.facebook.com/", "mario@esempio.it"]


def _keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from _keys(v)


def test_forbidden_fields_never_in_output():
    doc = run([meta(), S("08:00", "accesso"),
               {"tipo": "app", "ts": ts("08:05"), "app": "excel", "file": SEGRETI[0], "path": SEGRETI[0]},
               {"tipo": "posta", "ts": ts("08:10"), "direzione": "inviata", "oggetto": SEGRETI[1],
                "destinatario": SEGRETI[3]},
               {"tipo": "app", "ts": ts("08:20"), "app": "browser", "url": SEGRETI[2]}])
    s = json.dumps(doc, ensure_ascii=False)
    for x in SEGRETI:
        assert x not in s
    assert not set(_keys(doc)) & modelli.CAMPI_VIETATI
    assert sum("campo vietato" in a for a in doc["avvisi"]) == 5


@pytest.mark.parametrize("app", ["Relazione finale.docx", "c:\\temp\\x", "www.sito.it", "a" * 41])
def test_app_names_must_be_identifiers(app):
    doc = run([meta(), S("08:00", "accesso"), {"tipo": "app", "ts": ts("08:05"), "app": app}])
    assert app.lower() not in json.dumps(doc) and doc["totali"]["rilevati"]["per_applicazione"] == []




# ------------------------------------------------------------------------------------------- determinismo
def test_deterministic_and_order_independent():
    recs = [meta(), S("08:00", "accesso"), A("08:05"), S("09:00", "blocco"), A("10:00", "excel"),
            {"tipo": "posta", "ts": ts("08:30"), "direzione": "inviata", "categoria": "protocollo"}, S("12:00", "chiusura")]
    a = run(recs)
    shuffled = recs[:1] + random.Random(4).sample(recs[1:], len(recs) - 1)
    assert run(shuffled) == a == run(copy.deepcopy(recs))


# ------------------------------------------------------------------------------------------- sigilli
def test_canonical_json_format():
    assert sigillo.canonical({"b": 1, "a": "è", "c": [1, {"z": None, "y": True}]}) == \
        '{"a":"è","b":1,"c":[1,{"y":true,"z":null}]}'.encode("utf-8")
    with pytest.raises(ValueError):
        sigillo.canonical({"x": float("nan")})


def _sealed(key):
    doc = run([meta(), S("08:00", "accesso"), A("08:05"), S("12:00", "chiusura")])
    return sigillo.seal_technical(doc, key, "2026-10-05T12:10:00+02:00")


def test_two_stage_seal_roundtrip(key, tmp_path):
    d1 = _sealed(key)
    assert sigillo.verify(d1)["esito"] == "INTEGRO" and sigillo.verify(d1)["fase"] == "tecnica"
    man = modelli.parse_records([{"tipo": "meta", "giorno": G}, M("13:00", "14:00", "telefonata")]).manuali
    d2 = aggrega.apply_review(d1, man, "osservazione")
    r = sigillo.verify(d2)
    assert r["tecnico"]["valido"] and r["esito"] == "INTEGRO"           # revisione non rompe il sigillo tecnico
    d3 = sigillo.seal_final(d2, key, "2026-10-05T12:20:00+02:00")
    reg = tmp_path / "reg"
    reg.mkdir()
    (reg / "k.json").write_text(open(tmp_path / "k" / "pubblica.json", encoding="utf-8").read(), encoding="utf-8")
    r = sigillo.verify(d3, [str(reg)])
    assert r["esito"] == "VALIDO" and r["fase"] == "finale" and r["finale"]["valido"]
    # il sigillo finale copre l'hash del tecnico
    assert d3["integrita"]["sigillo_tecnico"]["sha256"] in json.dumps(sigillo.payload_finale(d3))


@pytest.mark.parametrize("mutate", [
    lambda d: d["fasce"][40].update(stato="attivita_rilevata"),
    lambda d: d["totali"]["rilevati"].update(minuti_attivita_rilevata=999),
    lambda d: d["sessione"]["eventi"].pop(),
    lambda d: d["dipendente"].update(nome="Altro Nome"),
    lambda d: d["presa_visione"] or d.update(presa_visione={"versione": "x", "data": "y"}),
])
def test_tamper_technical_detected(key, mutate):
    d = _sealed(key)
    mutate(d)
    assert sigillo.verify(d)["esito"] == "ALTERATO"


def test_tamper_after_final_seal_detected(key):
    d = sigillo.seal_final(aggrega.apply_review(_sealed(key), [], "ok"), key)
    for mutate in (lambda x: x.update(osservazioni_dipendente="cambiato"),
                   lambda x: x["integrita"]["sigillo_tecnico"].update(codice="AAAA-AAAA-AAAA"),
                   lambda x: x["manuali"].append({"id": "m9", "categoria": "altro", "inizio": ts("15:00"),
                                                  "fine": ts("16:00"), "minuti": 60, "descrizione": "",
                                                  "origine": "dichiarata"})):
        x = copy.deepcopy(d)
        mutate(x)
        assert sigillo.verify(x)["esito"] == "ALTERATO"


def test_seal_final_refuses_tampered_technical(key):
    d = _sealed(key)
    d["fasce"][50]["stato"] = "attivita_rilevata"
    with pytest.raises(ValueError, match="parte tecnica"):
        sigillo.seal_final(d, key)
    with pytest.raises(ValueError, match="manca il sigillo tecnico"):
        sigillo.seal_final(run([meta()]), key)


def test_resealed_with_other_key_is_not_valid(key, tmp_path):
    d = _sealed(key)
    reg = tmp_path / "reg"
    reg.mkdir()
    (reg / "k.json").write_text(open(tmp_path / "k" / "pubblica.json", encoding="utf-8").read(), encoding="utf-8")
    assert d["fasce"][60]["stato"] == "sessione_chiusa"            # 15:00, dopo la chiusura
    d["fasce"][60]["stato"] = "attivita_rilevata"                   # falsario coerente: ritocca anche i totali
    d["totali"]["rilevati"] = aggrega.compute_rilevati(d["fasce"], d["giorno"], d["fuso"])
    d["totali"]["con_manuali"] = aggrega.compute_con_manuali(d)
    other = sigillo.load_or_create_key(str(tmp_path / "altra"), {"account": "ENTE\\prova", "pc": "PC-2"})
    forged = sigillo.seal_technical(d, other)
    r = sigillo.verify(forged, [str(reg)])
    assert r["esito"] == "INTEGRO"                                   # firma coerente ma chiave non registrata
    assert sigillo.verify(_sealed(key), [str(reg)])["esito"] == "VALIDO"


@pytest.mark.parametrize("campo,valore", [("minuti_attivita_rilevata", 999), ("prima_attivita", "06:00"),
                                          ("per_applicazione", [{"app": "word", "fasce": 40, "minuti": 600}])])
def test_any_incoherent_total_detected(key, campo, valore):
    d = run([meta(), S("08:00", "accesso"), A("08:05")])
    d["totali"]["rilevati"][campo] = valore
    r = sigillo.verify(sigillo.seal_technical(d, key))
    assert r["esito"] == "ALTERATO" and any("non coerenti" in m for m in r["motivi"])


def test_incoherent_totals_detected_even_if_resealed(key):
    d = run([meta(), S("08:00", "accesso"), A("08:05")])
    d["totali"]["rilevati"]["fasce_per_stato"]["attivita_rilevata"] = 40
    assert sigillo.verify(sigillo.seal_technical(d, key))["esito"] == "ALTERATO"


def test_registry_account_mismatch(key, tmp_path):
    reg = tmp_path / "reg"
    reg.mkdir()
    j = json.load(open(tmp_path / "k" / "pubblica.json", encoding="utf-8"))
    j["account"] = "ENTE\\qualcunaltro"
    (reg / "k.json").write_text(json.dumps(j), encoding="utf-8")
    # Schema /4 identifica la chiave mediante impronta, senza account tecnico.
    assert sigillo.verify(_sealed(key), [str(reg)])["esito"] == "VALIDO"


def test_unsealed():
    assert sigillo.verify(run([meta()]))["esito"] == "NON SIGILLATO"


def test_key_reused_and_compatible_with_v3_fingerprint(tmp_path):
    k1 = sigillo.load_or_create_key(str(tmp_path / "k"), {"account": "a", "pc": "b"})
    k2 = sigillo.load_or_create_key(str(tmp_path / "k"))
    assert k1.public_raw == k2.public_raw and len(k1.impronta) == 24
    assert open(tmp_path / "k" / "privata.bin", "rb").read()[:5] in (b"PLAIN", b"DPAPI")


# ------------------------------------------------------------------------------------------- schema ed esempi
EXAMPLES = ["01_giornata_ufficio", "02_pause_lunghe_pranzo", "03_vdi_disconnessioni"]


@pytest.mark.parametrize("name", EXAMPLES)
def test_examples_conform_and_verify(name):
    pytest.importorskip("jsonschema")
    d = os.path.join(ROOT, "examples", name)
    for f in ("giorno", "rivisto", "finale"):
        assert validate(json.load(open(os.path.join(d, f + ".json"), encoding="utf-8"))) == []
    fin = json.load(open(os.path.join(d, "finale.json"), encoding="utf-8"))
    assert sigillo.verify(fin, [os.path.join(ROOT, "examples", "chiavi_registrate")])["esito"] == "VALIDO"


@pytest.mark.parametrize("name", EXAMPLES)
def test_examples_reproducible(name):
    d = os.path.join(ROOT, "examples", name)
    doc = aggrega.aggregate(modelli.read_jsonl(os.path.join(d, "raw.jsonl")))
    committed = json.load(open(os.path.join(d, "giorno.json"), encoding="utf-8"))
    # Fixture /3 conservata; nuova aggregazione /4 deterministica con stessi segnali.
    assert doc == aggrega.aggregate(modelli.read_jsonl(os.path.join(d, "raw.jsonl")))
    assert [{k: v for k, v in f.items() if k != "rete"} for f in doc["fasce"]] == [{k: v for k, v in f.items() if k != "rete"} for f in committed["fasce"]]
    assert [bool(f["rete"]) for f in committed["fasce"]] == [f["rete"] for f in doc["fasce"]]


def test_schema_rejects_extra_fields():
    pytest.importorskip("jsonschema")
    doc = run([meta()])
    doc["fasce"][0]["nome_file"] = "x.docx"
    doc["url"] = "http://x"
    errs = validate(doc)
    assert len(errs) >= 2


# ------------------------------------------------------------------------------------------- CLI
def test_cli_end_to_end(tmp_path):
    raw = tmp_path / "raw.jsonl"
    raw.write_text("\n".join(json.dumps(r) for r in [meta(), S("08:00", "accesso"), A("08:05")]) + "\n", encoding="utf-8")
    man = tmp_path / "man.jsonl"
    man.write_text(json.dumps(M("09:00", "10:00")) + "\n", encoding="utf-8")
    k = str(tmp_path / "k")
    assert main(["aggrega", str(raw), "-o", str(tmp_path / "g.json"), "--chiave", k]) == 0
    assert main(["rivedi", str(tmp_path / "g.json"), "--manuali", str(man), "-o", str(tmp_path / "r.json")]) == 0
    assert main(["sigilla-finale", str(tmp_path / "r.json"), "--chiave", k, "-o", str(tmp_path / "f.json")]) == 0
    assert main(["verifica", str(tmp_path / "f.json")]) == 1                       # INTEGRO
    assert main(["registra-chiave", os.path.join(k, "pubblica.json"), "--chiavi", str(tmp_path / "reg")]) == 0
    assert main(["verifica", str(tmp_path / "f.json"), "--chiavi", str(tmp_path / "reg")]) == 0
    f = json.load(open(tmp_path / "f.json", encoding="utf-8"))
    f["fasce"][3]["stato"] = "attivita_rilevata"
    json.dump(f, open(tmp_path / "x.json", "w", encoding="utf-8"))
    assert main(["verifica", str(tmp_path / "x.json")]) == 2
    assert main(["rivedi", str(tmp_path / "x.json"), "-o", str(tmp_path / "y.json")]) == 2   # rifiuta dati alterati
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"tipo":"app","ts":"2026-10-05T08:00:00","app":"word"}\n', encoding="utf-8")
    assert main(["aggrega", str(bad), "-o", str(tmp_path / "z.json"), "--senza-sigillo"]) == 2
