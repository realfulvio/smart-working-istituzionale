"""5.0.1 – icona nell'area di notifica, chiusura accidentale della finestra, riaggancio dopo un riavvio, collegamenti
del Setup e icone. Solo dati sintetici in cartelle temporanee; nessun processo di raccolta reale (lancia=False)."""
import datetime as dt
import os
import re
import struct
import sys
from pathlib import Path

import pytest

from applicazione import area_notifica as an
from applicazione.servizio import Servizio
from collector import giornata as cg
from collector.stato import FUSO, Stato

RADICE = Path(__file__).resolve().parents[1]
ISS = RADICE / "tools" / "pacchetto" / "setup" / "RendicontoSW.iss"
TZ = FUSO()
OGGI = dt.date(2026, 10, 14)


def T(hm, giorno=OGGI):
    h, m = map(int, hm.split(":"))
    return dt.datetime.combine(giorno, dt.time(h, m), TZ)


class Orologio:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def _servizio(tmp_path, monkeypatch, modalita="collector", ora="08:00"):
    oro = Orologio(T(ora))
    monkeypatch.setattr(cg, "_adesso", oro)
    imp = {"modalita": modalita, "server_ai": str(tmp_path / "nessuno"), "modelli_ai": str(tmp_path / "m"),
           "cache_ai": str(tmp_path / "cache"), "thread_ai": 2, "profilo_ai": None,
           "cartella_pdf": str(tmp_path / "pdf"), "profili_siti": []}
    s = Servizio(str(tmp_path / "base"), imp, adesso=oro)
    s.orologio = oro
    s.registra_informativa("Rossi Maria (ESEMPIO)", "Ufficio di prova")
    return s


def _avvia_senza_raccolta(s):
    cg.avvia(s.p, presa_visione=True, lancia=False)


def _raw(s, giorno=OGGI):
    path = s.p.raw_giorno(giorno.isoformat())
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


# ------------------------------------------------------------------------------------------- logica pura
def test_stato_icona_e_suggerimento():
    assert an.stato_icona("in_corso") == "attiva"
    assert an.stato_icona("in_pausa") == "pausa"
    for f in (None, "nessuna", "da_avviare", "chiusa"):
        assert an.stato_icona(f) == "nessuna"
    t = an.suggerimento({"fase": "in_corso", "avvio": "2026-10-14T08:12:00+02:00", "modalita": "collector",
                         "raccolta_attiva": True})
    assert "in corso dalle 08:12" in t and "non attiva" not in t
    assert "raccolta non attiva" in an.suggerimento({"fase": "in_corso", "avvio": None, "modalita": "collector",
                                                     "raccolta_attiva": False})
    assert "in pausa dalle 12:30" in an.suggerimento({"fase": "in_pausa", "pausa_dalle": "2026-10-14T12:30:00+02:00"})
    assert "nessuna giornata" in an.suggerimento({"fase": "nessuna"})
    assert all(len(an.suggerimento({"fase": f, "avvio": "x" * 400})) <= 127 for f in ("in_corso", "in_pausa", None))


def test_menu_apri_pausa_riprendi_chiudi_esci():
    def comandi(fase):
        return {v[0]: v for v in an.voci_menu(fase) if v}
    c = comandi("in_corso")
    assert list(c) == ["apri", "pausa", "chiudi_giornata", "esci"]
    assert c["apri"][3] is True and all(v[2] for v in c.values())
    assert "riprendi" in comandi("in_pausa") and "pausa" not in comandi("in_pausa")
    n = comandi(None)
    assert n["pausa"][2] is False and n["chiudi_giornata"][2] is False and n["apri"][2] and n["esci"][2]
    assert n["esci"][1].endswith("…") and n["chiudi_giornata"][1].endswith("…")   # entrambe chiedono conferma


def test_mutex_per_cartella_dati():
    assert an.nome_mutex("C:/x/base") == an.nome_mutex("C:/x/base")
    assert an.nome_mutex("C:/x/base") != an.nome_mutex("C:/x/altra")
    assert an.nome_mutex("C:/x/base").startswith("Local\\RendicontoSW_Interfaccia_")


