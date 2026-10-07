"""Token istituzionali condivisi da UI, PDF e mockup; nessun download a runtime."""
import json
from pathlib import Path

from .edizione import percorso
PERCORSO = percorso("design_tokens.json")


def carica():
    with PERCORSO.open(encoding="utf-8-sig") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def contrasto(primo, secondo):
    def luminanza(hex):
        rgb = [int(hex[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        rgb = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb]
        return sum(c * w for c, w in zip(rgb, (.2126, .7152, .0722)))
    a, b = sorted((luminanza(primo), luminanza(secondo)))
    return (b + .05) / (a + .05)


def palette():
    t = carica()
    return {"primary": t["primary"], "primary_h": t["primary-700"], "dark": t["dark"],
            "tint": t["primary-tint-1"], "tint2": t["primary-tint-2"], "gold": t["stemma-gold"],
            "text": t["text"], "muted": t["text-muted"], "line": t["border"], "bordo": t["border"],
            "bg": t["surface-alt"], "white": t["surface"], "ok": t["success"], "err": t["danger"],
            "warn": t["warning"], "warn_txt": t["warning"], "decl": t["stemma-gold"],
            "decl_bg": t["surface-alt"], "decl_txt": t["primary-900"],
            "ai": t["primary-900"], "ai_bg": t["primary-tint-1"],
            "ok_bg": t["surface-alt"], "warn_bg": t["surface-alt"], "err_bg": t["surface-alt"],
            "velo": t["text-muted"], "decl_bd": t["border"], "azure": t["primary-action"],
            "bar_bg": t["surface-alt"], "s_nes": t["primary-tint-2"]}


def verifica_contrasti():
    t = carica()
    coppie = [("surface", "primary"), ("surface", "primary-action"), ("surface", "primary-900"),
              ("surface", "dark"), ("text", "surface"), ("text-muted", "surface"),
              ("text-muted", "surface-alt"), ("success", "surface"), ("warning", "surface"),
              ("danger", "surface"), ("text", "stemma-gold"), ("primary-900", "stemma-gold"),
              ("primary-action", "surface-alt")]
    return [{"primo": a, "secondo": b, "rapporto": round(contrasto(t[a], t[b]), 2),
             "minimo_testo": 4.5, "valido": contrasto(t[a], t[b]) >= 4.5} for a, b in coppie]
