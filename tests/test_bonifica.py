"""Bonifica privacy della versione esistente (06/10/2026): le raccolte eliminate non devono più essere raggiungibili.

Ogni intervento (B1…B6b) aggiunge qui i suoi controlli di regressione: moduli assenti, chiavi di configurazione
assenti, testi e API vietati nel codice del prodotto, PDF/interfaccia/fatti AI senza i campi rimossi."""
from __future__ import annotations

import importlib
import json
import os
import re

import pytest

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACCHETTI = ("aggregatore", "applicazione", "collector", "estensione", "redattore", "resoconto",
             "verificatore")
ALTRE = (os.path.join("tools", "pacchetto"), "config", "schema")


def _file_prodotto(cartelle=PACCHETTI + ALTRE, estensioni=(".py", ".js", ".ps1", ".json")):
    for c in cartelle:
        for d, _, files in os.walk(os.path.join(RADICE, c)):
            if "__pycache__" in d or os.sep + "storico" in d:
                continue
            for f in files:
                if f.endswith(estensioni):
                    yield os.path.join(d, f)


def _cerca(regex, cartelle=PACCHETTI + ALTRE):
    r = re.compile(regex)
    out = []
    for f in _file_prodotto(cartelle):
        with open(f, encoding="utf-8-sig", errors="replace") as h:
            for n, riga in enumerate(h, 1):
                if r.search(riga):
                    out.append(f"{os.path.relpath(f, RADICE)}:{n}: {riga.strip()[:100]}")
    return out


