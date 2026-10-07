"""Test dell'allineamento M1 (schema giornaliero/2): categorie per fascia, mappatura CED, sessione_disconnessa,
rete come soli conteggi, segnalazioni di dato errato, origine automatica/dichiarata, profilo AI, cambio d'orario."""
import copy
import json
import os

import pytest

from aggregatore import aggrega, mappa, modelli, sigillo
from aggregatore.cli import main, validate
from test_aggregatore import A, G, S, M, meta, run, stato, ts


def fascia(doc, hm):
    return next(f for f in doc["fasce"] if f["ora"] == hm)


def E(hm, exe):
    return {"tipo": "app", "ts": ts(hm), "exe": exe}


def segn(doc, *recs):
    s = modelli.parse_records([{"tipo": "meta", "giorno": G}, *recs]).segnalazioni
    return aggrega.apply_review(doc, [], "", s)


@pytest.fixture
def key(tmp_path):
    return sigillo.load_or_create_key(str(tmp_path / "k"), {"account": "ENTE\\prova", "pc": "PC-1"})


# ------------------------------------------------------------------------------------- mappatura applicazioni
def test_exe_mapped_and_never_copied():
    doc = run([meta(), S("08:00", "accesso"), E("08:05", "WINWORD.EXE"),
               E("08:20", "C:\\Program Files\\Microsoft Office\\root\\Office16\\excel.exe")])
    assert fascia(doc, "08:00")["app"] == ["word"] and fascia(doc, "08:15")["app"] == ["excel"]
    assert doc["classificazione"]["applicazioni"]["word"] == {"etichetta": "Microsoft Word", "categoria": "office"}
    s = json.dumps(doc).upper()
    assert "WINWORD" not in s and ".EXE" not in s and "PROGRAM FILES" not in s
    assert doc["versioni"]["mappa_applicazioni"] == doc["classificazione"]["versione_mappa"]


def test_unknown_exe_is_activity_without_application_name():
    """Bonifica B5: un eseguibile non ammesso (vecchio grezzo) conta come attività, senza nome né «altra applicazione»."""
    doc = run([meta(), S("08:00", "accesso"), E("08:05", "GESTIONALE_X.EXE")])
    f = fascia(doc, "08:00")
    assert f["stato"] == "attivita_rilevata"
    assert f["app"] == [] and "altra_applicazione" not in json.dumps(doc)
    assert "GESTIONALE" not in json.dumps(doc).upper()


def test_custom_mapping_and_category():
    mp = mappa.Mappa.da_dict({"versione": "test.1", "categorie": {"protocollo": "Protocollo informatico"},
                              "applicazioni": {"PROTO.EXE": {"id": "protocollo_web", "etichetta": "Protocollo",
                                                             "categoria": "protocollo"}}})
    doc = aggrega.aggregate(modelli.parse_records([meta(), S("08:00", "accesso"), E("08:05", "proto.exe")]), mp)
    assert fascia(doc, "08:00")["categorie"] == ["protocollo"]
    assert doc["classificazione"]["categorie"] == {"protocollo": "Protocollo informatico"}
    assert doc["totali"]["rilevati"]["per_categoria"] == [{"categoria": "protocollo", "fasce": 1}]
    assert doc["versioni"]["mappa_applicazioni"] == "test.1"


@pytest.mark.parametrize("j", [
    {"applicazioni": {"X.EXE": {"id": "x", "etichetta": "X", "categoria": "giochi"}}},          # categoria non definita
    {"applicazioni": {"X.EXE": {"id": "X Y", "etichetta": "X", "categoria": "office"}}},        # id non valido
    {"applicazioni": {"X.EXE": {"id": "altra_applicazione", "etichetta": "X", "categoria": "office"}}},  # riservato
    {"applicazioni": {"X.EXE": {"id": "x", "etichetta": "", "categoria": "office"}}},           # senza etichetta
    {"applicazioni": {"A.EXE": {"id": "x", "etichetta": "X", "categoria": "office"},
                      "B.EXE": {"id": "x", "etichetta": "X", "categoria": "posta"}}},           # id incoerente
    {"categorie": {"Non Valida": "x"}},
    {"siti": {"inps": {"etichetta": "INPS", "categoria": "boh"}}},
])
def test_mapping_validation(j):
    with pytest.raises(mappa.ErroreMappa):
        mappa.Mappa.da_dict(j)