def test_area_notifica_non_raccoglie_dati():
    s = (RADICE / "applicazione" / "area_notifica.py").read_text(encoding="utf-8")
    for vietato in ("GetWindowText", "GetForegroundWindow", "SetWindowsHookEx", "GetAsyncKeyState", "keyboard",
                    "ImageGrab", "Registro(", "raw_giorno"):
        assert vietato not in s, vietato


# ------------------------------------------------------------------------------------------- riaggancio
def test_riaggancio_di_una_giornata_di_oggi_rimasta_in_corso(tmp_path, monkeypatch):
    s = _servizio(tmp_path, monkeypatch)
    _avvia_senza_raccolta(s)
    Stato(s.p).demone_terminato("spegnimento")
    s.orologio.t = T("09:40")
    lanciati = []
    monkeypatch.setattr(cg, "_lancia_demone", lambda p, st: lanciati.append(p.base))
    assert s.riaggancia() is True
    assert lanciati == [s.p.base]
    assert '"evento": "avvio_raccolta"' in _raw(s).splitlines()[-1] and "09:40" in _raw(s).splitlines()[-1]
    log = open(Stato(s.p).f_log, encoding="utf-8").read()
    assert "riaggancio della giornata 2026-10-14" in log and "spegnimento" in log
    assert s.stato_breve()["fase"] == "in_corso"


@pytest.mark.parametrize("caso", ["nessuna", "pausa", "ieri", "consuntivo", "processo_attivo"])
def test_nessuna_raccolta_senza_avvia_giornata(tmp_path, monkeypatch, caso):
    s = _servizio(tmp_path, monkeypatch, modalita="consuntivo" if caso == "consuntivo" else "collector")
    lanciati = []
    monkeypatch.setattr(cg, "_lancia_demone", lambda p, st: lanciati.append(p.base))
    if caso != "nessuna":
        _avvia_senza_raccolta(s)
    if caso == "pausa":
        cg.pausa(s.p)
    if caso == "ieri":
        s.orologio.t = T("08:30", OGGI + dt.timedelta(days=1))
    if caso == "processo_attivo":
        monkeypatch.setattr(Stato, "demone_attivo", lambda self: True)
    prima = _raw(s)
    assert s.riaggancia() is False
    assert lanciati == [] and _raw(s) == prima


def test_riaggancio_richiede_la_presa_visione(tmp_path, monkeypatch):
    s = _servizio(tmp_path, monkeypatch)
    _avvia_senza_raccolta(s)
    os.remove(Stato(s.p).f_presa)
    monkeypatch.setattr(cg, "_lancia_demone", lambda p, st: pytest.fail("raccolta senza presa visione"))
    assert s.riaggancia() is False


def test_avvio_all_accesso_resta_aperto_solo_con_una_giornata_di_oggi(tmp_path, monkeypatch):
    from applicazione.gui import deve_restare_aperta
    s = _servizio(tmp_path, monkeypatch)
    assert deve_restare_aperta(s) is False                       # nessuna giornata: esce subito
    _avvia_senza_raccolta(s)
    assert deve_restare_aperta(s) is True
    cg.pausa(s.p)
    assert deve_restare_aperta(s) is True                        # in pausa: solo icona, nessuna raccolta
    s.orologio.t = T("08:00", OGGI + dt.timedelta(days=1))
    assert deve_restare_aperta(s) is False                       # giornata di ieri: decide il dipendente
    os.remove(Stato(s.p).f_presa)
    assert deve_restare_aperta(s) is False


def test_avvio_all_accesso_senza_giornata_non_crea_finestre(tmp_path, monkeypatch):
    from applicazione import gui
    s = _servizio(tmp_path, monkeypatch)
    monkeypatch.setattr(an, "prima_istanza", lambda base: True)
    monkeypatch.setattr(gui, "App", lambda *a, **k: pytest.fail("nessuna finestra all'accesso senza giornata"))
    assert gui.avvia_interfaccia(s, avvio_sessione=True) == 0


