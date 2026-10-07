"""Impaginatori congelati delle versioni precedenti, usati solo dal verificatore (ADR-T6)."""


def carica_renderer(nome):
    """Archivio locale del CED: nomi modulo validati, nessun download."""
    import importlib
    import re
    from resoconto import edizione
    if not re.fullmatch(r"pdf_[0-9]+",nome):raise ValueError("Nome renderer storico non valido")
    root=edizione.cartella()
    path=(root / "storico") if root else edizione.RADICE / "config/storico"
    if str(path) not in __path__:__path__.append(str(path))
    return importlib.import_module("."+nome,__name__)
