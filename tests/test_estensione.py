"""M8 – estensione del browser: host Native Messaging (validazione, raccolta solo a giornata avviata, formato),
lettore alla chiusura, pacchetti generati (niente permesso «tabs», host_permissions = siti del CED),
background.js eseguito con Node su un'API del browser finta."""
import datetime as dt
import io
import json
import os
import shutil
import struct
import subprocess
from zoneinfo import ZoneInfo

import pytest

from aggregatore.cli import validate
from aggregatore.mappa import Mappa
from collector import giornata
from estensione import costruisci, host, lettore

TZ = ZoneInfo("Europe/Rome")
G = dt.date(2026, 10, 5)
RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def T(hm, giorno=G):
    h, m = map(int, hm.split(":"))
    return dt.datetime.combine(giorno, dt.time(h, m), TZ)


def ep(hm):
    return int(T(hm).timestamp())


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("RSW_BASE", str(tmp_path / "rsw"))
    from collector.percorsi import Percorsi
    return Percorsi.predefiniti()


@pytest.fixture
def mappa():
    return Mappa.predefinita()


def _giornata(base, monkeypatch, orari):
    it = iter(orari)
    monkeypatch.setattr(giornata, "_adesso", lambda: next(it))
    monkeypatch.setattr(giornata, "ATTESA_FLUSH_ESTENSIONE_S", 0)
    giornata.avvia(base, presa_visione=True, lancia=False)


def _host(base, mappa, adesso, attiva=True):
    return host.Host(base, {"estensione_browser": attiva}, mappa, adesso=lambda: adesso)


def test_protocollo_native_messaging():
    buf = io.BytesIO()
    host.scrivi_messaggio(buf, {"cmd": "config"})
    buf.seek(0)
    assert host.leggi_messaggio(buf) == {"cmd": "config"}
    assert host.leggi_messaggio(io.BytesIO(b"")) is None
    with pytest.raises(ValueError):
        host.leggi_messaggio(io.BytesIO(struct.pack("<I", 10 ** 6) + b"x"))


def test_config_disattivata_per_impostazione_predefinita(base, mappa, monkeypatch):
    from applicazione.servizio import impostazioni_predefinite
    assert impostazioni_predefinite(base.base)["estensione_browser"] is False
    _giornata(base, monkeypatch, [T("08:00")])
    c = _host(base, mappa, T("09:00"), attiva=False).config()
    assert c["raccolta"] is False
    r = _host(base, mappa, T("09:00"), attiva=False).fascia({"cmd": "fascia", "ts": ep("08:30"), "sito": "halley",
                                                              "campioni": 3})
    assert r == {"ok": False, "rifiutato": "estensione_disattivata"}


def test_config_elenca_solo_siti_ed_esclusi(base, mappa, monkeypatch):
    _giornata(base, monkeypatch, [T("08:00")])
    c = _host(base, mappa, T("09:00")).config()
    assert c["raccolta"] is True
    assert "gestionale.esempio.test" in c["siti"]["halley"]
    assert "escluso.esempio.test" in c["esclusi"]


@pytest.mark.parametrize("msg,motivo", [
    ({"ts": "x", "sito": "halley"}, "fascia_non_allineata"),
    ({"ts": None, "sito": "halley"}, "fascia_non_allineata"),
    ({"ts": 1, "sito": "halley"}, "fascia_non_allineata"),
    ({"sito": "https://gestionale.esempio.test/x"}, "sito_non_in_elenco"),
    ({"sito": "Pagina di Halley - titolo"}, "sito_non_in_elenco"),
    ({"sito": "sito_inventato"}, "sito_non_in_elenco"),
    ({"sito": "web_generico"}, "sito_non_in_elenco"),
    ({"sito": "halley", "campioni": 0}, "campioni_non_validi"),
])
def test_rifiuti(base, mappa, monkeypatch, msg, motivo):
    _giornata(base, monkeypatch, [T("08:00")])
    m = {"cmd": "fascia", "ts": ep("08:30"), "campioni": 2, **msg}
    assert _host(base, mappa, T("09:00")).fascia(m) == {"ok": False, "rifiutato": motivo}
    assert not [f for f in os.listdir(base.raw) if f.startswith("estensione-")]