def test_seconda_istanza_riporta_in_primo_piano_la_prima(tmp_path, monkeypatch):
    from applicazione import gui
    s = _servizio(tmp_path, monkeypatch)
    chiamate = []
    monkeypatch.setattr(an, "prima_istanza", lambda base: False)
    monkeypatch.setattr(an, "chiedi_apertura", lambda: chiamate.append("apri") or True)
    monkeypatch.setattr(gui, "App", lambda *a, **k: pytest.fail("seconda interfaccia"))
    assert gui.avvia_interfaccia(s) == 0 and chiamate == ["apri"]
    assert gui.avvia_interfaccia(s, avvio_sessione=True) == 0 and chiamate == ["apri"]   # all'accesso: silenziosa


@pytest.mark.skipif(sys.platform != "win32", reason="solo Windows")
def test_istanza_unica_con_mutex(tmp_path):
    base = str(tmp_path / "istanza")
    assert an.prima_istanza(base) is True
    assert an.prima_istanza(base) is False
    assert an.prima_istanza(str(tmp_path / "altra")) is True


@pytest.mark.skipif(sys.platform != "win32", reason="solo Windows")
def test_struttura_notifyicondata():
    import ctypes
    w = an._win32()
    assert ctypes.sizeof(w["NID"]) == (976 if ctypes.sizeof(ctypes.c_void_p) == 8 else 956)


@pytest.mark.skipif(sys.platform != "win32", reason="solo Windows")
def test_icona_vera_si_aggiunge_aggiorna_e_toglie(tmp_path):
    """Crea davvero l'icona (pochi decimi di secondo), cambia stato e la toglie: nessun comando eseguito."""
    from resoconto.edizione import icona
    comandi = []
    a = an.AreaNotifica(comandi.append, {k: str(icona(v)) for k, v in an.ICONE.items()})
    try:
        a.avvia({"fase": "in_corso", "avvio": "2026-10-14T08:00:00+02:00"})
        if not a.hwnd:
            pytest.skip("finestra Win32 non disponibile in questa sessione")
        assert a._w["user32"].FindWindowW(an.CLASSE, None)
        a.aggiorna({"fase": "in_pausa", "pausa_dalle": "2026-10-14T12:00:00+02:00"})
        assert an.chiedi_apertura() is True
        import time
        fine = time.monotonic() + 3
        while not comandi and time.monotonic() < fine:
            time.sleep(0.05)
        assert comandi == ["apri"]
    finally:
        a.chiudi()
    assert a.hwnd is None and not a.visibile


# ------------------------------------------------------------------------------------- finestra (Tk)
class AreaFinta:
    def __init__(self):
        self.visibile, self.hwnd, self.avvisi, self.stati, self.chiusa = True, 1, [], [], False

    def aggiorna(self, st):
        self.stati.append(st["fase"])

    def avviso(self, titolo, testo):
        self.avvisi.append((titolo, testo))

    def chiudi(self):
        self.chiusa = True


@pytest.fixture
def app(tmp_path, monkeypatch):
    import tkinter as tk
    from applicazione.gui import App
    s = _servizio(tmp_path, monkeypatch, modalita="consuntivo")
    try:
        a = App(s)
    except tk.TclError:
        pytest.skip("Tk non disponibile")
    a.area = AreaFinta()
    a.update()
    yield a
    try:
        a.destroy()
    except tk.TclError:
        pass


def test_chiusura_accidentale_con_giornata_avviata_resta_nell_area_di_notifica(app):
    app.azione_avvia(); app.update()
    area = app.area
    app.chiudi_finestra(); app.update()
    assert app.state() == "withdrawn" and app.winfo_exists()
    assert area.avvisi and "continua" in area.avvisi[-1][0].lower() and "riapri da qui" in area.avvisi[-1][1].lower()
    assert area.stati[-1] == "in_corso" and app.s.stato_breve()["fase"] == "in_corso"   # nessuna pausa implicita
    app._comando_area("apri"); app.update()
    assert app.state() == "normal"


def test_chiusura_senza_giornata_chiude_il_programma(app):
    area = app.area
    app.chiudi_finestra()
    assert area.chiusa                                   # icona tolta prima di uscire
    import tkinter as tk
    with pytest.raises(tk.TclError):
        app.winfo_exists()