def test_default_mapping_file_is_valid_and_has_base_categories():
    mp = mappa.Mappa.predefinita()
    assert set(mappa.CATEGORIE_BASE) <= set(mp.categorie)
    assert mp.da_exe("WINWORD.EXE") == "word" and mp.app("word") == ("Microsoft Word", "office")
    assert main(["valida-mappa"]) == 0


# ------------------------------------------------------------------------------------- categorie per fascia
def test_slot_categories():
    doc = run([meta(), S("08:00", "accesso"), {"tipo": "attivita", "ts": ts("08:05")}, A("08:20", "outlook"),
               {"tipo": "web", "ts": ts("08:35"), "dominio": "gestionale.esempio.test"},
               A("08:40", "excel")])
    assert fascia(doc, "08:00")["categorie"] == ["interazione_postazione"]
    assert fascia(doc, "08:15")["categorie"] == ["posta"]
    assert fascia(doc, "08:30")["categorie"] == ["halley", "office"]
    assert fascia(doc, "09:00")["categorie"] == []


# ------------------------------------------------------------------------------------- rete
def test_network_alone_is_never_interaction_proof():
    m = meta(copertura_fonti={"sessione": "completa", "app": "parziale", "rete": "completa"})
    doc = run([m, S("08:00", "accesso"), S("09:00", "blocco"),
               {"tipo": "rete", "ts": ts("08:20"), "operazioni": 40}, {"tipo": "rete", "ts": ts("08:25"), "operazioni": 2},
               {"tipo": "rete", "ts": ts("09:20"), "operazioni": 7}])
    f = fascia(doc, "08:15")
    assert f["stato"] == "nessuna_attivita_informatica_rilevata" and f["categorie"] == ["rete"] and f["rete"] is True
    assert stato(doc, "09:15") == "sessione_bloccata"                       # rete a PC bloccato: nessuno sblocco
    assert not any(e.get("implicito") for e in doc["sessione"]["eventi"])
    r = doc["totali"]["rilevati"]
    assert "operazioni_rete" not in r and r["fasce_con_rete"] == 2 and r["fasce_per_stato"]["attivita_rilevata"] == 0


def test_network_bytes_not_stored():
    doc = run([meta(), {"tipo": "rete", "ts": ts("08:20"), "byte": 987654321}])
    assert "987654321" not in json.dumps(doc) and fascia(doc, "08:15")["rete"] == 1


def test_network_operations_must_be_positive():
    with pytest.raises(modelli.ErroreIngresso):
        modelli.parse_records([meta(), {"tipo": "rete", "ts": ts("08:20"), "operazioni": -3}])


# ------------------------------------------------------------------------------------- posta e web
def test_mail_lines_are_not_activity_anymore():
    """Bonifica B2: un messaggio inviato non è più un'evidenza; la posta è solo la categoria dell'applicazione."""
    inv = lambda hm: {"tipo": "posta", "ts": ts(hm), "direzione": "inviata"}  # noqa: E731
    attiva = run([meta(), S("08:00", "accesso"), inv("08:05"), S("09:00", "blocco"), inv("09:05")])
    assert stato(attiva, "08:00") == "nessuna_attivita_informatica_rilevata" and fascia(attiva, "08:00")["categorie"] == []
    assert stato(attiva, "09:00") == "sessione_bloccata" and "posta" not in attiva


