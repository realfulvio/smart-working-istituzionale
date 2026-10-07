"""Processo di raccolta (lanciato da «Avvia giornata» / «Riprendi»): finestra nascosta + timer ogni 5 secondi.

Si ferma da solo quando trova il comando «pausa» o «chiudi» (file stato/comando.json scritto dall'interfaccia o dalla
riga di comando), oppure alla chiusura della sessione di Windows."""
from __future__ import annotations

import datetime as dt
import json
import os
import time

from . import __version__
from .campionatore import Campionatore
from .registro import Registro
from .stato import FUSO, Stato

INTERVALLO_S = 5
DIAG_OGNI_S = 60


def eseguibili_ammessi() -> frozenset:
    """Eseguibili dell'elenco del CED (config/applicazioni.json); mappatura illeggibile -> nessuno (bonifica B5)."""
    try:
        from aggregatore.mappa import Mappa
        return frozenset(Mappa.predefinita().per_exe)
    except Exception:
        return frozenset()


def esegui(p, intervallo_s: int = INTERVALLO_S):
    from . import win
    tz = FUSO()
    now = lambda: dt.datetime.now(tz)
    st = Stato(p)
    reg = Registro(p)
    camp = Campionatore(reg.scrivi, eseguibili_ammessi())
    smb = None  # PoC rete separato; nessun sensore SMB nell'edizione operativa
    avvio = now()
    t0_wall, t0_cpu = time.monotonic(), win.consumo_processo()["cpu_s"]
    offset = [time.time() - time.monotonic()]
    ultimo_diag = [0.0]
    fin = None

    def diag(forza=False):
        m = time.monotonic()
        if not forza and m - ultimo_diag[0] < DIAG_OGNI_S:
            return
        ultimo_diag[0] = m
        c = win.consumo_processo()
        rec = {"ts": now().replace(microsecond=0).isoformat(), "secondi": round(m - t0_wall, 1),
               "cpu_s": round(c["cpu_s"] - t0_cpu, 3), "ws_mb": c["ws_mb"], "picco_ws_mb": c["picco_ws_mb"],
               "privata_mb": c["privata_mb"], "eventi": dict(camp.conteggi)}
        with open(os.path.join(p.diagnostica, f"{avvio.date().isoformat()}.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")

    def fine(motivo: str, ts=None):
        camp.chiudi_fascia()
        t = ts or now()
        if motivo == "pausa":
            reg.scrivi("raccolta", t, evento="pausa")
        elif motivo == "chiudi":
            reg.scrivi("sessione", t, evento="fine_raccolta")
        elif motivo == "spegnimento":
            reg.scrivi("sessione", t, evento="spegnimento")
        diag(forza=True)
        st.demone_terminato(motivo)
        if fin is not None:
            fin.chiudi()

    def on_timer():
        cmd = st.leggi_comando()
        if cmd:
            st.cancella_comando()
            fine(cmd["comando"], dt.datetime.fromisoformat(cmd["ts"]))
            return
        camp.rete(None)
        camp.tick(now(), win.ultimo_input(), win.exe_primo_piano)
        diag()

    def on_timechange():
        nuovo = time.time() - time.monotonic()
        delta = round(nuovo - offset[0])
        offset[0] = nuovo
        camp.orologio(now(), delta)

    def on_fine(motivo: str):
        if motivo == "spegnimento":
            fine("spegnimento")
        else:
            st.log(f"errore nel ciclo: {motivo}")

    fin = win.Finestra(on_timer, lambda c: camp.wts(now(), c), lambda c: camp.power(now(), c), on_timechange,
                       on_fine, intervallo_s * 1000)
    st.demone_avviato(os.getpid(), {"wts": fin.wts_ok, "smb": False, "versione": __version__})
    camp.tick(now(), win.ultimo_input(), win.exe_primo_piano)       # riferimento iniziale dell'input
    camp.rete(None)
    diag(forza=True)
    fin.ciclo()
