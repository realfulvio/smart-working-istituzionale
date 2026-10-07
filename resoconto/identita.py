"""Identità pubblicabile del documento, sigillata; mai fatti per l'AI."""
import hashlib
from pathlib import Path
from . import ente
from .tokens import carica

def snapshot():
    e = ente.carica()
    return {"nome": e["nome"], "sottotitolo": e["sottotitolo"], "token": carica(),
            "logo_sha256": hashlib.sha256(Path(e["logo"]).read_bytes()).hexdigest() if e["logo"] else None}
