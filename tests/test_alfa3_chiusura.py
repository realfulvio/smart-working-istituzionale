"""Collaudo ALFA3 (06/10/2026).

N1 BLOCCANTE: «Chiudi giornata» nell'exe falliva con ModuleNotFoundError: No module named 'estensione' (pacchetto non
nell'eseguibile, importato dalla chiusura a consuntivo anche con estensione_browser false).
N2: dopo l'errore la giornata risultava «chiusa» senza resoconto e non si poteva rigenerare.
Qui la chiusura si prova con il pacchetto «estensione» reso introvabile, come nell'eseguibile."""
from __future__ import annotations

import datetime as dt
import importlib.abc
import json
import os
import sys

import pytest

from applicazione.servizio import ErroreApp, Servizio
from collector import giornata as cg
from collector.stato import FUSO, Stato

TZ = FUSO()


def T(h, m, s=0):
    return dt.datetime(2026, 10, 6, h, m, s, tzinfo=TZ)


class Orologio:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class _SenzaEstensione(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name == "estensione" or name.startswith("estensione."):
            raise ModuleNotFoundError(f"No module named '{name}'", name=name)
        return None


@pytest.fixture
def senza_estensione(monkeypatch):
    """Come nell'eseguibile ALFA: il pacchetto estensione non esiste."""
    for k in [k for k in sys.modules if k == "estensione" or k.startswith("estensione.")]:
        monkeypatch.delitem(sys.modules, k)
    finder = _SenzaEstensione()
    sys.meta_path.insert(0, finder)
    yield
    sys.meta_path.remove(finder)


def _lettore(giorno):
    return {"eventi": [("sessione", T(7, 50), {"evento": "accesso"}), ("web", T(8, 20), {"sito": "halley"}),
                       ("web", T(9, 5), {"sito": "halley"})],
            "copertura": {"sessione": "completa", "browser": "parziale", "attivita": "non_installato",
                          "app": "non_installato", "rete": "non_installato"}, "stato_iniziale": "chiusa"}


def _srv(tmp_path, oro, monkeypatch, **imp_extra):
    monkeypatch.setattr(cg, "_adesso", oro)
    imp = {"modalita": "consuntivo", "server_ai": str(tmp_path / "nessuno"), "modelli_ai": str(tmp_path / "m"),
           "cache_ai": str(tmp_path / "c"), "thread_ai": 2, "profilo_ai": None, "cartella_pdf": str(tmp_path / "pdf"),
           "profili_siti": [],
           "estensione_browser": False, "filigrana_pdf": None}
    imp.update(imp_extra)
    s = Servizio(str(tmp_path / "base"), imp, adesso=oro, lettore=_lettore)
    s.registra_informativa("Prova (ESEMPIO)", "Ufficio")
    return s


def _giornata(s, oro):
    oro.t = T(8, 0)
    s.avvia()
    oro.t = T(9, 30)


# ------------------------------------------------------------------------------------------------ N1
def test_n1_chiusura_consuntivo_senza_pacchetto_estensione(tmp_path, monkeypatch, senza_estensione):
    oro = Orologio(T(8, 0))
    s = _srv(tmp_path, oro, monkeypatch)
    _giornata(s, oro)
    r = s.chiudi()
    assert os.path.isfile(r["json"]) and r["avvisi"] == []
    assert Stato(s.p).giornata()["fase"] == "chiusa"
    assert "estensione" not in sys.modules
    with open(r["json"], encoding="utf-8") as f:
        d = json.load(f)
    assert [x["ora"] for x in d["fasce"] if x["stato"] == "attivita_rilevata"] == ["08:15", "09:00"]


def test_n1_estensione_attiva_ma_non_installata_non_blocca(tmp_path, monkeypatch, senza_estensione):
    oro = Orologio(T(8, 0))
    monkeypatch.setattr(cg, "ATTESA_FLUSH_ESTENSIONE_S", 0)
    s = _srv(tmp_path, oro, monkeypatch, estensione_browser=True)
    _giornata(s, oro)
    r = s.chiudi()
    assert os.path.isfile(r["json"])
    assert any("non installata" in a for a in r["avvisi"])
    assert Stato(s.p).giornata()["fase"] == "chiusa"


def test_n1_flusso_completo_fino_al_pdf_senza_estensione(tmp_path, monkeypatch, senza_estensione):
    """Avvia → attività dichiarata → chiudi e genera (funzione del pulsante) → conferma: PDF VALIDO."""
    from resoconto.verifica import verifica_file
    oro = Orologio(T(8, 0))
    s = _srv(tmp_path, oro, monkeypatch)
    _giornata(s, oro)
    s.aggiungi_manuale("2026-10-06", "riunione", "08:30", "09:00", "Riunione")
    v = s.chiudi_e_genera(None, True)
    assert v["sintesi"]["origine_testo"] == "testo_standard"
    r = s.conferma("2026-10-06", True)
    assert Stato(s.p).giornata()["fase"] == "conclusa"
    e = verifica_file(r["pdf"], [os.path.join(s.p.base, "chiave")])
    assert e["esito"] == "VALIDO", e


# ------------------------------------------------------------------------------------------------ N2
def _righe_raw(s, giorno="2026-10-06"):
    with open(s.p.raw_giorno(giorno), encoding="utf-8") as f:
        return [r for r in f.read().splitlines() if r.strip()]


def test_n2_errore_in_chiusura_non_marca_chiusa_e_riprova(tmp_path, monkeypatch):
    oro = Orologio(T(8, 0))
    s = _srv(tmp_path, oro, monkeypatch)
    _giornata(s, oro)
    import aggregatore.cli as acli
    vero = acli.main

    def rotto(args):
        raise RuntimeError("guasto simulato nell'aggregazione")
    monkeypatch.setattr(acli, "main", rotto)
    with pytest.raises(ErroreApp) as e:
        s.chiudi()
    assert "Riprova" in str(e.value)
    g = Stato(s.p).giornata()
    assert g["fase"] == "in_chiusura" and "guasto simulato" in g["errore_chiusura"]["errore"]
    assert not os.path.exists(s.p.json_giorno("2026-10-06"))
    st = s.stato()
    assert st["fase"] == "chiusura_da_completare" and "guasto simulato" in st["errore"]
    assert st["chiusura"] == T(9, 30).isoformat()
    assert "2026-10-06" not in st["da_confermare"]
    with pytest.raises(ErroreApp):
        s.avvia()                                   # la giornata non si sovrascrive né si riapre
    righe_dopo_errore = _righe_raw(s)
    # secondo errore: il grezzo non cresce (nessuna duplicazione degli eventi letti)
    with pytest.raises(ErroreApp):
        s.riprova_chiusura()
    assert _righe_raw(s) == righe_dopo_errore
    monkeypatch.setattr(acli, "main", vero)
    oro.t = T(10, 15)                               # «Riprova» più tardi: l'ora di chiusura resta 09:30
    r = s.riprova_chiusura()
    g = Stato(s.p).giornata()
    assert g["fase"] == "chiusa" and "errore_chiusura" not in g and g["json"] == r["json"]
    assert g["fasi"][-1]["chiusura"] == T(9, 30).isoformat()
    righe = _righe_raw(s)
    web = [x for x in righe if '"web"' in x]
    assert len(web) == 2, righe                     # 08:20 e 09:05, una volta sola
    assert not os.path.exists(s.p.raw_giorno("2026-10-06") + ".prima_della_chiusura")
    assert s.stato()["da_confermare"] == ["2026-10-06"]


def test_n2_stato_alfa3_chiusa_senza_json_si_rigenera(tmp_path, monkeypatch):
    """Stato lasciato dall'ALFA3: fase «chiusa», chiusura valorizzata, nessun giorni/<data>.json."""
    oro = Orologio(T(8, 0))
    s = _srv(tmp_path, oro, monkeypatch)
    _giornata(s, oro)
    from collector.registro import Registro
    Registro(s.p).scrivi("sessione", T(9, 30), evento="fine_raccolta")
    st = Stato(s.p)
    g = st.giornata()
    g["fase"] = "chiusa"
    g["fasi"][-1]["chiusura"] = T(9, 30).isoformat()
    st.salva_giornata(g)
    assert cg.chiusura_da_completare(s.p)
    assert s.stato()["fase"] == "chiusura_da_completare"
    v = s.chiudi_e_genera(None, True, riprova=True)
    assert os.path.isfile(v["chiusura"]["json"]) and v["sintesi"]
    assert Stato(s.p).giornata()["fase"] == "chiusa"
    assert s.stato()["fase"] == "da_avviare" and s.stato()["da_confermare"] == ["2026-10-06"]
    r = s.conferma("2026-10-06", True)
    assert os.path.isfile(r["pdf"]) and Stato(s.p).giornata()["fase"] == "conclusa"


def test_n2_errore_nel_lettore_ripristina_e_riprova(tmp_path, monkeypatch):
    oro = Orologio(T(8, 0))
    s = _srv(tmp_path, oro, monkeypatch)
    _giornata(s, oro)
    chiamate = {"n": 0}

    def lettore_instabile(giorno):
        chiamate["n"] += 1
        if chiamate["n"] == 1:
            raise OSError("registro eventi non leggibile")
        return _lettore(giorno)
    s._lettore = lettore_instabile
    with pytest.raises(ErroreApp):
        s.chiudi()
    assert s.stato()["fase"] == "chiusura_da_completare"
    s.riprova_chiusura()
    assert Stato(s.p).giornata()["fase"] == "chiusa"


def test_n2_giornata_su_due_giorni_errore_sul_secondo_toglie_il_primo_json(tmp_path, monkeypatch):
    oro = Orologio(T(22, 0))
    s = _srv(tmp_path, oro, monkeypatch)
    s.avvia()
    oro.t = dt.datetime(2026, 10, 7, 1, 0, tzinfo=TZ)
    import aggregatore.cli as acli
    vero = acli.main
    n = {"c": 0}

    def secondo_rotto(args):
        n["c"] += 1
        if n["c"] == 2:
            return 3
        return vero(args)
    monkeypatch.setattr(acli, "main", secondo_rotto)
    with pytest.raises(ErroreApp):
        s.chiudi()
    assert not os.path.exists(s.p.json_giorno("2026-10-06"))
    assert not os.path.exists(s.p.json_giorno("2026-10-07"))
    monkeypatch.setattr(acli, "main", vero)
    r = s.riprova_chiusura()
    assert [x["giorno"] for x in r["giorni"]] == ["2026-10-06", "2026-10-07"]


def test_n2_completa_chiusura_senza_chiusura_pendente(tmp_path, monkeypatch):
    oro = Orologio(T(8, 0))
    s = _srv(tmp_path, oro, monkeypatch)
    with pytest.raises(ErroreApp):
        s.riprova_chiusura()


# ------------------------------------------------------------------------------- interfaccia (Tk)
@pytest.fixture
def tk_ok():
    import tkinter as tk
    try:
        r = tk.Tk()
        r.destroy()
    except tk.TclError:
        pytest.skip("Tk non disponibile")


def test_n2_home_mostra_riprova_e_il_pulsante_completa(tmp_path, monkeypatch, tk_ok, senza_estensione):
    from applicazione.gui import App
    from applicazione.smoke import _bottoni
    oro = Orologio(T(8, 0))
    s = _srv(tmp_path, oro, monkeypatch)
    _giornata(s, oro)
    import aggregatore.cli as acli
    vero = acli.main
    monkeypatch.setattr(acli, "main", lambda a: (_ for _ in ()).throw(RuntimeError("guasto")))
    with pytest.raises(ErroreApp):
        s.chiudi()
    monkeypatch.setattr(acli, "main", vero)
    import tkinter as tk
    try:
        app = App(s)
    except tk.TclError as e:      # alcuni runner Windows non riescono a leggere init.tcl alla seconda radice Tk
        pytest.skip(f"Tk non utilizzabile in questo ambiente: {str(e).splitlines()[0]}")
    app.withdraw()
    try:
        assert not _bottoni(app, "Avvia giornata")
        b = _bottoni(app, "Riprova la chiusura")
        assert b, "pulsante «Riprova la chiusura» assente"
        b[0]._click()
        for _ in range(200):
            app.update()
            if getattr(app, "bt_conferma", None) is not None and app.bt_conferma.winfo_exists() and not app._occupato:
                break
            app.after(20)
        assert Stato(s.p).giornata()["fase"] == "chiusa"
        assert os.path.isfile(s.p.json_giorno("2026-10-06"))
    finally:
        app.destroy()


# ------------------------------------------------------------------------- collaudo --smoke-giornata
@pytest.mark.parametrize("finestra", [True, False])
def test_smoke_giornata_senza_estensione_pdf_valido(tmp_path, senza_estensione, finestra):
    from applicazione.smoke import esegui
    from resoconto.verifica import verifica_file
    if finestra:
        import tkinter as tk
        try:
            tk.Tk().destroy()
        except tk.TclError:
            pytest.skip("Tk non disponibile")
    esito = tmp_path / "esito.json"
    codice = esegui(str(tmp_path / "sandbox"), str(esito), finestra=finestra, testo_standard=True, timeout_s=120)
    r = json.loads(esito.read_text(encoding="utf-8"))
    assert codice == 0 and r["ok"], r
    assert [p["passo"] for p in r["passi"]] == ["avvia", "attivita_dichiarata", "chiudi_giornata", "conferma_pdf"]
    assert r["fase_finale"] == "conclusa" and r["manuali"] == 1
    assert r["modalita"] == ("finestra" if finestra else "senza_finestra")
    e = verifica_file(r["pdf"], [str(tmp_path / "sandbox" / "chiave")])
    assert e["esito"] == "VALIDO", e
    assert "estensione" not in sys.modules


def test_smoke_giornata_rifiuta_cartella_non_pulita(tmp_path, senza_estensione):
    from applicazione.smoke import esegui
    base = tmp_path / "sb"
    assert esegui(str(base), str(tmp_path / "e1.json"), finestra=False, testo_standard=True) == 0
    assert esegui(str(base), str(tmp_path / "e2.json"), finestra=False, testo_standard=True) == 1


def test_entry_congelato_inoltra_smoke_giornata(tmp_path, monkeypatch, senza_estensione):
    """app_entry.py → applicazione.gui.main: l'opzione --smoke-giornata arriva all'eseguibile."""
    import runpy
    radice = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    esito = tmp_path / "e.json"
    monkeypatch.setattr(sys, "argv", ["RendicontoSW.exe", "--smoke-giornata", str(tmp_path / "sb"), "--esito",
                                      str(esito), "--senza-finestra", "--testo-standard"])
    with pytest.raises(SystemExit) as e:
        runpy.run_path(os.path.join(radice, "tools", "pacchetto", "app_entry.py"), run_name="__main__")
    assert e.value.code == 0, esito.read_text(encoding="utf-8")


def test_n6_assistente_accanto_all_exe_anche_con_config_del_pacchetto(tmp_path, monkeypatch):
    """Il config/app.json del pacchetto punta a %LOCALAPPDATA%\\Programs\\RendicontoSW\\ai: con installazione
    altrove (-Destinazione) l'assistente accanto all'exe va usato comunque; se il percorso configurato esiste resta."""
    import json
    import sys
    from applicazione import servizio
    inst = tmp_path / "altrove" / "RendicontoSW"
    exe = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    (inst / "ai" / "llama").mkdir(parents=True)
    (inst / "ai" / "modelli").mkdir()
    (inst / "ai" / "llama" / exe).write_bytes(b"x")
    cfg = tmp_path / "app.json"
    cfg.write_text(json.dumps({"server_ai": str(tmp_path / "Programs" / "RendicontoSW" / "ai" / "llama" / exe),
                               "modelli_ai": str(tmp_path / "Programs" / "RendicontoSW" / "ai" / "modelli")}),
                   encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(inst / "RendicontoSW.exe"))
    imp = servizio.carica_impostazioni(str(tmp_path / "dati"), str(cfg))
    assert imp["server_ai"] == str(inst / "ai" / "llama" / exe)
    assert imp["modelli_ai"] == str(inst / "ai" / "modelli")
    # percorso configurato esistente: non si tocca
    altro = tmp_path / "ced" / exe
    altro.parent.mkdir()
    altro.write_bytes(b"x")
    cfg.write_text(json.dumps({"server_ai": str(altro)}), encoding="utf-8")
    assert servizio.carica_impostazioni(str(tmp_path / "dati"), str(cfg))["server_ai"] == str(altro)
    # non congelato: nessun ripiego
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    cfg.write_text(json.dumps({"server_ai": str(tmp_path / "manca" / exe)}), encoding="utf-8")
    assert servizio.carica_impostazioni(str(tmp_path / "dati"), str(cfg))["server_ai"] == str(tmp_path / "manca" / exe)