def _config_app():
    with open(os.path.join(RADICE, "config", "app.json"), encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------------------------------- B1 cronologia
def test_b1_lettore_cronologia_assente():
    with pytest.raises(ImportError):
        importlib.import_module("consuntivo.browser")


def test_b1_nessun_accesso_ai_database_della_cronologia():
    assert _cerca(r"places\.sqlite|moz_places|moz_historyvisits|rsw_hist|[\"'/\\]History[\"']|visit_time") == []


def test_b1_opzione_browser_assente():
    from applicazione.servizio import impostazioni_predefinite
    assert "browser" not in _config_app()
    assert "browser" not in impostazioni_predefinite("/tmp/x")


# ------------------------------------------------------------------------- B2 PDF già emessi (ADR-T6)
def test_b2_pdf_400_gia_emesso_resta_verificabile():
    from resoconto import VERSIONE_APP
    from resoconto.verifica import verifica_file
    assert VERSIONE_APP != "4.0.0"
    r = verifica_file(os.path.join(RADICE, "tests", "dati", "resoconto_400_esempio01.pdf"),
                      [os.path.join(RADICE, "examples", "chiavi_registrate")])
    # Il PDF d'archivio è stato impaginato con un'altra versione di ReportLab: il confronto grafico non è possibile e,
    # senza, l'esito massimo è INTEGRO (sigilli e testo corrispondono, ma non si esclude contenuto sovrapposto).
    assert r["esito"] == "INTEGRO", r
    assert r["testo_pdf"] == "corrisponde ai dati"
    assert r["grafica_pdf"].startswith("non confrontata")


# ------------------------------------------------------------------------------------------- B2 posta
@pytest.mark.parametrize("modulo", ["collector.posta", "collector.posta_graph"])
def test_b2_lettori_posta_assenti(modulo):
    with pytest.raises(ImportError):
        importlib.import_module(modulo)


def test_b2_nessun_accesso_a_outlook_mapi_ews_graph():
    assert _cerca(r"win32com|pythoncom|Outlook\.Application|GetNamespace|\bMAPI\b|\bEWS\b|graph\.microsoft|"
                  r"Mail\.Read|ConversationIndex|conversationIndex|\bmsal\b|posta_graph") == []


def test_b2_impostazioni_posta_assenti():
    from applicazione.servizio import impostazioni_predefinite
    for k in ("posta", "posta_avvia_outlook", "posta_fonte", "posta_graph"):
        assert k not in _config_app() and k not in impostazioni_predefinite("/tmp/x")


def test_b2_registro_rifiuta_eventi_di_posta():
    from collector import registro
    with pytest.raises(Exception):
        registro.controlla("posta", {"direzione": "inviata"})


def test_b2_vecchio_json_con_posta_si_apre_senza_conteggi(tmp_path):
    """Un JSON della versione precedente con il campo «posta» si impagina e produce i fatti senza errori,
    ma nessun conteggio della posta compare nei fatti per l'AI o nel PDF."""
    from redattore import fatti
    from resoconto.pdf import pdf_bytes
    from resoconto.verifica import _testo_pagine
    with open(os.path.join(RADICE, "examples", "01_giornata_ufficio", "rivisto.json"), encoding="utf-8") as f:
        doc = json.load(f)
    doc["posta"] = {"disponibile": True, "ricevute": 41, "inviate": 37, "risposte": 5, "lette": 29, "interne": 3,
                    "esterne": 4, "per_categoria": {"tributi": 7}}
    doc["copertura_fonti"]["posta"] = "completa"
    testi = " ".join(f["testo"] for f in fatti.estrai(doc))
    assert "41" not in testi and "37" not in testi and "messaggi" not in testi
    pagine = " ".join(_testo_pagine(pdf_bytes(doc, "PROVA")))
    for vietato in ("Ricevute", "Inviate", "di cui risposte", "Lette", "Interne al Comune", "Cartella o categoria"):
        assert vietato not in pagine, vietato


# ------------------------------------------------------------------------------- B3 prototipo v3 e strumenti di prova
def test_b3_ponte_v3_e_lettura_titoli_eliminati():
    assert not os.path.exists(os.path.join(RADICE, "tools", "consuntivo_v3.py"))
    cartelle = PACCHETTI + ALTRE + ("tools",)
    assert _cerca(r"GetWindowText|keybd_event|mouse_event|SendInput|SendKeys|consuntivo_v3|RecentDocs|"
                  r"\\\\Recent\\\\|documenti recenti", cartelle) == []


# ------------------------------------------------------------------- B4 tempi complessivi, classifiche, indicatori
VIETATI_PDF_B4 = ("Tempo complessivo", "Strumenti più usati", "Totale attività dichiarate", "Operazioni di rete per fascia",
                  "Attività rilevata in totale", "Quota")


@pytest.mark.parametrize("esempio", sorted(d for d in os.listdir(os.path.join(RADICE, "examples"))
                                           if os.path.exists(os.path.join(RADICE, "examples", d, "finale.json"))))
def test_b4_pdf_e_fatti_senza_tempi_complessivi_ne_classifiche(esempio):
    from redattore import fatti
    from resoconto.pdf import pdf_bytes
    from resoconto.verifica import _testo_pagine
    with open(os.path.join(RADICE, "examples", esempio, "finale.json"), encoding="utf-8") as f:
        doc = json.load(f)
    pagine = " ".join(_testo_pagine(pdf_bytes(doc, "PROVA")))
    for v in VIETATI_PDF_B4:
        assert v not in pagine, v
    for x in fatti.estrai(doc):
        assert x["tipo"] != "totale_complessivo"
        assert "per un totale di" not in x["testo"] and "totale complessivo" not in x["testo"].lower()
        if x["tipo"] in ("categorie", "applicazioni", "siti", "totale_rilevato"):
            assert not re.search(r"\d+\s+minuti\b(?! \d)", x["testo"].replace("15 minuti", "")), x["testo"]


def test_b4_elenco_resoconti_senza_minuti(tmp_path):
    from applicazione import servizio
    assert "minuti" not in servizio.Servizio.resoconti_salvati.__code__.co_names
    assert _cerca(r"[\"']Tempo complessivo|Strumenti più usati|punteggio", PACCHETTI) == []   # «produttività» resta solo nel lessico vietato all'AI


# ------------------------------------------------------------------------------- B5 eseguibili non ammessi
def test_b5_campionatore_non_registra_eseguibili_non_ammessi():
    import datetime as dt
    from zoneinfo import ZoneInfo
    from collector.campionatore import Campionatore
    righe = []
    c = Campionatore(lambda tipo, ts, **k: righe.append((tipo, k)), {"WINWORD.EXE"})
    t = dt.datetime(2026, 10, 5, 9, 0, tzinfo=ZoneInfo("Europe/Rome"))
    c.tick(t, 1)
    c.tick(t + dt.timedelta(seconds=5), 2, lambda: "PRIVATO.EXE")
    c.tick(t + dt.timedelta(seconds=10), 3, lambda: "winword.exe")
    assert ("attivita", {}) in righe and ("app", {"exe": "WINWORD.EXE"}) in righe
    assert "PRIVATO" not in repr(righe) and c.conteggi["app_non_ammesse"] == 1


def test_b5_demone_usa_solo_l_elenco_del_ced():
    from aggregatore.mappa import Mappa
    from collector.demone import eseguibili_ammessi
    assert eseguibili_ammessi() == frozenset(Mappa.predefinita().per_exe) and "WINWORD.EXE" in eseguibili_ammessi()


def test_b5_vecchio_grezzo_con_eseguibile_non_ammesso_senza_nome():
    with open(os.path.join(RADICE, "examples", "01_giornata_ufficio", "giorno.json"), encoding="utf-8") as f:
        s = f.read()
    assert "altra_applicazione" not in s and "GESTPRATICHE" not in s.upper()


# ------------------------------------------------------------------------------- B6 siti ridotti a Halley
def test_configurazione_predefinita_senza_siti_ne_esclusi():
    """Il file distribuito ha l'elenco dei siti VUOTO: è una configurazione locale dell'Ente."""
    with open(os.path.join(RADICE, "config", "applicazioni.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    assert cfg["siti"] == {} and cfg["esclusi"] == {}


def test_b6_configurazione_di_prova_solo_halley_e_dominio_escluso():
    from aggregatore.mappa import Mappa
    with open(os.path.join(RADICE, "tests", "dati", "applicazioni_prova.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    assert {k: v["domini"] for k, v in cfg["siti"].items()} == {"halley": ["gestionale.esempio.test"]}
    assert "escluso.esempio.test" in cfg["esclusi"] and "cronologia" not in cfg["_istruzioni"]
    for prof in ((), ("sistemi_informativi",)):
        m = Mappa.predefinita(prof)
        assert sorted(m.per_dominio) == ["gestionale.esempio.test"]
        assert m.da_dominio("portale.esempio.test") == "" and m.da_dominio("escluso.esempio.test") == ""


def test_b6_estensione_chiede_solo_il_dominio_di_halley():
    from aggregatore.mappa import Mappa
    from estensione import costruisci
    for browser in ("chrome", "firefox"):
        man = costruisci.manifest(Mappa.predefinita(["sistemi_informativi"]), browser)
        assert man["host_permissions"] == ["*://*.gestionale.esempio.test/*", "*://gestionale.esempio.test/*"]


# ------------------------------------------------------------- B6b registro eventi (Security) e lettura retroattiva
def test_b6b_pacchetto_consuntivo_eliminato_e_nessuna_query_al_registro_eventi():
    for m in ("consuntivo", "consuntivo.sessione"):
        with pytest.raises(ImportError):
            importlib.import_module(m)
    assert not os.path.exists(os.path.join(RADICE, "consuntivo"))
    assert _cerca(r"wevtutil|EvtQuery|EvtSubscribe|Get-WinEvent|Win32_NTLogEvent|ReadEventLog|OpenEventLog|"
                  r"\b46(24|34|47)\b|\b48(00|01)\b|\b47(78|79)\b|Winlogon/Operational") == []
    with open(os.path.join(RADICE, "tools", "pacchetto", "build_app.ps1"), encoding="utf-8-sig") as f:
        assert "consuntivo" not in f.read()


def test_b6b_chiusura_a_consuntivo_non_legge_nulla(tmp_path, monkeypatch):
    import sys
    from applicazione.servizio import Servizio
    monkeypatch.setattr(sys, "platform", "win32")
    s = Servizio(str(tmp_path), impostazioni={"modalita": "consuntivo", "server_ai": "/x", "modelli_ai": "/x",
                                               "cache_ai": str(tmp_path / "c"), "cartella_pdf": str(tmp_path / "pdf")})
    letto = s._lettore_consuntivo()(None)
    assert letto["eventi"] == [] and set(letto["copertura"].values()) == {"non_installato"}