def test_menu_pausa_riprendi_dall_icona(app):
    app.azione_avvia(); app.update()
    app._comando_area("pausa"); app.update()
    assert app.s.stato_breve()["fase"] == "in_pausa" and app.area.stati[-1] == "in_pausa"
    app._comando_area("riprendi"); app.update()
    assert app.s.stato_breve()["fase"] == "in_corso"


def test_chiudi_giornata_dall_icona_chiede_conferma(app):
    app.azione_avvia(); app.update()
    app.withdraw()
    app._comando_area("chiudi_giornata"); app.update()
    assert app.state() == "normal" and app.velo is not None
    assert app.s.stato_breve()["fase"] == "in_corso"     # nulla di chiuso senza conferma
    app.chiudi_velo()


def test_esci_dall_icona_con_conferma_e_pausa(app):
    app.azione_avvia(); app.update()
    area = app.area
    app.withdraw()
    app._comando_area("esci"); app.update()
    assert app.state() == "normal" and app.velo is not None
    assert app.s.stato_breve()["fase"] == "in_corso"     # finché non si conferma non cambia nulla
    from applicazione.tema import Bottone
    bottoni = []

    def cerca(w):
        if isinstance(w, Bottone):
            bottoni.append(w)
        for c in w.winfo_children():
            cerca(c)
    cerca(app.velo)
    esci = [b for b in bottoni if "Metti in pausa ed esci" in b.lab.cget("text")]
    assert esci, "manca il pulsante esplicito «Metti in pausa ed esci»"
    assert any(b.lab.cget("text") == "Annulla" for b in bottoni)
    s = app.s
    esci[0]._click(None)
    assert s.stato_breve()["fase"] == "in_pausa" and area.chiusa


# ------------------------------------------------------------------------------------------- Setup
def _sezione(s, nome):
    m = re.search(r"^\[" + nome + r"\]\s*$(.*?)(?=^\[|\Z)", s, re.M | re.S)
    assert m, nome
    return [r for r in m.group(1).splitlines() if r.strip() and not r.lstrip().startswith(";")]


def test_setup_crea_collegamenti_desktop_start_e_accesso():
    s = ISS.read_text(encoding="utf-8-sig")
    tasks = _sezione(s, "Tasks")
    assert any('Name: "desktop"' in r for r in tasks) and any('Name: "accesso"' in r for r in tasks)
    assert not any("unchecked" in r for r in tasks)          # opzioni già spuntate
    icone = _sezione(s, "Icons")
    assert len(icone) == 5 and all("Check: InstallaRiuscita" in r for r in icone)
    def riga(prefisso, exe):
        return [r for r in icone if r.startswith(f'Name: "{prefisso}') and f'{{app}}\\{exe}"' in r]
    assert riga("{autoprograms}\\Resoconto lavoro agile", "RendicontoSW.exe")
    assert riga("{autoprograms}\\Verifica resoconto", "VerificaRendiconto.exe")
    assert "Tasks: desktop" in riga("{autodesktop}\\Resoconto lavoro agile", "RendicontoSW.exe")[0]
    assert "Tasks: desktop" in riga("{autodesktop}\\Verifica resoconto", "VerificaRendiconto.exe")[0]
    avvio = riga("{userstartup}\\", "RendicontoSW.exe")[0]
    assert 'Parameters: "--avvio-sessione"' in avvio and "Tasks: accesso" in avvio
    canc = _sezione(s, "InstallDelete")
    assert sum("Tasks: not desktop" in r for r in canc) == 2 and any("Tasks: not accesso" in r for r in canc)
    assert "if CurPageID = wpSelectTasks then" in s and "SetupIconFile={#IconaSetup}" in s
    assert "PrivilegesRequired=lowest" in s                     # tutto per utente: nessun HKLM, nessun servizio
    assert "HKLM" not in s.replace("HKEY_LOCAL_MACHINE", "") and "[Registry]" not in s


def test_disinstallazione_toglie_anche_desktop_e_avvio():
    s = (RADICE / "tools" / "pacchetto" / "disinstalla.ps1").read_text(encoding="utf-8-sig")
    corpo = s[s.index("function Rimuovi-CollegamentiPerBersaglio"):s.index("function Rimuovi-HostBrowserSeNostri")]
    for luogo in ("GetFolderPath('Startup')", "GetFolderPath('Desktop')", "Start Menu\\Programs"):
        assert luogo in corpo, luogo
    assert "Resoconto lavoro agile (ripresa giornata).lnk" in corpo


