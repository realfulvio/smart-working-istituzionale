"""Modalità «collector» predefinita (06/10/2026): il programma deve funzionare end-to-end in quella modalità.

Solo dati SINTETICI. Il processo di raccolta vero (collector/demone.py) gira in un thread con un modulo «win» finto
(le API di Windows non esistono sul box): niente processi reali, niente Outlook/COM, niente wevtutil."""
import datetime as dt
import json
import os
import runpy
import sys
import threading
import time
import types
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import collector
from aggregatore.cli import validate
from applicazione.servizio import Servizio, carica_impostazioni
from collector import demone, giornata
from collector.campionatore import Campionatore
from collector.percorsi import Percorsi
from collector.registro import Registro
from collector.stato import Stato
from resoconto.verifica import _testo_pagine, verifica_file

RADICE = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Europe/Rome")


def _righe(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(r) for r in f if r.strip()]


def _testo_standard(doc):
    return None, None, {"motivo": "test: testo standard"}


# ------------------------------------------------------------------------------- processo di raccolta (thread)
class _WinFinto:
    """Sostituto di collector.win: input sempre nuovo, primo piano alternato tra un programma dell'elenco del CED
    e uno sconosciuto (che non deve lasciare traccia), contatore SMB crescente."""

    def __init__(self):
        self.n = 0
        self.lanci = []
        self.word_osservato = threading.Event()

    def modulo(self):
        w = types.ModuleType("collector.win")
        fin = self

        def ultimo_input():
            fin.n += 1
            return 1000 + fin.n * 10

        def exe_primo_piano():
            if fin.n % 2: fin.word_osservato.set()
            return "WINWORD.EXE" if fin.n % 2 else "SCONOSCIUTO_PRIVATO.EXE"

        class ContatoreSMB:
            ok = True

            def __init__(self):
                self.v = 0

            def leggi(self):
                self.v += 7
                return self.v

        class Finestra:
            def __init__(self, on_timer, on_wts, on_power, on_timechange, on_fine, intervallo_ms):
                self.on_timer, self.fermo, self.wts_ok = on_timer, threading.Event(), True

            def ciclo(self):
                while not self.fermo.wait(0.02):
                    self.on_timer()

            def chiudi(self):
                self.fermo.set()

        w.ultimo_input, w.exe_primo_piano, w.ContatoreSMB, w.Finestra = ultimo_input, exe_primo_piano, ContatoreSMB, Finestra
        w.consumo_processo = lambda: {"cpu_s": 0.0, "ws_mb": 20.0, "picco_ws_mb": 21.0, "privata_mb": 12.0}
        # collector.giornata.meta li chiama quando sys.platform == "win32": senza, il test passava solo su Linux
        w.ram_gb, w.tipo_postazione = (lambda: 16.0), (lambda: "fisica")
        return w


@pytest.fixture
def raccolta(monkeypatch):
    """Il «lancio» del processo di raccolta esegue il demone vero in un thread (stesso comando e ambiente)."""
    finto = _WinFinto()
    mod = finto.modulo()
    monkeypatch.setitem(sys.modules, "collector.win", mod)
    monkeypatch.setattr(collector, "win", mod, raising=False)
    thread = []

    def popen(cmd, cwd=None, env=None, **k):
        assert cmd[-1] == "_esegui" and env and env.get("RSW_BASE")
        finto.lanci.append(cmd)
        t = threading.Thread(target=demone.esegui, args=(Percorsi(env["RSW_BASE"]),), daemon=True)
        t.start()
        thread.append(t)
        return types.SimpleNamespace(pid=os.getpid())

    monkeypatch.setattr(giornata, "subprocess", types.SimpleNamespace(Popen=popen, DEVNULL=-3))
    finto.thread = thread
    return finto


