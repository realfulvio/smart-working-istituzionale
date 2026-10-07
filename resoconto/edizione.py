"""Overlay locale scelto dal CED; la configurazione condivisa è neutra."""
import json
import os
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]

def cartella():
    scelta = os.environ.get("RENDICONTO_EDIZIONE")
    if scelta is None:
        try:
            scelta = json.loads((RADICE / "config/edizione.json").read_text(encoding="utf-8-sig")).get("overlay")
        except (OSError, ValueError):
            scelta = None
    if not scelta or scelta == "neutra":
        return None
    p = Path(scelta)
    return p.resolve() if p.is_absolute() else (RADICE / "edizioni" / p).resolve()

def percorso(nome):
    overlay = cartella()
    if overlay and (overlay / nome).is_file():
        return overlay / nome
    return RADICE / "config" / nome

def identita():
    try:
        return json.loads(percorso("identita.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {"id": "neutra", "etichetta": "Edizione neutra"}