def test_compila_setup_usa_l_icona_dell_edizione():
    s = (RADICE / "tools" / "pacchetto" / "setup" / "compila_setup.ps1").read_text(encoding="utf-8-sig")
    assert "config\\icone\\setup.ico" in s and "/DIconaSetup=" in s
    b = (RADICE / "tools" / "pacchetto" / "build_app.ps1").read_text(encoding="utf-8-sig")
    assert '"rendiconto.ico") --name RendicontoSW' in b and '"verifica.ico") --name VerificaRendiconto' in b



# ------------------------------------------------------------------------------------------- icone
def _formati_ico(path):
    b = Path(path).read_bytes()
    _, tipo, n = struct.unpack("<HHH", b[:6])
    assert tipo == 1
    out = []
    for i in range(n):
        w, h, _, _, _, bpp, size, off = struct.unpack("<BBBBHHII", b[6 + 16 * i:22 + 16 * i])
        out.append((w or 256, bpp, b[off:off + 8] == b"\x89PNG\r\n\x1a\n"))
    return out


def test_icone_multirisoluzione():
    from tools.crea_icone import NOMI
    for nome in NOMI:
        f = _formati_ico(RADICE / "applicazione/assets/icone" / f"{nome}.ico")
        assert {16, 20, 24, 32, 40, 48, 64, 256} <= {w for w, _, _ in f}, nome
        assert all(bpp == 32 for _, bpp, _ in f)
        assert [png for w, _, png in f if w == 256] == [True] and not any(png for w, _, png in f if w < 256)


def test_icone_riproducibili_dai_token(tmp_path):
    """Le icone neutre nel repository sono esattamente quelle del generatore con i token neutri."""
    import json
    from tools.crea_icone import NOMI, crea
    crea(tmp_path / "neutra", json.loads((RADICE / "config/design_tokens.json").read_text(encoding="utf-8-sig")))
    for nome in NOMI:
        assert (tmp_path / "neutra" / f"{nome}.ico").read_bytes() == \
            (RADICE / "applicazione/assets/icone" / f"{nome}.ico").read_bytes(), nome


def _overlay_di_prova(tmp_path):
    """Overlay sintetico (cartella assoluta) con token diversi e icone generate da quei token."""
    import json
    import shutil
    from tools.crea_icone import crea
    ov = tmp_path / "overlay_prova"
    ov.mkdir()
    for nome in ("ente.json", "identita.json"):
        shutil.copyfile(RADICE / "config" / nome, ov / nome)
    token = json.loads((RADICE / "config/design_tokens.json").read_text(encoding="utf-8-sig"))
    token.update({"primary": "#2E7D32", "primary-800": "#1B5E20", "stemma-gold": "#F9A825"})
    (ov / "design_tokens.json").write_text(json.dumps(token), encoding="utf-8")
    crea(ov / "icone", token)
    return ov


def test_icona_dell_edizione_e_materializzazione(tmp_path, monkeypatch):
    from resoconto import edizione
    from tools import configura_edizione
    monkeypatch.setenv("RENDICONTO_EDIZIONE", "neutra")
    assert edizione.icona("tray_attiva.ico") == RADICE / "applicazione/assets/icone/tray_attiva.ico"
    dest_neutra = tmp_path / "config_neutra"
    configura_edizione.prepara(dest_neutra)
    assert not (dest_neutra / "icone").exists()            # la neutra usa le icone in applicazione/assets/icone
    ov = _overlay_di_prova(tmp_path)
    monkeypatch.setenv("RENDICONTO_EDIZIONE", str(ov))
    assert edizione.icona("tray_attiva.ico") == ov / "icone" / "tray_attiva.ico"
    assert (ov / "icone/rendiconto.ico").read_bytes() != (RADICE / "applicazione/assets/icone/rendiconto.ico").read_bytes()
    dest = tmp_path / "config"
    configura_edizione.prepara(dest)
    assert sorted(p.name for p in (dest / "icone").iterdir()) == sorted(p.name for p in (ov / "icone").iterdir())
