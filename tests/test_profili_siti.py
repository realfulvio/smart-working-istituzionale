"""Siti di lavoro: dopo la bonifica B6 (06/10/2026) solo il gestionale Halley; profili e meccanismo della mappatura
(IPv4, esclusioni, host senza porta/percorso) restano e si provano con mappature di prova."""
import json
import os

import pytest

from aggregatore import aggrega, mappa, modelli
from aggregatore.cli import main, validate
from test_aggregatore import A, S, meta, ts

ROOT = os.path.join(os.path.dirname(__file__), "..")
CFG = json.load(open(os.path.join(ROOT, "tests", "dati", "applicazioni_prova.json"), encoding="utf-8"))


def W(hm, dom):
    return {"tipo": "web", "ts": ts(hm), "dominio": dom}


def fascia(doc, hm):
    return next(f for f in doc["fasce"] if f["ora"] == hm)


def run(recs, profili=()):
    return aggrega.aggregate(modelli.parse_records(recs), mappa.Mappa.predefinita(profili))


def tutti_i_domini():
    return [d for s in CFG["siti"].values() for d in s["domini"]]


# ------------------------------------------------------------------------------------------ profili
def test_profili_restano_ma_solo_halley():
    """Bonifica B6: i profili restano (compatibilità delle impostazioni), l'unico sito è Halley per tutti."""
    gen = mappa.Mappa.predefinita()
    ced = mappa.Mappa.predefinita(["sistemi_informativi"])
    assert gen.profili_attivi == ("generale",) and ced.profili_attivi == ("generale", "sistemi_informativi")
    assert ced.versione == CFG["versione"] + "+sistemi_informativi" and gen.versione == CFG["versione"]
    for m in (gen, ced):
        assert set(m.siti) == {"halley"} and m.da_dominio("gestionale.esempio.test") == "halley"
        for altro in ("198.51.100.20", "console-edr.esempio.test", "www2.x-desk.it", "servizi2.inps.it",
                      "srv-vcenter6.ente.invalid", "portale.esempio.test"):
            assert m.da_dominio(altro) == "", altro


def test_strumenti_ced_non_riconosciuti_neppure_con_profilo():
    recs = [meta(), S("08:00", "accesso"), A("08:05", "browser"), W("08:06", "srv-vcenter6.ente.invalid")]
    for d in (run(recs), run(recs, ["sistemi_informativi"])):
        assert fascia(d, "08:00")["siti"] == [] and fascia(d, "08:00")["categorie"] == ["web_generico"]
        assert validate(d) == [] and "ente.invalid" not in json.dumps(d)


def test_profilo_sconosciuto_o_non_definito_e_errore():
    with pytest.raises(mappa.ErroreMappa):
        mappa.Mappa.predefinita(["contabilita"])
    with pytest.raises(mappa.ErroreMappa):
        mappa.Mappa.da_dict({"siti": {"x": {"etichetta": "X", "categoria": "web_generico", "domini": ["x.it"], "profilo": "boh"}}})


def test_cli_aggrega_con_profilo(tmp_path):
    raw = tmp_path / "raw.jsonl"
    raw.write_text("\n".join(json.dumps(r) for r in [meta(), S("08:00", "accesso"), A("08:05", "browser"),
                                                      W("08:06", "198.51.100.20")]), encoding="utf-8")
    out = tmp_path / "g.json"
    assert main(["aggrega", str(raw), "-o", str(out), "--senza-sigillo", "--profilo", "sistemi_informativi"]) == 0
    assert fascia(json.loads(out.read_text(encoding="utf-8")), "08:00")["siti"] == []       # B6: solo Halley
    assert main(["aggrega", str(raw), "-o", str(out), "--senza-sigillo", "--profilo", "inesistente"]) == 2


# ------------------------------------------------------------------------------------------ IPv4
def test_ipv4_vale_solo_per_se_stesso():
    m = mappa.Mappa.da_dict({"siti": {"console": {"etichetta": "Console", "categoria": "web_generico",
                                                  "domini": ["198.51.100.20"]}}})
    assert m.da_dominio("198.51.100.20") == "console"
    assert m.da_dominio("198.51.100.2") == m.da_dominio("7.198.51.100.20") == m.da_dominio("51.100.20") == ""


@pytest.mark.parametrize("dom", ["198.51.100.20:8443", "300.1.1.1", "198.51.100", "https://198.51.100.20"])
def test_ipv4_non_valido_rifiutato(dom):
    with pytest.raises(mappa.ErroreMappa):
        mappa.Mappa.da_dict({"siti": {"c": {"etichetta": "C", "categoria": "web_generico", "domini": [dom]}}})