def test_web_whitelist_label_and_generic():
    m = meta(copertura_fonti={"sessione": "completa", "browser": "parziale"})
    doc = run([m, S("08:00", "accesso"), {"tipo": "web", "ts": ts("08:05"), "sito": "halley"},
               {"tipo": "web", "ts": ts("08:20")}, {"tipo": "web", "ts": ts("08:35"), "sito": "sito_ignoto"},
               {"tipo": "web", "ts": ts("08:50"), "url": "https://www.facebook.com/x"},
               S("09:00", "blocco"), {"tipo": "web", "ts": ts("09:05"), "sito": "inps"}])
    assert fascia(doc, "08:00")["categorie"] == ["halley"]
    assert fascia(doc, "08:15")["categorie"] == ["web_generico"]             # senza etichetta: non «non lavoro»
    assert fascia(doc, "08:30")["categorie"] == ["web_generico"]             # fuori elenco: web generico
    assert "facebook" not in json.dumps(doc)
    assert stato(doc, "09:00") == "sessione_bloccata"                         # web a sessione bloccata: non prova
    assert not any(e.get("implicito") for e in doc["sessione"]["eventi"])
    assert doc["copertura_fonti"]["browser"] == "parziale"


# ------------------------------------------------------------------------------------- stati e marcature
def test_sessione_disconnessa_distinct_from_locked():
    doc = run([meta(), S("08:00", "accesso"), A("08:01"), S("08:15", "blocco"), S("08:30", "sblocco"),
               S("08:45", "disconnessione"), S("09:30", "riconnessione"), S("10:00", "sospensione")])
    assert stato(doc, "08:15") == "sessione_bloccata"
    assert stato(doc, "08:45") == stato(doc, "09:15") == "sessione_disconnessa"
    assert stato(doc, "10:00") == "sessione_chiusa"                           # sospensione = sessione chiusa
    fp = doc["totali"]["rilevati"]["fasce_per_stato"]
    assert fp["sessione_disconnessa"] == 3 and fp["sessione_bloccata"] == 1


def test_implicit_unlock_slot_is_marked():
    doc = run([meta(), S("08:00", "accesso"), S("09:00", "blocco"), A("10:10")])
    assert fascia(doc, "10:00")["note_tecniche"] == ["sblocco_implicito"]
    assert sum(1 for f in doc["fasce"] if f["note_tecniche"]) == 1
    assert doc["totali"]["rilevati"]["fasce_con_note_tecniche"] == 1


@pytest.mark.parametrize("delta,attese", [(119, 0), (-120, 1), (3600, 9)])
def test_clock_change_threshold_and_marked_slots(delta, attese):
    doc = run([meta(), {"tipo": "orologio", "ts": ts("09:07"), "delta_s": delta}])
    marcate = [f["ora"] for f in doc["fasce"] if "cambio_orario" in f["note_tecniche"]]
    assert len(marcate) == attese
    assert any("ora di sistema" in a for a in doc["avvisi"]) == (attese > 0)
    if delta == -120:
        assert marcate == ["09:00"]                       # finestra 09:05-09:09
    if delta == 3600:
        assert marcate[0] == "08:00" and marcate[-1] == "10:00"   # finestra 08:07-10:07


# ------------------------------------------------------------------------------------- profilo AI
@pytest.mark.parametrize("post,profilo,criterio", [
    ({"ram_gb": 8}, "AI-LIGHT", "ram_rilevata"),
    ({"ram_gb": 7.8}, "AI-LIGHT", "ram_rilevata"),
    ({"ram_gb": 12}, "AI-LIGHT", "ram_rilevata"),
    ({"ram_gb": 15.8}, "AI-STANDARD", "ram_rilevata"),
    ({"ram_gb": 32}, "AI-STANDARD", "ram_rilevata"),
    ({}, "AI-LIGHT", "ram_non_rilevata"),
    ({"ram_gb": 0}, "AI-LIGHT", "ram_non_rilevata"),
    ({"ram_gb": 32, "profilo_ai": "AI-LIGHT"}, "AI-LIGHT", "impostato_ced"),
])
def test_ai_profile_from_ram(post, profilo, criterio):
    doc = run([meta(postazione={"host": "PC-1", "tipo": "fisica", **post})])
    assert "postazione" not in doc
    # Solo proposta di profilo runtime: non modifica il JSON tecnico.
    p = aggrega.profilo_ai(post)
    assert (p["profilo"], p["criterio"]) == (profilo, criterio)
    assert p["modello_indicativo"] == aggrega.PROFILI_AI[profilo]
    assert "account" not in doc["dipendente"]


