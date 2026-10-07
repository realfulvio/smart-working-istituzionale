"""M7 – interfaccia: importazione, assenza di caratteri non gestiti da Tk 8.6 su Windows, prova a video se c'è un display."""
import os
import subprocess
import sys

import pytest

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_import_senza_display():
    import applicazione.gui  # noqa: F401
    import verificatore.gui  # noqa: F401


@pytest.mark.parametrize("f", ["applicazione/gui.py", "applicazione/tema.py", "verificatore/gui.py"])
def test_solo_caratteri_bmp(f):
    """Tk 8.6 su Windows non disegna i caratteri fuori dal piano base (es. emoji): niente nei testi."""
    s = open(os.path.join(RADICE, f), encoding="utf-8").read()
    assert not [c for c in s if ord(c) > 0xFFFF]


def test_interfaccia_non_raccoglie_dati_vietati():
    s = open(os.path.join(RADICE, "applicazione", "gui.py"), encoding="utf-8").read()
    for vietato in ("GetWindowText", "GetForegroundWindow", "keyboard", "pynput", "SetWindowsHookEx", "ImageGrab"):
        assert vietato not in s


@pytest.mark.skipif(not os.environ.get("DISPLAY") and sys.platform != "win32", reason="serve un display")
def test_flusso_a_video(tmp_path):
    """Avvia l'applicazione vera su un display, percorre le schermate principali (dati di esempio)."""
    import datetime as dt
    import tkinter as tk
    from applicazione.gui import App
    from applicazione.servizio import Servizio
    from collector import giornata as cg
    from tests.test_servizio import T, Orologio, lettore
    oro = Orologio(T("07:58"))
    cg._adesso = oro
    imp = {"modalita": "consuntivo", "server_ai": "/x", "modelli_ai": "/x", "cache_ai": str(tmp_path / "c"), "thread_ai": 2,
           "profilo_ai": None, "cartella_pdf": str(tmp_path / "pdf"), "profili_siti": [], "browser": True, "posta": False,
           "filigrana_pdf": "PROVA"}
    s = Servizio(str(tmp_path / "b"), imp, adesso=oro, lettore=lettore)
    try:
        app = App(s)
    except tk.TclError:
        pytest.skip("display non utilizzabile")
    try:
        assert app.velo is not None                     # informativa al primo avvio
        s.registra_informativa("Rossi Maria (ESEMPIO)", "Tributi")
        app.vai_oggi(); app.update()
        app.azione_avvia(); app.update()
        assert s.stato()["fase"] == "in_corso"
        oro.t = T("12:40")
        app.azione_chiudi()
        while app._occupato:
            app.update(); app.after(50)
        app.update()
        g = s.stato()["da_confermare"][0]
        app.vai_revisione(g); app.update()
        app.azione_genera(g)
        while app._occupato:
            app.update(); app.after(50)
        app.vai_revisione(g); app.update()
        assert not app.bt_conferma._attivo              # serve «Ho verificato la sintesi»
        app.ho_verificato.set(True); app._aggiorna_conferma(s.documento(g)); app.update()
        assert app.bt_conferma._attivo
        app.azione_conferma(g)
        while app._occupato:
            app.update(); app.after(50)
        assert s.resoconti_salvati()[0]["pdf"]
        app.mostra_informazioni(); app.update()
        app.vai_salvati(); app.vai_aiuto(); app.update()
        v = app.apri_verificatore(); v.mostra(s.resoconti_salvati()[0]["pdf"]); app.update()
        assert v.risultato["esito"] in ("VALIDO", "INTEGRO")
    finally:
        app.destroy()


def test_verificatore_riga_di_comando(tmp_path):
    fin = os.path.join(RADICE, "examples", "01_giornata_ufficio", "finale.json")
    chiavi = os.path.join(RADICE, "examples", "chiavi_registrate")
    r = subprocess.run([sys.executable, "-m", "verificatore", fin, "--chiavi", chiavi], cwd=RADICE,
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.startswith("VALIDO")
    import json
    d = json.load(open(fin, encoding="utf-8")); d["giorno"] = "2026-10-06"
    p = tmp_path / "x.json"; p.write_text(json.dumps(d), encoding="utf-8")
    r = subprocess.run([sys.executable, "-m", "verificatore", str(p)], cwd=RADICE, capture_output=True, text=True)
    assert r.returncode == 1 and r.stdout.startswith("ALTERATO")


def test_percorso_breve_nasconde_la_cartella_personale(monkeypatch, tmp_path):
    import os
    from applicazione.gui import percorso_breve
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("USERPROFILE", str(tmp_path))
    p = os.path.join(str(tmp_path), "Documents", "Rendiconti lavoro agile")
    assert percorso_breve(p) == "…" + os.sep + os.path.join("Documents", "Rendiconti lavoro agile")
    assert os.path.basename(str(tmp_path)) not in percorso_breve(p)
    assert percorso_breve("/altro/percorso") == os.path.normpath("/altro/percorso")


def test_verificatore_non_mostra_la_cartella_personale():
    import inspect
    from verificatore import gui as vg
    assert "percorso_breve(reg)" in inspect.getsource(vg)


def test_percorso_breve_oscura_anche_alias_windows(monkeypatch, tmp_path):
    from applicazione import tema
    import os
    home = str(tmp_path)
    alias = "C:\\Users\\ESEMPI~1\\AppData\\registro.json"
    monkeypatch.setenv("USERPROFILE", home)
    monkeypatch.setenv("HOME", home)
    monkeypatch.setattr(tema, "_percorso_esteso", lambda p: os.path.join(home, "AppData", "registro.json") if p == alias else p)
    assert tema.percorso_breve(alias) == "…" + os.sep + os.path.join("AppData", "registro.json")


@pytest.mark.skipif(not os.environ.get("DISPLAY") and sys.platform != "win32", reason="serve un display")
def test_logo_appartiene_al_proprio_interprete(tmp_path):
    import tkinter as tk
    from applicazione.servizio import Servizio
    from applicazione.gui import App
    other = tk.Tk(); other.withdraw()
    app = None
    try:
        try:
            app = App(Servizio(str(tmp_path)))
        except tk.TclError as e:
            if any(message in str(e) for message in ("Can't find a usable tk.tcl", "Can't find a usable init.tcl")):
                pytest.skip("bootstrap Tcl/Tk non disponibile; ripetere isolatamente")
            raise  # Errori di immagini o dell'app restano errori, non skip.
        app.update()
        assert app.img_stemma is not None
        assert str(app.img_stemma) in app.tk.call("image", "names")
        assert app.img_stemma.tk is app.tk
    finally:
        if app is not None: app.destroy()
        other.destroy()
