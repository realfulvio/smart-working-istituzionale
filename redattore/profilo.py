"""Scelta del profilo AI e del modello al momento di «Genera resoconto».

  AI-STANDARD – Qwen3-4B Q4_K_M (PC con ≥ 14 GB rilevati, cioè 16 GB nominali), profilo del JSON giornaliero
                (`postazione.profilo_ai`, che il CED può forzare);
  AI-LIGHT    – Qwen3-1.7B Q4_K_M (PC da 8–12 GB).
Prima di caricare il modello si controlla la memoria libera: se non basta per il 4B si ripiega sull'1.7B, se non basta
nemmeno per quello si usa il testo standard (nessun modello). Stessi fatti, stesso controllo, stesso schema.
"""
from __future__ import annotations

import os
import sys

MODELLI = {"AI-STANDARD": "Qwen3-4B-Q4_K_M.gguf", "AI-LIGHT": "Qwen3-1.7B-Q4_K_M.gguf"}
# memoria libera necessaria (GB): picco misurato del motore (4B: 2,8 GB; 1.7B: 1,45 GB) + margine per il sistema
MEMORIA_LIBERA_GB = {"AI-STANDARD": 4.0, "AI-LIGHT": 2.2}
SOGLIA_RAM_STANDARD_GB = 14


def memoria_gb() -> tuple[float | None, float | None]:
    """(totale, disponibile) in GB; (None, None) se non rilevabile."""
    try:
        if sys.platform.startswith("linux"):
            v = {}
            with open("/proc/meminfo") as f:
                for r in f:
                    k, x = r.split(":", 1)
                    v[k] = int(x.split()[0]) / 2**20
            return round(v["MemTotal"], 1), round(v.get("MemAvailable", v.get("MemFree", 0)), 1)
        if sys.platform == "win32":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS(); m.dwLength = ctypes.sizeof(MS)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
                return round(m.ullTotalPhys / 2**30, 1), round(m.ullAvailPhys / 2**30, 1)
    except Exception:   # noqa: BLE001
        pass
    return None, None


def profilo_richiesto(doc: dict, totale_gb: float | None) -> tuple[str, str]:
    """Profilo dal JSON (rilevato dal collector o forzato dal CED); altrimenti dalla RAM di questo PC."""
    p = ((doc.get("postazione") or {}).get("profilo_ai") or {})
    if p.get("profilo") in MODELLI:
        return p["profilo"], p.get("criterio") or "json"
    if totale_gb is None:
        return "AI-LIGHT", "ram_non_rilevata"
    return ("AI-STANDARD" if totale_gb >= SOGLIA_RAM_STANDARD_GB else "AI-LIGHT"), "ram_rilevata"


def scegli(doc: dict, cartella_modelli: str, memoria: tuple[float | None, float | None] | None = None,
           forza: str | None = None) -> dict:
    """{"profilo_richiesto", "profilo", "modello" (percorso o None = testo standard), "motivo"}."""
    totale, libera = memoria if memoria is not None else memoria_gb()
    richiesto, criterio = (forza, "forzato") if forza in MODELLI else profilo_richiesto(doc, totale)
    ordine = ["AI-STANDARD", "AI-LIGHT"] if richiesto == "AI-STANDARD" else ["AI-LIGHT"]
    motivi = []
    for p in ordine:
        f = os.path.join(cartella_modelli, MODELLI[p])
        if not os.path.exists(f):
            motivi.append(f"{p}: modello non installato"); continue
        if libera is not None and libera < MEMORIA_LIBERA_GB[p]:
            motivi.append(f"{p}: memoria libera {libera} GB < {MEMORIA_LIBERA_GB[p]} GB"); continue
        return {"profilo_richiesto": richiesto, "criterio": criterio, "profilo": p, "modello": f,
                "motivo": "; ".join(motivi) or "profilo richiesto", "memoria_gb": {"totale": totale, "libera": libera}}
    return {"profilo_richiesto": richiesto, "criterio": criterio, "profilo": None, "modello": None,
            "motivo": "; ".join(motivi) + " → testo standard", "memoria_gb": {"totale": totale, "libera": libera}}