def test_collector_end_to_end_avvia_pausa_riprendi_chiudi_pdf(tmp_path, raccolta):
    base = tmp_path / "dati"
    imp = carica_impostazioni(str(base), str(tmp_path / "nessun_config.json"))
    assert imp["modalita"] == "collector"                                  # predefinita, senza alcun file
    imp.update(cartella_pdf=str(tmp_path / "pdf"), cache_ai=str(tmp_path / "cache"))
    s = Servizio(str(base), impostazioni=imp, motore_factory=_testo_standard)
    s.registra_informativa("Collaudo Sintetico (ESEMPIO)", "Sistemi Informativi")
    st = Stato(s.p)

    # «Avvia giornata»: il processo di raccolta parte
    giorno = s.avvia()
    assert len(raccolta.lanci) == 1 and st.demone_attivo()
    assert raccolta.word_osservato.wait(5), "campione ammesso non raggiunto"
    # «Pausa»: il processo si ferma da solo (comando) e scrive l'evento di pausa
    s.pausa()
    raccolta.thread[0].join(5)
    assert not raccolta.thread[0].is_alive() and not st.demone_attivo()
    assert st.demone()["motivo"] == "pausa" and s.stato()["fase"] == "in_pausa"
    # «Riprendi»: riparte
    s.riprendi()
    assert len(raccolta.lanci) == 2 and st.demone_attivo()
    time.sleep(0.3)
    s.aggiungi_manuale(giorno, "telefonata", "00:00", "00:10", "Telefonata di prova (dati sintetici)")
    # «Chiudi giornata – Genera resoconto»: il processo si ferma, l'aggregatore produce le fasce
    v = s.chiudi_e_genera(None, True)
    raccolta.thread[1].join(5)
    assert not raccolta.thread[1].is_alive() and st.demone()["motivo"] == "chiudi"
    r = v["chiusura"]
    righe = _righe(r["raw"])
    eventi = [(x["tipo"], x.get("evento")) for x in righe]
    assert ("raccolta", "pausa") in eventi and ("raccolta", "ripresa") in eventi and ("sessione", "fine_raccolta") in eventi
    assert {x["tipo"] for x in righe} <= {"meta", "sessione", "raccolta", "attivita", "app", "rete"}
    assert {x["exe"] for x in righe if x["tipo"] == "app"} == {"WINWORD.EXE"}           # solo l'elenco del CED
    assert any(x["tipo"] == "attivita" for x in righe) and not any(x["tipo"] == "rete" for x in righe)
    for x in righe:
        assert set(x) <= {"tipo", "ts", "evento", "exe", "operazioni", "giorno", "fuso", "modalita", "dipendente",
                          "postazione", "dati_tecnici_postazione", "versioni", "copertura_fonti", "stato_iniziale_sessione", "presa_visione"}, x
    doc = json.load(open(r["json"], encoding="utf-8"))
    assert validate(doc) == [] and doc["modalita"] == "collector"
    assert doc["copertura_fonti"]["attivita"] == "completa" and doc["copertura_fonti"]["app"] == "completa"
    assert doc["integrita"]["sigillo_tecnico"]                                         # sigillo tecnico
    attive = [f for f in doc["fasce"] if f["stato"] == "attivita_rilevata"]
    assert attive and any("word" in f["app"] for f in attive)
    assert len(doc["fasce"]) in (92, 96, 100)
    assert "SCONOSCIUTO" not in open(r["raw"], encoding="utf-8").read() + json.dumps(doc)
    # revisione → «Ho verificato la sintesi» → «Conferma e crea il PDF»: PDF sigillato e verificabile
    assert v["sintesi"]["origine_testo"]
    c = s.conferma(giorno, True)
    assert os.path.isfile(c["pdf"]) and Stato(s.p).giornata()["fase"] == "conclusa"
    fin = s.finale(giorno)
    assert fin["integrita"]["sigillo_finale"]["codice"] == c["codice"]
    esito = verifica_file(c["pdf"], [str(base / "chiave")])
    assert esito["esito"] == "VALIDO" and esito["testo_pdf"] == "corrisponde ai dati", esito
    testo = "\n".join(_testo_pagine(open(c["pdf"], "rb").read()))
    assert "Dati rilevati automaticamente" in testo and "SCONOSCIUTO" not in testo


def test_avvio_fallito_se_il_processo_non_parte(tmp_path, monkeypatch):
    """Se il processo di raccolta non parte la giornata resta avviata e l'errore è chiaro (nessun blocco silenzioso)."""
    monkeypatch.setattr(giornata, "subprocess", types.SimpleNamespace(Popen=lambda *a, **k: None, DEVNULL=-3))
    monkeypatch.setattr(giornata.time, "sleep", lambda s: None)
    s = Servizio(str(tmp_path / "d"), impostazioni=dict(carica_impostazioni(str(tmp_path / "d"), str(tmp_path / "x.json")),
                                                        cartella_pdf=str(tmp_path / "pdf")))
    s.registra_informativa("Collaudo Sintetico (ESEMPIO)", "")
    with pytest.raises(Exception, match="processo di raccolta non è partito"):
        s.avvia()


# ------------------------------------------------- «Nessuna attività informatica rilevata» solo con fonte coperta
def _T(hm, g=dt.date(2026, 10, 5)):
    h, m = map(int, hm.split(":"))
    return dt.datetime.combine(g, dt.time(h, m), TZ)


