"""Identità dell'Ente (nome, logo, colori, assistenza) letta da config/ente.json.

Valori predefiniti neutri: «Ente», nessun logo, palette sobria. Un file assente o non valido equivale ai predefiniti
(il programma non si ferma mai per un problema di personalizzazione grafica).
"""
from __future__ import annotations

import json
import os
import re
from .tokens import carica as token_ente
from .edizione import percorso

_TOKEN = token_ente()

PERCORSO_PREDEFINITO = str(percorso("ente.json"))
PREDEFINITI = {
    "nome": "Il tuo Ente", "sottotitolo": "", "assistenza": "", "logo": "",
    "dati_tecnici_postazione": True,
    "versione_informativa": "2026-10-07",
    "colori": {"primario": _TOKEN["primary"].lower(), "primario_scuro": _TOKEN["primary-700"].lower(),
               "scuro": _TOKEN["dark"].lower(), "tenue": _TOKEN["primary-tint-1"].lower(),
               "accento": _TOKEN["stemma-gold"].lower()},
}
_RE_COLORE = re.compile(r"^#[0-9a-fA-F]{6}$")
_cache: dict | None = None


def carica(percorso: str | None = None) -> dict:
    """→ dizionario con nome, sottotitolo, assistenza, logo (percorso assoluto o ""), colori."""
    global _cache
    if percorso is None and _cache is not None:
        return _cache
    p = percorso or PERCORSO_PREDEFINITO
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in PREDEFINITI.items()}
    try:
        with open(p, encoding="utf-8") as f:
            j = json.load(f)
        if isinstance(j, dict):
            if isinstance(j.get("dati_tecnici_postazione"), bool):
                out["dati_tecnici_postazione"] = j["dati_tecnici_postazione"]
            for k in ("nome", "sottotitolo", "assistenza", "versione_informativa"):
                if isinstance(j.get(k), str):
                    out[k] = j[k].strip()[:120]
            if not out["nome"]:
                out["nome"] = PREDEFINITI["nome"]
            if isinstance(j.get("logo"), str) and j["logo"].strip():
                lg = os.path.join(os.path.dirname(os.path.abspath(p)), os.path.expandvars(j["logo"].strip()))
                if os.path.isfile(lg):
                    out["logo"] = os.path.abspath(lg)
            if isinstance(j.get("colori"), dict):
                for k, v in j["colori"].items():
                    if k in out["colori"] and isinstance(v, str) and _RE_COLORE.match(v):
                        out["colori"][k] = v.lower()
    except (OSError, ValueError):
        pass
    if percorso is None:
        _cache = out
    return out
