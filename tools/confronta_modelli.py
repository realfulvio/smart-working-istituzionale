"""Confronto di modelli GGUF per la «Sintesi della giornata», solo su giornate SINTETICHE (tools/m5_giornate_sintetiche.py).

Per ogni giornata e ogni modello esegue la stessa pipeline dell'app (redattore.sintesi.genera con LlamaCpp: stessi fatti,
stesso prompt, stesso controllo anti-invenzione, secondo tentativo, ripiego sul testo standard) e registra: esito, frasi
respinte e motivi del controllo, testo finale, tempi, picco di memoria del motore. Con --ram-job-gb il processo (e il
motore figlio) gira dentro un Job Object di Windows con quel limite di memoria, come nella simulazione 8 GB della 5.0.

  python -m tools.confronta_modelli --server llama-server.exe --modelli A.gguf B.gguf --giornate CARTELLA \
      --uscita risultati.json [--ram-job-gb 8] [--thread 4] [--solo g01,g02]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import tempfile
import time


def limite_job_gb(gb: float | None) -> dict:
    """Mette il processo corrente in un Job Object con JobMemoryLimit = gb (Windows). I figli ne fanno parte."""
    if not gb or sys.platform != "win32":
        return {"limite_job_gb": None}
    import ctypes
    from ctypes import wintypes as w

    class B(ctypes.Structure):
        _fields_ = [("a", ctypes.c_longlong), ("b", ctypes.c_longlong), ("flags", w.DWORD), ("minws", ctypes.c_size_t),
                    ("maxws", ctypes.c_size_t), ("proc", w.DWORD), ("aff", ctypes.c_size_t), ("pri", w.DWORD),
                    ("sched", w.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in "abcdef"]

    class E(ctypes.Structure):
        _fields_ = [("basic", B), ("io", IO), ("process_limit", ctypes.c_size_t), ("job_limit", ctypes.c_size_t),
                    ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.restype = w.HANDLE
    k.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    k.GetCurrentProcess.restype = w.HANDLE
    job = k.CreateJobObjectW(None, None)
    info = E()
    info.basic.flags = 0x200                       # JOB_OBJECT_LIMIT_JOB_MEMORY
    info.job_limit = int(gb * 1024 ** 3)
    ok = bool(k.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
              and k.AssignProcessToJobObject(job, k.GetCurrentProcess()))
    limite_job_gb._job = job                        # resta aperto fino alla fine del processo
    return {"limite_job_gb": gb if ok else None, "job_impostato": ok,
            "errore": None if ok else ctypes.get_last_error()}


def esegui(server: str, modello: str, giornata: str, thread: int, cache: str) -> dict:
    from aggregatore.cli import _load
    from redattore import motore, sintesi
    doc = _load(giornata)
    m = motore.LlamaCpp(server, modello, thread=thread, cache_prefisso=cache)
    t0 = time.monotonic()
    s = sintesi.genera(doc, m, adesso="2026-10-14T12:00:00+02:00", profilo="AI-LIGHT")
    respinte = [{"n": p["n"], "esito": p["esito"], "problemi": p["problemi"],
                 "testo": " ".join(f.get("testo", "") for f in p.get("frasi") or [])}
                for p in s["controllo"]["tentativi"] if p["esito"] != "superato"]
    return {"giornata": os.path.basename(giornata)[:-5], "modello": os.path.basename(modello),
            "esito": s["esito"], "origine": s["origine_testo"], "tentativi": len(s["controllo"]["tentativi"]),
            "respinte": respinte, "problemi_respinti": sum(len(r["problemi"]) for r in respinte),
            "controllo_finale": s["controllo"]["esito"], "testo": s["testo"], "fatti": len(s["fatti"]),
            "secondi_totali": round(time.monotonic() - t0, 2), "prestazioni": s["prestazioni"],
            "runtime": (s.get("motore") or {}).get("runtime")}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="confronta_modelli")
    ap.add_argument("--server", required=True)
    ap.add_argument("--modelli", nargs="+", required=True)
    ap.add_argument("--giornate", required=True)
    ap.add_argument("--uscita", required=True)
    ap.add_argument("--thread", type=int, default=4)
    ap.add_argument("--ram-job-gb", type=float)
    ap.add_argument("--solo")
    ns = ap.parse_args(argv)
    job = limite_job_gb(ns.ram_job_gb)
    file = sorted(glob.glob(os.path.join(ns.giornate, "g*.json")))
    if ns.solo:
        voluti = set(ns.solo.split(","))
        file = [f for f in file if os.path.basename(f).split("_")[0] in voluti]
    out = {"limite": job, "thread": ns.thread, "server": os.path.basename(ns.server), "risultati": []}
    for modello in ns.modelli:
        cache = tempfile.mkdtemp(prefix="cache_ai_")           # cache del prefisso propria di ogni modello
        for f in file:
            r = esegui(ns.server, modello, f, ns.thread, cache)
            out["risultati"].append(r)
            print(f"{r['modello']:28s} {r['giornata']:28s} {r['esito']:15s} tent={r['tentativi']} "
                  f"resp={r['problemi_respinti']} t={r['secondi_totali']}s ram={r['prestazioni'].get('ram_picco_mb')}MB",
                  flush=True)
            with open(ns.uscita, "w", encoding="utf-8") as fh:
                json.dump(out, fh, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