@pytest.mark.parametrize("modalita", ["collector", "consuntivo"])
def test_nessuna_attivita_solo_con_fonte_coperta(tmp_path, monkeypatch, modalita):
    g = dt.date(2026, 10, 5)
    orari = iter([_T("09:00"), _T("11:00")])
    monkeypatch.setattr(giornata, "_adesso", lambda: next(orari))
    base = tmp_path / modalita
    imp = dict(carica_impostazioni(str(base), str(tmp_path / "x.json")), modalita=modalita,
               cartella_pdf=str(tmp_path / "pdf"), cache_ai=str(tmp_path / "c"))
    s = Servizio(str(base), impostazioni=imp, adesso=lambda: _T("11:05"), motore_factory=_testo_standard)
    s.registra_informativa("Collaudo Sintetico (ESEMPIO)", "")
    giornata.avvia(s.p, presa_visione=True, lancia=False)
    if modalita == "collector":                       # eventi del campionatore solo tra le 09:00 e le 09:30
        c = Campionatore(Registro(s.p).scrivi, {"WINWORD.EXE"})
        c.tick(_T("09:00").replace(second=5), 10)
        c.tick(_T("09:01"), 20, lambda: "WINWORD.EXE")
        c.tick(_T("09:20"), 30, lambda: "WINWORD.EXE")
        c.chiudi_fascia()
    r = s.chiudi()
    doc = json.load(open(r["json"], encoding="utf-8"))
    st = {f["ora"]: f["stato"] for f in doc["fasce"]}
    fps = doc["totali"]["rilevati"]["fasce_per_stato"]
    if modalita == "collector":
        assert st["09:00"] == st["09:15"] == "attivita_rilevata"
        assert st["09:30"] == st["10:45"] == "nessuna_attivita_informatica_rilevata"
        assert fps["nessuna_attivita_informatica_rilevata"] == 6
    else:                                              # a consuntivo nessuna fonte: mai «nessuna attività»
        assert st["09:30"] == st["10:45"] == "dato_non_disponibile"
        assert fps.get("nessuna_attivita_informatica_rilevata", 0) == 0
    s.genera(g.isoformat())
    c = s.conferma(g.isoformat(), True)
    testo = "\n".join(_testo_pagine(open(c["pdf"], "rb").read()))
    attese = "6 fasce" if modalita == "collector" else "0 fasce"
    riga = [x for x in testo.splitlines() if "Nessuna attività informatica rilevata" in x]
    assert riga and any(attese in x for x in riga), riga


