"""Collector M3: logica di campionamento (senza Windows), registro con campi chiusi, comandi della giornata e
integrazione con l'aggregatore."""
import datetime as dt
import json
import os
from zoneinfo import ZoneInfo

import pytest

from aggregatore import aggrega, modelli
from aggregatore.cli import validate
from collector import giornata
from collector.campionatore import Campionatore, inizio_fascia
from collector.cli import main as cli_main, riepilogo_diagnostica
from collector.percorsi import Percorsi
from collector.registro import ErroreRegistro, Registro, controlla
from collector.stato import Stato

TZ = ZoneInfo("Europe/Rome")


def T(hm, s=0, giorno=dt.date(2026, 10, 5)):
    h, m = map(int, hm.split(":"))
    return dt.datetime.combine(giorno, dt.time(h, m, s), TZ)


class Buffer:
    def __init__(self):
        self.ev = []

    def __call__(self, tipo, ts, **campi):
        controlla(tipo, campi)
        rec = {"tipo": tipo, "ts": ts.isoformat(), **campi}
        self.ev.append(rec)
        return rec

    def tipi(self, tipo):
        return [e for e in self.ev if e["tipo"] == tipo]


# ------------------------------------------------------------------------------------------ campionatore
def test_un_solo_evento_attivita_per_fascia_e_app_solo_con_input():
    b = Buffer(); c = Campionatore(b)
    c.tick(T("08:00"), 1000, lambda: "WINWORD.EXE")             # riferimento: nessun input ancora
    assert b.ev == []
    c.tick(T("08:00", 5), 1000, lambda: "WINWORD.EXE")          # nessun nuovo input -> niente
    assert b.ev == []
    c.tick(T("08:00", 10), 1500, lambda: "WINWORD.EXE")
    c.tick(T("08:01"), 2500, lambda: "WINWORD.EXE")
    c.tick(T("08:02"), 3500, lambda: "C:\\x\\EXCEL.EXE".rsplit("\\", 1)[1])
    assert len(b.tipi("attivita")) == 1
    assert [e["exe"] for e in b.tipi("app")] == ["WINWORD.EXE", "EXCEL.EXE"]
    c.tick(T("08:15", 3), 4000, lambda: "WINWORD.EXE")          # nuova fascia
    assert len(b.tipi("attivita")) == 2 and len(b.tipi("app")) == 3


def test_sessione_bloccata_non_registra_attivita():
    b = Buffer(); c = Campionatore(b)
    c.tick(T("09:00"), 1, lambda: "WINWORD.EXE")
    c.wts(T("09:01"), 0x7)                                       # WTS_SESSION_LOCK
    c.tick(T("09:02"), 2, lambda: "LOCKAPP.EXE")
    assert b.tipi("attivita") == [] and b.tipi("app") == []
    c.wts(T("09:20"), 0x8)                                       # sblocco
    c.tick(T("09:20", 5), 3, lambda: "OUTLOOK.EXE")
    assert [e["evento"] for e in b.tipi("sessione")] == ["blocco", "sblocco"]
    assert [e["exe"] for e in b.tipi("app")] == ["OUTLOOK.EXE"]
    c.power(T("09:30"), 0x4); c.power(T("09:40"), 0x12); c.wts(T("09:41"), 0x4); c.wts(T("09:42"), 0x99)
    assert [e["evento"] for e in b.tipi("sessione")][-3:] == ["sospensione", "ripresa", "disconnessione"]


def test_rete_un_numero_per_fascia_e_contatore_azzerato():
    b = Buffer(); c = Campionatore(b)
    for hm, n in (("10:00", 100), ("10:05", 160), ("10:10", 170), ("10:16", 50), ("10:20", 80)):
        c.rete(n); c.tick(T(hm), None)
    c.chiudi_fascia()
    assert [(e["ts"][11:16], e["operazioni"]) for e in b.tipi("rete")] == [("10:10", 70), ("10:20", 30)]


def test_fasce_in_tempo_assoluto_anche_al_cambio_ora():
    t = dt.datetime(2026, 10, 25, 2, 50, tzinfo=TZ, fold=1)     # seconda volta delle 02:50 (ora solare)
    assert inizio_fascia(t).minute == 45 and inizio_fascia(t).utcoffset() == dt.timedelta(hours=1)


# ---------------------------------------------------------------------------------------------- registro
@pytest.mark.parametrize("tipo, campi", [("app", {"exe": "C:\\Programmi\\WINWORD.EXE"}), ("app", {"titolo": "x"}),
                                          ("attivita", {"tasti": 3}), ("posta", {"direzione": "inviata", "oggetto": "x"}),
                                          ("web", {"url": "https://x"}), ("rete", {"operazioni": 0})])
def test_registro_rifiuta_campi_non_ammessi(tipo, campi):
    with pytest.raises(ErroreRegistro):
        controlla(tipo, campi)