# ------------------------------------------------------------------------------------- segnalazioni
def test_flag_never_alters_technical_data_and_is_sealed(key):
    d1 = sigillo.seal_technical(run([meta(), S("08:00", "accesso"), A("08:05"), S("09:00", "blocco")]), key)
    d2 = segn(d1, {"tipo": "segnalazione", "campo": "stato", "dalle": "09:00", "alle": "10:00",
                   "nota": "Ero in riunione su Teams dal telefono"})
    assert d2["fasce"] == d1["fasce"] and d2["totali"]["rilevati"] == d1["totali"]["rilevati"]
    assert sigillo.parte_tecnica(d2) == sigillo.parte_tecnica(d1)
    assert sigillo.verify(d2)["tecnico"]["valido"]
    s = d2["segnalazioni_dipendente"][0]
    assert (s["id"], s["fascia_da"], s["fascia_a"], s["dalle"], s["alle"], s["origine"]) == \
        ("s1", 36, 39, "09:00", "10:00", "dichiarata")
    d3 = sigillo.seal_final(d2, key)
    x = copy.deepcopy(d3)
    x["segnalazioni_dipendente"][0]["nota"] = "cambiata"
    assert sigillo.verify(x)["esito"] == "ALTERATO"
    assert validate(d3) == [] if _has_jsonschema() else True


def _has_jsonschema():
    try:
        import jsonschema  # noqa: F401
        return True
    except ImportError:
        return False


def test_flag_references():
    doc = run([meta()])
    d = segn(doc, {"tipo": "segnalazione", "campo": "applicazioni", "fascia": 40, "nota": "a"},
             {"tipo": "segnalazione", "campo": "rete", "dalle": "10:07", "nota": "b"},
             {"tipo": "segnalazione", "campo": "posta", "nota": "c"},
             {"tipo": "segnalazione", "campo": "stato", "dalle": "23:30", "alle": "23:59", "nota": "d"})
    s = d["segnalazioni_dipendente"]
    assert [x["id"] for x in s] == ["s1", "s2", "s3", "s4"]
    assert (s[0]["fascia_da"], s[0]["dalle"], s[0]["alle"]) == (40, "10:00", "10:15")
    assert (s[1]["fascia_da"], s[1]["fascia_a"]) == (40, 40)
    assert s[2]["fascia_da"] is None and s[2]["dalle"] is None
    assert (s[3]["fascia_da"], s[3]["fascia_a"], s[3]["alle"]) == (94, 95, "24:00")


@pytest.mark.parametrize("rec", [
    {"tipo": "segnalazione", "campo": "nome_file", "fascia": 3, "nota": "x"},
    {"tipo": "segnalazione", "campo": "stato", "nota": "manca la fascia"},
    {"tipo": "segnalazione", "campo": "stato", "fascia": 3, "nota": "  "},
    {"tipo": "segnalazione", "campo": "stato", "fascia": -1, "nota": "x"},
    {"tipo": "segnalazione", "campo": "stato", "dalle": "9:00", "nota": "x"},
    {"tipo": "segnalazione", "campo": "stato", "alle": "10:00", "nota": "x"},
])
def test_flag_invalid_input(rec):
    with pytest.raises(modelli.ErroreIngresso):
        modelli.parse_records([{"tipo": "meta", "giorno": G}, rec])


@pytest.mark.parametrize("rec", [
    {"tipo": "segnalazione", "campo": "stato", "fascia": 96, "nota": "x"},
    {"tipo": "segnalazione", "campo": "stato", "dalle": "10:00", "alle": "09:00", "nota": "x"},
])
def test_flag_invalid_reference(rec):
    with pytest.raises(ValueError):
        segn(run([meta()]), rec)


