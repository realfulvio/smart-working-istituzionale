"""Stato della giornata e comandi tra interfaccia/riga di comando e processo di raccolta (file in stato/)."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

NOME_FUSO = "Europe/Rome"


def FUSO():
    from zoneinfo import ZoneInfo
    return ZoneInfo(NOME_FUSO)


def intervalli_attivi(g: dict, adesso: dt.datetime) -> list[tuple[dt.datetime, dt.datetime]]:
    """Periodi di raccolta attiva della giornata: da ogni avvio/ripresa alla pausa o chiusura successiva
    (l'ultimo, se la giornata è in corso, arriva ad adesso).

    Sta nel collector (non in estensione.host) perché serve anche alla chiusura «a consuntivo» senza estensione:
    nell'ALFA3 l'import da estensione.host faceva fallire «Chiudi giornata» nell'eseguibile (collaudo ALFA3 N1)."""
    out, fasi = [], g.get("fasi") or []
    for i, f in enumerate(fasi):
        if "avvio" not in f:
            continue
        a = dt.datetime.fromisoformat(f["avvio"])
        fine = f.get("pausa") or f.get("chiusura")
        if fine:
            b = dt.datetime.fromisoformat(fine)
        elif i == len(fasi) - 1 and g.get("fase") == "in_corso":
            b = adesso
        else:
            continue
        if b > a:
            out.append((a, b))
    return out


def _scrivi_json(path: str, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _leggi_json(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def processo_attivo(pid: int) -> bool:
    if not pid:
        return False
    if sys.platform == "win32":
        import ctypes
        k = ctypes.WinDLL("kernel32")
        k.OpenProcess.restype = ctypes.c_void_p
        h = k.OpenProcess(0x1000, False, int(pid))
        if not h:
            return False
        code = ctypes.c_ulong(0)
        k.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code))
        k.CloseHandle(ctypes.c_void_p(h))
        return code.value == 259                      # STILL_ACTIVE
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


class Stato:
    def __init__(self, p):
        self.p = p
        self.f_giornata = os.path.join(p.stato, "giornata.json")
        self.f_demone = os.path.join(p.stato, "demone.json")
        self.f_comando = os.path.join(p.stato, "comando.json")
        self.f_presa = os.path.join(p.stato, "presa_visione.json")
        self.f_dipendente = os.path.join(p.stato, "dipendente.json")
        self.f_log = os.path.join(p.diagnostica, "collector.log")

    # giornata ------------------------------------------------------------------------------------
    def giornata(self) -> dict:
        return _leggi_json(self.f_giornata) or {}

    def salva_giornata(self, g: dict):
        _scrivi_json(self.f_giornata, g)

    # processo di raccolta ------------------------------------------------------------------------
    def demone(self) -> dict:
        return _leggi_json(self.f_demone) or {}

    def demone_attivo(self) -> bool:
        d = self.demone()
        return bool(d.get("in_esecuzione")) and processo_attivo(d.get("pid", 0))

    def demone_avviato(self, pid: int, info: dict):
        _scrivi_json(self.f_demone, {"in_esecuzione": True, "pid": pid, **info,
                                     "avviato": dt.datetime.now(FUSO()).replace(microsecond=0).isoformat()})

    def demone_terminato(self, motivo: str):
        d = self.demone()
        d.update({"in_esecuzione": False, "motivo": motivo,
                  "terminato": dt.datetime.now(FUSO()).replace(microsecond=0).isoformat()})
        _scrivi_json(self.f_demone, d)

    # comandi -------------------------------------------------------------------------------------
    def invia_comando(self, comando: str, ts: dt.datetime):
        _scrivi_json(self.f_comando, {"comando": comando, "ts": ts.replace(microsecond=0).isoformat()})

    def leggi_comando(self):
        c = _leggi_json(self.f_comando)
        return c if isinstance(c, dict) and c.get("comando") in ("pausa", "chiudi") else None

    def cancella_comando(self):
        try:
            os.remove(self.f_comando)
        except OSError:
            pass

    # presa visione dell'informativa ----------------------------------------------------------------
    def presa_visione(self):
        return _leggi_json(self.f_presa)

    def registra_presa_visione(self, versione: str, ts: dt.datetime):
        _scrivi_json(self.f_presa, {"versione": versione, "data": ts.replace(microsecond=0).isoformat()})

    # nome e ufficio indicati dal dipendente al primo avvio (M7) --------------------------------------------------
    def dipendente(self) -> dict:
        return _leggi_json(self.f_dipendente) or {}

    def salva_dipendente(self, nome: str, ufficio: str):
        _scrivi_json(self.f_dipendente, {"nome": " ".join(nome.split())[:80], "ufficio": " ".join(ufficio.split())[:80]})

    def log(self, testo: str):
        with open(self.f_log, "a", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now(FUSO()).replace(microsecond=0).isoformat()} {testo}\n")