def test_registro_scrive_nel_file_del_giorno(tmp_path):
    p = Percorsi(str(tmp_path)); r = Registro(p)
    r.scrivi("attivita", T("23:59", 59)); r.scrivi("attivita", T("00:00", 1, dt.date(2026, 10, 6)))
    assert os.path.exists(p.raw_giorno("2026-10-05")) and os.path.exists(p.raw_giorno("2026-10-06"))
    with pytest.raises(ErroreRegistro):
        r.scrivi("attivita", dt.datetime(2026, 10, 5, 9))       # senza fuso


# ------------------------------------------------------------------------------------ giornata end to end
@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("RSW_BASE", str(tmp_path))
    return Percorsi.predefiniti()


def test_giornata_completa_senza_windows(base, monkeypatch):
    """avvia -> campioni -> pausa -> riprendi -> chiudi: raw.jsonl valido e JSON giornaliero dell'aggregatore."""
    orari = iter([T("08:59"), T("09:00"), T("10:00"), T("10:30"), T("11:30")])
    monkeypatch.setattr(giornata, "_adesso", lambda: next(orari))
    with pytest.raises(giornata.ErroreGiornata):
        giornata.avvia(base, lancia=False)                       # senza presa visione
    giornata.avvia(base, presa_visione=True, lancia=False)
    reg = Registro(base); c = Campionatore(reg.scrivi)
    c.tick(T("09:00", 5), 10)
    for i, hm in enumerate(("09:01", "09:07", "09:20", "09:40")):
        c.tick(T(hm), 100 + i, lambda: "WINWORD.EXE")
    c.wts(T("09:45"), 0x7); c.wts(T("09:50"), 0x8); c.tick(T("09:51"), 200, lambda: "HALLEY.EXE")
    c.chiudi_fascia()
    giornata.pausa(base)                                         # 10:00 (processo non attivo: scrive la CLI)
    giornata.riprendi(base, lancia=False)                        # 10:30
    c2 = Campionatore(reg.scrivi); c2.tick(T("10:30", 5), 300); c2.tick(T("10:31"), 301, lambda: "OUTLOOK.EXE")
    r = giornata.chiudi(base, sigillo=False)        # 11:30
    doc = json.load(open(r["json"], encoding="utf-8"))
    assert validate(doc) == []
    st = {f["ora"]: f["stato"] for f in doc["fasce"]}
    assert st["08:45"] == "dato_non_disponibile"                 # prima dell'avvio: non osservato
    assert st["09:00"] == st["09:15"] == st["09:30"] == "attivita_rilevata"
    assert st["09:45"] == "attivita_rilevata"                    # sblocco + Halley nella fascia
    assert st["10:00"] == st["10:15"] == "raccolta_sospesa"
    assert st["10:30"] == "attivita_rilevata" and st["10:45"] == "nessuna_attivita_informatica_rilevata"
    assert st["11:30"] == st["12:00"] == "dato_non_disponibile"  # dopo «Chiudi giornata»
    assert doc["modalita"] == "collector" and doc["copertura_fonti"]["browser"] == "non_installato"
    out = json.dumps(doc)
    assert "WINWORD.EXE" not in out and "HALLEY.EXE" not in out
    ev = [json.loads(x) for x in open(r["raw"], encoding="utf-8")]
    assert ev[0]["tipo"] == "meta" and sum(e["tipo"] == "meta" for e in ev) == 1
    assert {e["tipo"] for e in ev} <= {"meta", "sessione", "attivita", "app", "rete", "posta", "raccolta", "orologio"}
    assert Stato(base).giornata()["fase"] == "chiusa"


def test_comandi_fuori_sequenza(base):
    with pytest.raises(giornata.ErroreGiornata):
        giornata.pausa(base)
    with pytest.raises(giornata.ErroreGiornata):
        giornata.chiudi(base)
    assert cli_main(["riprendi"]) == 2


def test_demone_risponde_al_comando_scritto_dalla_cli(base):
    st = Stato(base)
    st.invia_comando("pausa", T("10:00"))
    assert st.leggi_comando() == {"comando": "pausa", "ts": T("10:00").isoformat()}
    st.cancella_comando(); assert st.leggi_comando() is None
    st.invia_comando("formatta", T("10:00")); assert st.leggi_comando() is None


def test_riepilogo_consumo_su_piu_esecuzioni(base):
    f = os.path.join(base.diagnostica, "2026-10-05.jsonl")
    rows = [{"secondi": 0, "cpu_s": 0, "ws_mb": 20, "picco_ws_mb": 21, "privata_mb": 12},
            {"secondi": 600, "cpu_s": 1.2, "ws_mb": 22, "picco_ws_mb": 23, "privata_mb": 13},
            {"secondi": 0, "cpu_s": 0, "ws_mb": 19, "picco_ws_mb": 20, "privata_mb": 12},
            {"secondi": 400, "cpu_s": 0.8, "ws_mb": 21, "picco_ws_mb": 24, "privata_mb": 14}]
    open(f, "w", encoding="utf-8").write("\n".join(json.dumps(r) for r in rows))
    r = riepilogo_diagnostica(base, "2026-10-05")
    assert r["secondi"] == 1000 and r["cpu_s"] == 2.0 and r["cpu_percento"] == 0.2 and r["picco_ws_mb"] == 24


