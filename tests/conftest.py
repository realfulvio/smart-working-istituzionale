"""Sicurezza dei test: mai toccare Outlook/COM reali, Office, registro eventi, né lanciare processi di ufficio.

Un test che chiamava il COM reale aveva avviato OUTLOOK.EXE -Embedding su una postazione di sviluppo.
Questo modulo rende impossibile ripetere la cosa: Dispatch/GetActiveObject e le esecuzioni di Office falliscono
ad alta voce. I test che usano un COM finto lo installano in sys.modules dopo questo fixture (ordine LIFO di
monkeypatch: il loro setitem resta attivo)."""
from __future__ import annotations

import os
import subprocess
import sys
import types

import pytest


@pytest.fixture(autouse=True)
def postazione_sintetica(monkeypatch):
    from collector import postazione
    monkeypatch.setattr(postazione, "rileva", lambda: {"nome_macchina": "PC-ESEMPIO", "tipo": "VDI",
                        "sistema_operativo": "Windows 11 (ESEMPIO)", "processore": "CPU di esempio", "ram_gb": 8})

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Nomi eseguibili vietati (Windows e generici): Outlook e suite Office, plus utilità di sistema sensibili
_VIETATI_EXE = {
    "outlook.exe", "outlook", "winword.exe", "excel.exe", "powerpnt.exe", "onenote.exe",
    "msaccess.exe", "lync.exe", "teams.exe", "wevtutil.exe", "wevtutil",
}


class _BloccoCOM(RuntimeError):
    """I test non possono usare il COM reale."""


def _blocca(*a, **k):
    raise _BloccoCOM(
        "test: chiamata COM/Office bloccata (win32com/pythoncom). Usa un finto Dispatch nel test. "
        "Un test aveva avviato Outlook vero."
    )


def _installa_blocco_com():
    """Moduli stub che falliscono su Dispatch/GetActiveObject; import win32com non dà AttributeError silenzioso."""
    for nome in ("pythoncom", "win32com", "win32com.client"):
        if nome in sys.modules and getattr(sys.modules[nome], "_rsw_blocco_com", False):
            continue
    pc = types.ModuleType("pythoncom")
    pc.CoInitialize = lambda: None
    pc.CoUninitialize = lambda: None
    pc._rsw_blocco_com = True
    w = types.ModuleType("win32com")
    w._rsw_blocco_com = True
    cl = types.ModuleType("win32com.client")
    cl.Dispatch = _blocca
    cl.DispatchEx = _blocca
    cl.GetActiveObject = _blocca
    cl.gencache = types.SimpleNamespace(EnsureDispatch=_blocca)
    cl._rsw_blocco_com = True
    w.client = cl
    sys.modules["pythoncom"] = pc
    sys.modules["win32com"] = w
    sys.modules["win32com.client"] = cl


def _nome_exe(arg) -> str:
    s = str(arg).strip().strip('"').replace("\\", "/").split("/")[-1].lower()
    return s


def _args_vietati(args) -> str | None:
    if not args:
        return None
    seq = list(args) if not isinstance(args, (str, bytes)) else [args]
    if seq and isinstance(seq[0], (list, tuple)):
        seq = list(seq[0]) + seq[1:]
    for a in seq:
        n = _nome_exe(a)
        if n in _VIETATI_EXE or n.endswith(".exe") and n[:-4] in _VIETATI_EXE:
            return n
        low = str(a).lower()
        if "outlook.application" in low or "outlook.exe" in low:
            return "outlook"
    return None


MAPPA_PROVA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dati", "applicazioni_prova.json")


@pytest.fixture(autouse=True)
def _mappa_di_prova(monkeypatch):
    """La mappatura predefinita del programma ha l'elenco dei siti VUOTO (configurazione locale dell'Ente): i test
    usano una mappatura di prova con un sito inventato (gestionale.esempio.test) e un dominio escluso."""
    from aggregatore import mappa
    monkeypatch.setattr(mappa, "PERCORSO_PREDEFINITO", MAPPA_PROVA)


@pytest.fixture(autouse=True)
def _rsw_blocca_com_e_office(monkeypatch):
    """Blocca COM reale e lanci di Outlook/Office/wevtutil per tutta la durata di ogni test."""
    _installa_blocco_com()

    reale_run = subprocess.run
    reale_popen = subprocess.Popen
    reale_call = subprocess.call
    reale_check = getattr(subprocess, "check_call", None)
    reale_check_out = getattr(subprocess, "check_output", None)

    def _guard_run(*a, **k):
        v = _args_vietati(a[0] if a else None)
        if v:
            raise _BloccoCOM(f"test: esecuzione di {v!r} bloccata")
        return reale_run(*a, **k)

    def _guard_popen(*a, **k):
        v = _args_vietati(a[0] if a else None)
        if v:
            raise _BloccoCOM(f"test: Popen di {v!r} bloccato")
        return reale_popen(*a, **k)

    monkeypatch.setattr(subprocess, "run", _guard_run)
    monkeypatch.setattr(subprocess, "Popen", _guard_popen)
    monkeypatch.setattr(subprocess, "call", lambda *a, **k: _guard_run(*a, **k).returncode)
    if reale_check:
        monkeypatch.setattr(subprocess, "check_call", lambda *a, **k: _guard_run(*a, **k))
    if reale_check_out:
        def _co(*a, **k):
            r = _guard_run(*a, capture_output=True, **k)
            if r.returncode:
                raise subprocess.CalledProcessError(r.returncode, a[0] if a else None, r.stdout, r.stderr)
            return r.stdout
        monkeypatch.setattr(subprocess, "check_output", _co)

    # Re-installa dopo eventuali setitem dei test sul COM finto? No: i test di posta impostano il finto
    # DOPO l'autouse (stack LIFO di monkeypatch: teardown del test ripristina il nostro blocco).
    # Ma setitem del test sostituisce i moduli: ok. All'inizio di ogni test rimettiamo il blocco.
    yield
    _installa_blocco_com()