def test_dominio_in_due_siti_anche_in_profili_diversi_e_errore():
    with pytest.raises(mappa.ErroreMappa):
        mappa.Mappa.da_dict({"profili": {"ced": {}}, "siti": {
            "a": {"etichetta": "A", "categoria": "web_generico", "domini": ["a.it"]},
            "b": {"etichetta": "B", "categoria": "web_generico", "domini": ["a.it"], "profilo": "ced"}}})


# ------------------------------------------------------------------------------------------ contenuto
def test_configurazione_solo_halley():
    assert tutti_i_domini() == ["gestionale.esempio.test"]


@pytest.mark.parametrize("vietato", ["youtube", "maps.google", "google.", "facebook", "instagram", "whatsapp", "telegram",
                                     "amazon", "aliexpress", "ebay", "netflix", "spotify", "repubblica", "corriere",
                                     "poste.it", "paypal", "chatgpt", "openvpn", "bitwarden", "day.it", "noipa"])
def test_nessun_sito_personale_in_mappatura(vietato):
    assert not any(vietato in d for d in tutti_i_domini())


# ------------------------------------------------------------------------------------------ host con porta / URL
HALLEY_URL = "https://gestionale.esempio.test:8443/halley/main.php?sessione=AbC123tok&utente=x#menu"
XDESK_URL = "https://www2.x-desk.it/area-clienti/ticket?id=987654"


@pytest.mark.parametrize("valore, host", [
    (HALLEY_URL, "gestionale.esempio.test"), ("gestionale.esempio.test:8443", "gestionale.esempio.test"),
    (XDESK_URL, "www2.x-desk.it"), ("WWW2.X-Desk.it.", "www2.x-desk.it"), ("https://u:p@198.51.100.20:443/x", "198.51.100.20"),
    ("[::1]:8080", ""), ("", "")])
def test_solo_host(valore, host):
    assert mappa.solo_host(valore) == host


def test_halley_8443_e_x_desk_riconosciuti_senza_porta_percorso_query():
    m = mappa.Mappa.predefinita()
    assert m.da_dominio("gestionale.esempio.test:8443") == m.da_dominio(HALLEY_URL) == "halley"
    assert m.da_dominio("www2.x-desk.it") == m.da_dominio(XDESK_URL) == ""                 # B6: solo Halley
    assert mappa.Mappa.predefinita(["sistemi_informativi"]).da_dominio("198.51.100.20:8443") == ""
    recs = [meta(), S("08:00", "accesso"), A("08:05", "browser"), W("08:06", HALLEY_URL), W("08:20", XDESK_URL),
            {"tipo": "web", "ts": ts("08:31"), "dominio": "gestionale.esempio.test:8443", "url": HALLEY_URL}]
    doc = run(recs)
    assert fascia(doc, "08:00")["siti"] == ["halley"] and fascia(doc, "08:15")["siti"] == []
    assert fascia(doc, "08:30")["siti"] == ["halley"]
    out = json.dumps(doc)
    for vietato in ("8443", "AbC123tok", "sessione=", "main.php", "/halley", "area-clienti", "987654", "gestionale.esempio",
                    "x-desk.it", "https://"):
        assert vietato not in out, vietato
    assert validate(doc) == []


@pytest.mark.parametrize("host", ["escluso.esempio.test", "urlsand.esvalabs.com", "url.fornitore.esempio.test", "antispam02.fornitore.esempio.test",
                                  "eu-west-1.protection.sophos.com", "us.list-manage.com", "www.fornitore.esempio.test",
                                  "www.fornitore.esempio.test", "www.altro-fornitore.esempio.test", "ntp1.inrim.it", "128.1.0.227",
                                  "www.mepa.it", "zendesk.com"])
def test_link_di_passaggio_firme_e_sospetti_non_mappati(host):
    assert mappa.Mappa.predefinita(["sistemi_informativi"]).da_dominio(host) == ""


# ------------------------------------------------------------------------------------------ esclusioni
def test_dominio_escluso_esplicitamente():
    assert "escluso.esempio.test" in CFG["esclusi"]
    for prof in ((), ("sistemi_informativi",)):
        m = mappa.Mappa.predefinita(prof)
        assert m.escluso("www.escluso.esempio.test") and m.escluso("https://login.escluso.esempio.test:443/x?y=1")
        assert m.da_dominio("escluso.esempio.test") == m.da_dominio("portale.escluso.esempio.test") == ""


def test_dominio_escluso_non_puo_essere_sito():
    with pytest.raises(mappa.ErroreMappa):
        mappa.Mappa.da_dict({"esclusi": {"esempio.it": "phishing"},
                             "siti": {"x": {"etichetta": "X", "categoria": "web_generico", "domini": ["www.esempio.it"]}}})
    with pytest.raises(mappa.ErroreMappa):
        mappa.Mappa.da_dict({"esclusi": {"esempio.it": ""}})