def test_solo_fasce_concluse_e_durante_la_raccolta(base, mappa, monkeypatch):
    _giornata(base, monkeypatch, [T("08:10"), T("10:00"), T("10:40")])
    giornata.pausa(base); giornata.riprendi(base, lancia=False)
    h = _host(base, mappa, T("11:05"))
    f = lambda hm: h.fascia({"cmd": "fascia", "ts": ep(hm), "sito": "halley", "campioni": 2})
    assert f("07:45")["rifiutato"] == "raccolta_non_attiva"       # prima di «Avvia»
    assert f("10:15")["rifiutato"] == "raccolta_non_attiva"       # tutta in pausa
    assert f("11:00")["rifiutato"] == "fascia_fuori_periodo"      # non ancora conclusa
    assert f("08:00") == {"ok": True}                             # avvio alle 08:10: conta dalle 08:10
    assert f("10:30") == {"ok": True}                             # ripresa alle 10:40
    assert f("08:00") == {"ok": True, "duplicata": True}
    righe = [json.loads(x) for x in open(os.path.join(base.raw, "estensione-2026-10-05.jsonl"), encoding="utf-8")]
    assert righe == [{"fonte": "estensione", "sito": "halley", "tipo": "web", "ts": T("08:10").isoformat()},
                     {"fonte": "estensione", "sito": "halley", "tipo": "web", "ts": T("10:40").isoformat()}]
    log = open(os.path.join(base.diagnostica, "estensione-host.log"), encoding="utf-8").read()
    assert "raccolta_non_attiva" in log and "halley" not in log


def test_main_stdin_stdout(base, mappa, monkeypatch):
    """Il ciclo dei messaggi termina alla chiusura di stdin; un messaggio malformato chiude con errore."""
    class Flussi:
        def __init__(self, dati):
            self.buffer = io.BytesIO(dati)
    ingresso = io.BytesIO()
    host.scrivi_messaggio(ingresso, {"cmd": "boh"})
    out = Flussi(b"")
    monkeypatch.setenv("RSW_BASE", base.base)
    monkeypatch.setattr(host.sys, "stdin", Flussi(ingresso.getvalue()))
    monkeypatch.setattr(host.sys, "stdout", out)
    assert host.main() == 0
    out.buffer.seek(0)
    r = host.leggi_messaggio(out.buffer)
    assert r["ok"] is False and r["rifiutato"] == "comando_sconosciuto" and "raccolta" in r
    monkeypatch.setattr(host.sys, "stdin", Flussi(struct.pack("<I", 3) + b"[1]"))
    assert host.main() == 1


def test_lettore_scarta_righe_non_valide(base, mappa, tmp_path):
    righe = [{"tipo": "web", "ts": T("09:00").isoformat(), "sito": "halley"},
             {"tipo": "web", "ts": T("09:00").isoformat(), "sito": "halley"},
             {"tipo": "web", "ts": T("09:15").isoformat(), "sito": "web_generico"},
             {"tipo": "web", "ts": T("09:30").isoformat(), "sito": "https://esempio.it/pagina"},
             {"tipo": "web", "ts": T("09:30").isoformat(), "sito": "non_in_mappa"},
             {"tipo": "app", "ts": T("09:30").isoformat(), "app": "word"},
             {"tipo": "web", "ts": "2026-10-04T09:00:00+02:00", "sito": "halley"},
             {"tipo": "web", "ts": "2026-10-05T09:00:00", "sito": "halley"}]
    p = tmp_path / "estensione-2026-10-05.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in righe) + "riga rotta\n", encoding="utf-8")
    ev = lettore.eventi(str(tmp_path), G, mappa)
    assert ev == [("web", T("09:00"), {"sito": "halley"}), ("web", T("09:15"), {"sito": "web_generico"})]
    assert lettore.eventi(str(tmp_path), G, mappa, intervalli=[(T("09:10"), T("10:00"))]) == ev[1:]
    assert lettore.eventi(str(tmp_path), dt.date(2026, 10, 6), mappa) == []


def test_chiusura_collector_unisce_le_fasce(base, mappa, monkeypatch):
    _giornata(base, monkeypatch, [T("08:00"), T("12:00")])
    h = _host(base, mappa, T("11:00"))
    for hm in ("08:00", "08:15", "09:00"):
        assert h.fascia({"cmd": "fascia", "ts": ep(hm), "sito": "halley", "campioni": 4})["ok"]
    r = giornata.chiudi(base, sigillo=False, estensione=True)
    doc = json.load(open(r["json"], encoding="utf-8"))
    assert validate(doc) == []
    assert doc["copertura_fonti"]["browser"] == "parziale"
    fasce = {f["ora"]: f for f in doc["fasce"]}
    assert "halley" in json.dumps(fasce["09:00"]) and "halley" not in json.dumps(fasce["10:00"])
    testo = json.dumps(doc)
    assert "gestionale.esempio" not in testo and "estensione" not in testo
    raw = open(r["raw"], encoding="utf-8").read()
    assert '"sito": "halley"' in raw and "fonte" not in raw.split('"tipo": "meta"')[1]