def test_nessun_accesso_a_cronologia_o_titoli_nel_codice():
    src = "".join(open(os.path.join(os.path.dirname(giornata.__file__), f), encoding="utf-8").read()
                  for f in os.listdir(os.path.dirname(giornata.__file__)) if f.endswith(".py"))
    for vietato in ("GetWindowText", "places.sqlite", "History", "SetWindowsHookEx", "GetAsyncKeyState",
                    "GetCursorPos", ".Subject", ".Body", "SenderEmail", "Recipients", "Documenti comuni"):
        assert vietato not in src, vietato


def test_eseguibile_con_spazi_accettato_percorso_scartato():
    b = Buffer(); c = Campionatore(b)
    c.tick(T("08:00"), 1); c.tick(T("08:01"), 2, lambda: "MY APP (X64).EXE"); c.tick(T("08:02"), 3, lambda: "C:\\A\\B.EXE")
    assert [e["exe"] for e in b.tipi("app")] == ["MY APP (X64).EXE"] and c.conteggi["app_scartate"] == 1


def test_giornata_a_cavallo_della_mezzanotte(base, monkeypatch):
    """avvia 23:00, blocco 23:50, sblocco 00:20, pausa 00:40, chiudi 01:10 -> due JSON validi; il secondo giorno
    parte bloccato (non «dato non disponibile») e la pausa è riconosciuta."""
    g2 = dt.date(2026, 10, 6)
    orari = iter([T("23:00"), T("00:40", giorno=g2), T("01:10", giorno=g2)])
    monkeypatch.setattr(giornata, "_adesso", lambda: next(orari))
    giornata.avvia(base, presa_visione=True, lancia=False)
    reg = Registro(base); c = Campionatore(reg.scrivi)
    c.tick(T("23:00", 5), 10); c.tick(T("23:10"), 20, lambda: "WINWORD.EXE")
    c.wts(T("23:50"), 0x7)
    c.wts(T("00:20", giorno=g2), 0x8); c.tick(T("00:21", giorno=g2), 30, lambda: "EXCEL.EXE")
    c.chiudi_fascia()
    giornata.pausa(base)
    r = giornata.chiudi(base, sigillo=False)
    assert [x["giorno"] for x in r["giorni"]] == ["2026-10-05", "2026-10-06"]
    d1, d2 = (json.load(open(x["json"], encoding="utf-8")) for x in r["giorni"])
    assert validate(d1) == [] and validate(d2) == []
    s1 = {f["ora"]: f["stato"] for f in d1["fasce"]}
    s2 = {f["ora"]: f["stato"] for f in d2["fasce"]}
    assert s1["22:45"] == "dato_non_disponibile" and s1["23:00"] == "attivita_rilevata"
    assert s1["23:45"] == "attivita_rilevata" or s1["23:45"] == "sessione_bloccata"
    assert s2["00:00"] == "sessione_bloccata"                     # stato a mezzanotte riportato dal giorno prima
    assert s2["00:15"] == "attivita_rilevata"
    assert s2["00:45"] == s2["01:00"] == "raccolta_sospesa"
    assert s2["01:15"] == "dato_non_disponibile"                  # dopo «Chiudi giornata»
    assert d2["avvisi"] == [] and "excel" in [a["app"] for a in d2["totali"]["rilevati"]["per_applicazione"]]
    assert Stato(base).giornata()["json_successivi"] == [r["giorni"][1]["json"]]


def test_pausa_prima_di_mezzanotte_chiusa_il_giorno_dopo(base, monkeypatch):
    """pausa alle 23:30 non ripresa, «Chiudi giornata» alle 00:50: il secondo giorno è in pausa da mezzanotte fino alla
    chiusura, poi «dato non disponibile» (non «raccolta sospesa» fino a fine giornata)."""
    g2 = dt.date(2026, 10, 6)
    orari = iter([T("23:00"), T("23:30"), T("00:50", giorno=g2)])
    monkeypatch.setattr(giornata, "_adesso", lambda: next(orari))
    giornata.avvia(base, presa_visione=True, lancia=False)
    reg = Registro(base); c = Campionatore(reg.scrivi)
    c.tick(T("23:00", 5), 10); c.tick(T("23:10"), 20, lambda: "WINWORD.EXE"); c.chiudi_fascia()
    giornata.pausa(base)
    r = giornata.chiudi(base, sigillo=False)
    d1, d2 = (json.load(open(x["json"], encoding="utf-8")) for x in r["giorni"])
    assert validate(d1) == [] and validate(d2) == []
    s1 = {f["ora"]: f["stato"] for f in d1["fasce"]}
    s2 = {f["ora"]: f["stato"] for f in d2["fasce"]}
    assert s1["23:45"] == "raccolta_sospesa"
    assert s2["00:00"] == s2["00:30"] == "raccolta_sospesa"
    assert s2["01:00"] == "dato_non_disponibile"