# --------------------------------------------------------------- eseguibile congelato: «RendicontoSW.exe _esegui»
def test_comando_del_processo_nell_eseguibile_congelato(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert giornata._comando_demone() == [sys.executable, "_esegui"]


def _app_entry(argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["RendicontoSW.exe"] + argv)
    with pytest.raises(SystemExit) as e:
        runpy.run_path(str(RADICE / "tools" / "pacchetto" / "app_entry.py"), run_name="__main__")
    return e.value.code


def test_app_entry_esegui_avvia_la_raccolta_e_non_la_finestra(tmp_path, monkeypatch):
    chiamate = []
    monkeypatch.setenv("RSW_BASE", str(tmp_path))
    monkeypatch.setattr(demone, "esegui", lambda p: chiamate.append(p.base))
    import applicazione.gui as gui
    monkeypatch.setattr(gui, "main", lambda *a, **k: pytest.fail("aperta la finestra al posto della raccolta"))
    assert _app_entry(["_esegui"], monkeypatch) == 0
    assert chiamate == [str(tmp_path)]


def test_app_entry_errore_della_raccolta_nel_log(tmp_path, monkeypatch):
    monkeypatch.setenv("RSW_BASE", str(tmp_path))

    def guasto(p):
        raise RuntimeError("guasto sintetico")
    monkeypatch.setattr(demone, "esegui", guasto)
    assert _app_entry(["_esegui"], monkeypatch) == 1
    log = (tmp_path / "diagnostica" / "collector.log").read_text(encoding="utf-8")
    assert "errore del processo di raccolta" in log and "guasto sintetico" in log


# ------------------------------------------------------------------------ testi per il dipendente (collector)
def test_informativa_breve_del_setup_descrive_il_collector():
    rtf = (RADICE / "tools" / "pacchetto" / "setup" / "informativa_breve.rtf").read_text(encoding="ascii")
    testo = rtf.replace("\\u224?", "à").replace("\\u232?", "è").replace("\\u233?", "é").replace("\\u236?", "ì") \
        .replace("\\u171?", "«").replace("\\u187?", "»")
    for atteso in ("Avvia giornata", "escluse le pause", "15 minuti", "solo sì/no", "elenco dei Sistemi Informativi",
                   "Rete e integrazione Halley disabilitate", "Web", "registro eventi", "Nulla prima di", "5.0.0"):
        assert atteso in testo, atteso
    for falso in ("Solo gli orari dei tuoi pulsanti", "Nessun programma resta attivo", "4.1.0"):
        assert falso not in testo, falso


def _testi(w):
    out = []
    try:
        t = w.cget("text")
        if t:
            out.append(str(t))
    except Exception:  # noqa: BLE001
        pass
    for c in w.winfo_children():
        out += _testi(c)
    return out


@pytest.mark.skipif(not os.environ.get("DISPLAY") and sys.platform != "win32", reason="serve un display")
@pytest.mark.parametrize("estensione", [False, True])
def test_testi_a_video_in_modalita_collector(tmp_path, estensione):
    import tkinter as tk
    from applicazione import gui
    base = tmp_path / "b"
    imp = dict(carica_impostazioni(str(base), str(tmp_path / "x.json")), cartella_pdf=str(tmp_path / "pdf"),
               estensione_browser=estensione)
    s = Servizio(str(base), impostazioni=imp)
    try:
        app = gui.App(s)
    except tk.TclError:
        pytest.skip("display non utilizzabile")
    try:
        app.update()
        t = " | ".join(_testi(app))
        assert "Cosa registra" in t and "Cosa non registra mai" in t
        assert all(x in t for x in gui.INFORMATIVA_COLLECTOR + gui.INFORMATIVA_MAI)
        assert (gui.INFORMATIVA_HALLEY if estensione else gui.INFORMATIVA_WEB) in t
        assert "Solo gli orari dei tuoi pulsanti" not in t and "nessun programma resta attivo" not in t
        s.registra_informativa("Collaudo Sintetico (ESEMPIO)", "")
        app.vai_oggi(); app.update()
        t = " | ".join(_testi(app))
        assert "Solo a giornata avviata: blocco e sblocco del computer" in t and "Conto solo" not in t
        app.mostra_cosa(); app.update()
        t = " | ".join(_testi(app))
        assert "escluse le pause" in t and "solo sì/no" in t and "disabilitata in questa edizione" in t
        assert ("Halley solo come nome" in t) == estensione
    finally:
        app.destroy()


# ------------------------------------------------------------------------ installer: PSModulePath e processo di raccolta
ISS = RADICE / "tools" / "pacchetto" / "setup" / "RendicontoSW.iss"
DISINSTALLA = RADICE / "tools" / "pacchetto" / "disinstalla.ps1"


def _funzione_pascal(testo, nome):
    i = testo.index(nome)
    return testo[i:testo.index("\nend;", i)]


def test_setup_powershell_con_psmodulepath_ripulito_in_installazione_e_disinstallazione():
    s = ISS.read_text(encoding="utf-8-sig")
    assert "external 'SetEnvironmentVariableW@kernel32.dll stdcall'" in s
    prep = _funzione_pascal(s, "procedure PreparaAmbientePowerShell;")
    assert "SetEnvironmentVariable('PSModulePath', Valore)" in prep
    for parte in ("{userdocs}') + '\\WindowsPowerShell\\Modules;'", "{commonpf64}') + '\\WindowsPowerShell\\Modules;'",
                  "{sys}') + '\\WindowsPowerShell\\v1.0\\Modules'"):
        assert parte in prep, parte
    assert "pwsh" not in prep.lower() and "PowerShell\\7" not in prep
    for nome in ("procedure EseguiInstalla;", "function EseguiDisinstalla("):
        corpo = _funzione_pascal(s, nome)
        assert "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File" in corpo
        assert corpo.index("PreparaAmbientePowerShell;") < corpo.index("Exec(PowerShellExe"), nome
    assert s.count("Exec(") == 2
    assert '#define AppVer "5.0.0"' in s


def test_setup_rileva_la_raccolta_in_installazione_e_la_lascia_a_disinstalla():
    s = ISS.read_text(encoding="utf-8-sig")
    proc = _funzione_pascal(s, "function ProcessiAperti: String;")
    assert "SELECT Name, ProcessId, ExecutablePath, CommandLine FROM Win32_Process" in proc
    assert "Pos(' _esegui ', Riga + ' ') > 0" in proc
    assert "if Raccolta and IsUninstaller then" in proc and "raccolta attività della giornata in corso" in proc
    assert "premi «Pausa»" in _funzione_pascal(s, "function AppChiusaOppureAnnulla(")
    # in installazione il processo resta tra quelli aperti: PrepareToInstall rifiuta come prima
    assert "AppChiusaOppureAnnulla('l''installazione si interrompe" in s


def test_disinstalla_ferma_la_raccolta_prima_del_controllo_dei_processi():
    s = DISINSTALLA.read_text(encoding="utf-8-sig")
    assert "Riga = [string]$_.CommandLine" in s
    i_stop = s.index("Stop-Raccolta $dest @($dati, $datiDefault)")
    assert i_stop < s.index("$proc = @(Get-ProcessiCartella $dest)")
    corpo = s[s.index("function Stop-Raccolta"):s.index("try { \"--- disinstalla Rendiconto SW ---\"")]
    assert "'(^|\\s)_esegui(\\s|$)'" in s
    assert "Stop-Process -Id $r.Pid -Force" in corpo and "AddSeconds(20)" in corpo
    for vietato in ("wevtutil", "Outlook", "Unblock-File", "Add-MpPreference"):
        assert vietato not in corpo


@pytest.mark.skipif(__import__("shutil").which("pwsh") is None, reason="pwsh non installato")
def test_disinstalla_chiede_la_pausa_al_processo_di_raccolta(tmp_path):
    """Stop-Raccolta vero (estratto da disinstalla.ps1) contro un processo di raccolta finto che legge comando.json con
    collector.stato: la pausa arriva, con un istante col fuso, e il processo esce da solo (niente Stop-Process)."""
    import subprocess
    dati = tmp_path / "dati"
    esito = tmp_path / "esito.json"
    finto = tmp_path / "finto.py"
    finto.write_text(
        "import datetime as dt, json, os, sys, time\n"
        f"sys.path.insert(0, {str(RADICE)!r})\n"
        "from collector.percorsi import Percorsi\nfrom collector.stato import Stato\n"
        f"st = Stato(Percorsi({str(dati)!r}))\n"
        "st.demone_avviato(os.getpid(), {'wts': False, 'smb': False, 'versione': 'test'})\n"
        "for _ in range(600):\n"
        "    c = st.leggi_comando()\n"
        "    if c:\n"
        "        t = dt.datetime.fromisoformat(c['ts'])\n"
        f"        open({str(esito)!r}, 'w').write(json.dumps({{'comando': c['comando'], 'fuso': t.utcoffset() is not None}}))\n"
        "        st.cancella_comando(); st.demone_terminato(c['comando']); sys.exit(0)\n"
        "    time.sleep(0.1)\n", encoding="utf-8")
    p = subprocess.Popen([sys.executable, str(finto)])
    threading.Thread(target=p.wait, daemon=True).start()     # su Linux il figlio uscito va raccolto (niente zombie)
    try:
        for _ in range(100):
            if (dati / "stato" / "demone.json").exists():
                break
            time.sleep(0.05)
        log = tmp_path / "log.txt"
        script = tmp_path / "prova.ps1"
        script.write_text(
            "$ErrorActionPreference = 'Stop'\n"
            f"$ast = [System.Management.Automation.Language.Parser]::ParseFile('{DISINSTALLA}', [ref]$null, [ref]$null)\n"
            "$f = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and "
            "$n.Name -in @('Get-ProcessiRaccolta', 'Stop-Raccolta') }, $true)\n"
            "foreach ($x in $f) { . ([scriptblock]::Create($x.Extent.Text)) }\n"
            f"function Scrivi-Log {{ param([string]$Msg) Add-Content -LiteralPath '{log}' -Value $Msg }}\n"
            "function Get-ProcessiCartella { param([string]$Cartella)\n"
            f"  $p = Get-Process -Id {p.pid} -ErrorAction SilentlyContinue\n"
            f"  if ($p) {{ return @([pscustomobject]@{{ Tipo = 'app'; Nome = 'RendicontoSW.exe'; Pid = {p.pid}; Path = 'x'; "
            "Riga = '\"C:\\x\\RendicontoSW.exe\" _esegui' }) }\n"
            "  return @() }\n"
            f"Stop-Raccolta 'C:\\x' @('{dati}', '{tmp_path / 'altrove'}')\n", encoding="utf-8")
        r = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File", str(script)], capture_output=True,
                           text=True, timeout=120)
        assert r.returncode == 0, r.stdout + r.stderr
        p.wait(timeout=10)
    finally:
        if p.poll() is None:
            p.kill()
    assert json.loads(esito.read_text(encoding="utf-8")) == {"comando": "pausa", "fuso": True}
    righe = log.read_text(encoding="utf-8")
    assert "Chiesta la pausa al processo di raccolta" in righe and "Processo di raccolta fermato." in righe
    assert "Processo di raccolta chiuso" not in righe            # uscito da solo, nessuna chiusura forzata
    assert p.returncode == 0
