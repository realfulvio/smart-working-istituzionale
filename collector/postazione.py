"""Snapshot tecnico autorizzato dall'utente: niente identificativi di rete o inventario esteso."""
import os
import platform
import sys

CAMPI = ("nome_macchina", "tipo", "sistema_operativo", "processore", "ram_gb")


def rileva() -> dict:
    from redattore.profilo import memoria_gb
    cpu = platform.processor() or "Non disponibile"
    tipo = "PC fisso"
    sistema = platform.system() + " " + platform.release() + " (" + platform.version() + ")"
    if sys.platform == "win32":
        import winreg
        from .win import tipo_postazione
        tipo = "VDI" if tipo_postazione() == "vdi" else "PC fisso"
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                cpu = winreg.QueryValueEx(k, "ProcessorNameString")[0]
        except OSError:
            pass
        v = sys.getwindowsversion()
        sistema = f"Windows {platform.release()} — {v.major}.{v.minor}, build {v.build}"
    return {"nome_macchina": (os.environ.get("COMPUTERNAME") or platform.node() or "Non disponibile")[:120],
            "tipo": tipo, "sistema_operativo": sistema[:160], "processore": str(cpu).strip()[:160],
            "ram_gb": memoria_gb()[0]}


def minimizza(dati: dict) -> dict:
    """Whitelist separata dai vecchi metadati: campi aggiunti fuori elenco mai propagati."""
    return {k: dati[k] for k in CAMPI if k in dati}