def test_flag_note_and_manual_description_max_200_with_warning():
    doc = run([meta()], [M("09:00", "10:00", d="y" * 250)])
    d = segn(doc, {"tipo": "segnalazione", "campo": "altro", "nota": "x" * 300})
    assert len(d["segnalazioni_dipendente"][0]["nota"]) == 200 and len(d["manuali"][0]["descrizione"]) == 200
    assert sum("200 caratteri" in a for a in d["avvisi_revisione"]) == 2


# ------------------------------------------------------------------------------------- origine
def test_origin_automatic_vs_declared_everywhere():
    doc = run([meta(), S("08:00", "accesso"), A("08:05")], [M("09:00", "10:00")])
    doc = segn(doc, {"tipo": "segnalazione", "campo": "totali", "nota": "x"})
    assert {f["origine"] for f in doc["fasce"]} == {"automatica"}
    assert {x["origine"] for x in doc["manuali"] + doc["segnalazioni_dipendente"]} == {"dichiarata"}
    od = doc["origine_dati"]
    assert od["fasce"] == od["sessione"] == "automatic" and "posta" not in od
    assert od["manuali"] == "declared"
    assert od["segnalazioni_dipendente"] == od["osservazioni_dipendente"] == "observation"
    assert "segnalazioni_dipendente" in sigillo.CAMPI_NON_TECNICI


# ------------------------------------------------------------------------------------- coerenza, purezza, CLI
def test_tampered_category_totals_detected(key):
    d = sigillo.seal_technical(run([meta(), S("08:00", "accesso"), A("08:05")]), key)
    d["totali"]["rilevati"]["per_categoria"] = [{"categoria": "halley", "fasce": 20, "minuti": 300}]
    d = sigillo.seal_technical(d, key)
    r = sigillo.verify(d)
    assert r["esito"] == "ALTERATO" and any("non coerenti" in m for m in r["motivi"])


def test_aggregate_does_not_mutate_input():
    inp = modelli.parse_records([meta(), S("08:00", "accesso"), E("08:05", "WINWORD.EXE")])
    before = copy.deepcopy(inp.eventi)
    a = aggrega.aggregate(inp)
    assert inp.eventi == before and aggrega.aggregate(inp) == a


def test_cli_review_file_with_flags(tmp_path):
    raw = tmp_path / "raw.jsonl"
    raw.write_text("\n".join(json.dumps(r) for r in [meta(), S("08:00", "accesso"), E("08:05", "EXCEL.EXE")]) + "\n",
                   encoding="utf-8")
    rev = tmp_path / "rev.jsonl"
    rev.write_text("\n".join(json.dumps(r) for r in [
        M("09:00", "10:00", "telefonata", "Contribuente"),
        {"tipo": "segnalazione", "campo": "stato", "fascia": 33, "nota": "Il PC era acceso"},
        {"tipo": "osservazione", "testo": "Giornata con molte telefonate"}]) + "\n", encoding="utf-8")
    k = str(tmp_path / "k")
    assert main(["aggrega", str(raw), "-o", str(tmp_path / "g.json"), "--chiave", k]) == 0
    assert main(["rivedi", str(tmp_path / "g.json"), "--revisione", str(rev), "-o", str(tmp_path / "r.json")]) == 0
    r = json.load(open(tmp_path / "r.json", encoding="utf-8"))
    assert len(r["manuali"]) == 1 and len(r["segnalazioni_dipendente"]) == 1
    assert r["osservazioni_dipendente"] == "Giornata con molte telefonate"
    assert sigillo.verify(r, check_final=False)["tecnico"]["valido"]
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps(S("08:00", "accesso")) + "\n", encoding="utf-8")
    assert main(["rivedi", str(tmp_path / "g.json"), "--revisione", str(bad), "-o", str(tmp_path / "x.json")]) == 2


def test_schema_rejects_unknown_technical_note_and_category_label():
    pytest.importorskip("jsonschema")
    doc = run([meta()])
    doc["fasce"][0]["note_tecniche"] = ["tasti_premuti"]
    doc["fasce"][1]["origine"] = "dichiarata"
    assert len(validate(doc)) >= 2