def test_chiusura_senza_estensione_ignora_il_file(base, mappa, monkeypatch):
    _giornata(base, monkeypatch, [T("08:00"), T("12:00")])
    assert _host(base, mappa, T("11:00")).fascia({"cmd": "fascia", "ts": ep("09:00"), "sito": "halley",
                                                  "campioni": 4})["ok"]
    r = giornata.chiudi(base, sigillo=False)
    doc = json.load(open(r["json"], encoding="utf-8"))
    assert doc["copertura_fonti"]["browser"] == "non_installato"
    assert '"sito"' not in open(r["raw"], encoding="utf-8").read()


def test_manifest_generati(mappa, tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    import base64
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = base64.b64encode(k.public_key().public_bytes(serialization.Encoding.DER,
                                                       serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
    r = costruisci.costruisci(str(tmp_path), mappa, pub)
    assert len(r["id_chromium"]) == 32 and set(r["id_chromium"]) <= set("abcdefghijklmnop")
    for b in ("chromium", "firefox"):
        m = json.load(open(tmp_path / b / "manifest.json", encoding="utf-8"))
        assert m["manifest_version"] == 3
        assert set(m["permissions"]) == {"alarms", "idle", "storage", "nativeMessaging"}
        assert "content_scripts" not in m and "content_security_policy" not in m
        assert "*://gestionale.esempio.test/*" in m["host_permissions"]
        assert not any("escluso.esempio" in x or x in ("<all_urls>", "*://*/*") for x in m["host_permissions"])
        assert (tmp_path / b / "background.js").exists()
    assert json.load(open(tmp_path / "chromium" / "manifest.json"))["background"] == {"service_worker": "background.js"}
    ff = json.load(open(tmp_path / "firefox" / "manifest.json"))
    assert ff["browser_specific_settings"]["gecko"]["data_collection_permissions"] == {"required": ["none"]}
    hc = json.load(open(tmp_path / "host-chromium.json"))
    assert hc["allowed_origins"] == [f"chrome-extension://{r['id_chromium']}/"] and hc["type"] == "stdio"
    assert json.load(open(tmp_path / "host-firefox.json"))["allowed_extensions"] == [costruisci.ID_FIREFOX]


def test_nessuna_chiave_privata_nel_repository():
    for cart, _, files in os.walk(os.path.join(RADICE, "estensione")):
        for f in files:
            assert not f.endswith((".pem", ".crx", ".key"))
            if f.endswith((".js", ".py", ".json", ".ps1", ".md")):
                assert "PRIVATE KEY" not in open(os.path.join(cart, f), encoding="utf-8").read()


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js non disponibile")
def test_background_js_con_api_finta():
    r = subprocess.run(["node", os.path.join(RADICE, "tests", "js", "test_background.js")], capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout



def test_risposta_fascia_include_raccolta(base, mappa, monkeypatch):
    """Ogni risposta (anche rifiuto) porta «raccolta», così l'estensione ferma i campioni subito dopo Pausa."""
    from collector import giornata as cg
    orari = iter([T("09:00"), T("10:20"), T("10:20")])
    monkeypatch.setattr(cg, "_adesso", lambda: next(orari))
    cg.avvia(base, presa_visione=True, lancia=False)
    h = host.Host(base, {"estensione_browser": True}, mappa, adesso=lambda: T("09:30"))
    r = h.gestisci({"cmd": "fascia", "ts": ep("09:00"), "sito": "halley", "campioni": 3})
    assert r.get("ok") is True and r.get("raccolta") is True
    cg.pausa(base)
    h = host.Host(base, {"estensione_browser": True}, mappa, adesso=lambda: T("10:45"))
    r2 = h.gestisci({"cmd": "fascia", "ts": ep("10:30"), "sito": "halley", "campioni": 3})
    assert r2.get("ok") is False and r2.get("rifiutato") == "raccolta_non_attiva"
    assert r2.get("raccolta") is False
