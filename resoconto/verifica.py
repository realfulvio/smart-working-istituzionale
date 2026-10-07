"""Verifica di un resoconto (PDF con il JSON allegato, oppure il solo JSON).

Esiti (come aggregatore.sigillo.verify, più il controllo del testo del PDF):
  VALIDO         sigilli integri e chiave della postazione presente nel registro dei Sistemi Informativi;
  INTEGRO        sigilli integri, chiave non registrata (o registro non indicato);
  ALTERATO       un sigillo non corrisponde ai dati, oppure il testo del PDF non corrisponde ai dati allegati;
  NON SIGILLATO  manca il sigillo finale (es. PDF di prova) o manca il JSON allegato.
Il testo del PDF si controlla rigenerando l'impaginazione dal JSON allegato (deterministica) e confrontando il testo
pagina per pagina: una modifica al testo visibile (es. un orario cambiato con un editor PDF) risulta ALTERATO.
"""
from __future__ import annotations

import hashlib
import io
import json
import re

from aggregatore import sigillo

from . import VERSIONE_APP
from .pdf import NOME_ALLEGATO, pdf_bytes


def _testo_pagine(dati: bytes) -> list[str]:
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(dati))
    return [re.sub(r"\s+", " ", p.extract_text() or "").strip() for p in r.pages]


_SALTA = {"/Parent", "/P", "/Length", "/Filter", "/DecodeParms", "/Prev"}
# ReportLab dà alle immagini passate come percorso (il logo) il nome «/FormXob.<hash del PERCORSO del file>»: cambia con la
# cartella di installazione (e con il nome utente) senza che cambi il PDF. Nei confronti si usa il nome senza hash.
_RE_XOB = re.compile(r"/FormXob\.[0-9A-Fa-f]+")
_RE_XOB_B = re.compile(rb"/FormXob\.[0-9A-Fa-f]+")
_ATTIVI = ("/OpenAction", "/AA", "/AcroForm", "/JavaScript", "/URI", "/Launch")     # contenuto attivo: mai nei resoconti


def _hash_oggetto(o, h, visti: set) -> None:
    """Impronta strutturale di un oggetto PDF (numeri di oggetto esclusi; stream decodificati)."""
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, StreamObject
    if isinstance(o, IndirectObject):
        if o.idnum in visti:
            h.update(b"<ref>")
            return
        visti.add(o.idnum)
        o = o.get_object()
    if isinstance(o, DictionaryObject):
        h.update(b"{")
        for nome, k in sorted((_RE_XOB.sub("/FormXob", str(k)), k) for k in o):
            if k in _SALTA:
                continue
            h.update(nome.encode()); h.update(b"=")
            _hash_oggetto(o[k], h, visti)
        h.update(b"}")
        if isinstance(o, StreamObject):
            h.update(hashlib.sha256(_RE_XOB_B.sub(b"/FormXob", o.get_data())).digest())
    elif isinstance(o, ArrayObject):
        h.update(b"[")
        for x in o:
            _hash_oggetto(x, h, visti)
        h.update(b"]")
    else:
        h.update(repr(o).encode("utf-8", "replace"))


def _impronte_grafiche(dati: bytes) -> tuple[list[str], list[str]]:
    """([impronta del contenuto grafico di ogni pagina], [contenuti attivi trovati]).
    Il testo estratto non basta: un rettangolo bianco sopra un dato, un'annotazione, un'immagine o un font diversi
    non cambiano il testo ma cambiano ciò che si vede."""
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(dati))
    out = []
    for p in r.pages:
        h = hashlib.sha256()
        for k in ("/MediaBox", "/CropBox", "/Rotate", "/Resources", "/Annots", "/Contents"):
            h.update(k.encode())
            if k in p:
                _hash_oggetto(p[k], h, set())
        out.append(h.hexdigest())
    radice = r.trailer["/Root"]
    attivi = [k for k in _ATTIVI if k in radice]
    return out, attivi


def _manomissioni_indipendenti_dalla_versione(dati: bytes) -> list[str]:
    """Segni di manomissione controllabili senza rigenerare il PDF (quindi anche se la versione dell'impaginatore
    dichiarata nei metadati è diversa): contenuto attivo e annotazioni, che un resoconto non contiene mai."""
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(dati))
    trovati = [k for k in _ATTIVI if k in r.trailer["/Root"]]
    con_annotazioni = [i + 1 for i, p in enumerate(r.pages) if "/Annots" in p]
    if con_annotazioni:
        trovati.append("/Annots (pagine " + ", ".join(map(str, con_annotazioni)) + ")")
    return trovati


def leggi_pdf(path: str) -> tuple[dict | None, bytes, dict]:
    from pypdf import PdfReader
    with open(path, "rb") as f:
        dati = f.read()
    r = PdfReader(io.BytesIO(dati))
    doc = None
    att = r.attachments or {}
    if NOME_ALLEGATO in att:
        doc = sigillo.loads_stretto(att[NOME_ALLEGATO][0].decode("utf-8"))
    meta = {k: str(v) for k, v in (r.metadata or {}).items()}
    return doc, dati, meta


def _declassa_se_valido(out: dict) -> None:
    """VALIDO richiede anche il confronto grafico: se non è stato possibile non si può escludere contenuto sovrapposto
    (un rettangolo bianco su un dato non cambia il testo estratto), quindi l'esito massimo è INTEGRO."""
    if out["esito"] == "VALIDO":
        out["esito"] = "INTEGRO"
        out["motivi"].append("aspetto grafico del PDF non verificato: non si può escludere contenuto sovrapposto ai dati")


def verifica_file(path: str, chiavi_dirs: list[str] | None = None) -> dict:
    chiavi_dirs = chiavi_dirs or []
    out = {"file": path, "tipo": "pdf" if path.lower().endswith(".pdf") else "json", "esito": "ALTERATO",
           "motivi": [], "giorno": None, "dipendente": None, "codice": None, "testo_pdf": None, "grafica_pdf": None}
    try:
        if out["tipo"] == "pdf":
            doc, dati, meta = leggi_pdf(path)
            if doc is None:
                out.update(esito="NON SIGILLATO", motivi=["il PDF non contiene il file dati «resoconto.json»"])
                return out
        else:
            doc = sigillo.load_stretto(path)
            dati, meta = None, {}
    except sigillo.JsonAmbiguo as e:
        out["motivi"].append(f"il file dati contiene chiavi duplicate ({e}): ambiguo, non va accettato")
        return out
    except Exception as e:   # noqa: BLE001
        out["motivi"].append(f"file non leggibile ({type(e).__name__})")
        return out
    if not isinstance(doc, dict):
        out["motivi"].append("il file dati non è un oggetto JSON")
        return out
    out["giorno"] = doc.get("giorno")
    out["dipendente"] = (doc.get("dipendente") or {}).get("nome") or (doc.get("dipendente") or {}).get("account")
    sf = (doc.get("integrita") or {}).get("sigillo_finale") or {}
    out["codice"] = sf.get("codice")
    try:
        r = sigillo.verify(doc, chiavi_dirs)
    except Exception as e:   # noqa: BLE001
        out["motivi"].append(f"dati non verificabili ({type(e).__name__})")
        return out
    out["esito"] = r["esito"]
    out["motivi"] = list(r.get("motivi", []))
    if out["esito"] in ("VALIDO", "INTEGRO") and not (r.get("finale") or {}).get("presente"):
        out["esito"] = "NON SIGILLATO"
        out["motivi"].insert(0, "manca il sigillo finale: la giornata non è stata confermata dal dipendente")
    out["sigilli"] = {k: {"presente": r[k].get("presente"), "valido": r[k].get("valido"), "codice": r[k].get("codice")}
                      for k in ("tecnico", "finale") if isinstance(r.get(k), dict)}
    if dati is not None and out["esito"] in ("VALIDO", "INTEGRO", "NON SIGILLATO"):
        filigrana = (meta.get("/RendicontoSWFiligrana") or "DATI DI ESEMPIO") if "filigrana" in meta.get("/RendicontoSW", "") \
            else None
        parti = (meta.get("/RendicontoSW") or "").split("|")
        if parti[0] in ("4.0.0", "4.1.0") and meta.get("/Subject") != "Smart Working Istituzionale – Ente":
            out["testo_pdf"] = "non confrontabile (identità storica personalizzata)"
            out["grafica_pdf"] = "non confrontata (configurazione storica non disponibile)"
            out["motivi"].append("sigilli verificati; serve la configurazione dell'Ente dell'epoca per confrontare il PDF storico")
            segni = _manomissioni_indipendenti_dalla_versione(dati)
            if segni:
                out["esito"] = "ALTERATO"
                out["motivi"].append("contenuto attivo o annotazioni non previsti nel PDF storico")
            _declassa_se_valido(out)
            return out
        impagina = pdf_bytes
        from .edizione import identita
        archivio=identita().get("renderer_storici",{}).get(parti[0])
        try:
            if archivio:
                from .storico import carica_renderer
                impagina=carica_renderer(archivio).pdf_bytes
            elif parti[0] == "4.1.0":
                from .storico.pdf_410 import pdf_bytes as impagina
            elif parti[0] == "4.0.0":
                from .storico.pdf_400 import pdf_bytes as impagina
        except Exception as e:  # Archivio esterno incompleto: mai VALIDO senza confronto.
            out["testo_pdf"] = "non confrontabile (renderer storico non disponibile)"
            out["grafica_pdf"] = "non confrontata"
            _declassa_se_valido(out)
            out["motivi"].append(f"renderer storico non disponibile ({type(e).__name__})")
            if _manomissioni_indipendenti_dalla_versione(dati):
                out["esito"] = "ALTERATO"
                out["motivi"].append("contenuto attivo o annotazioni non previsti nel PDF")
            return out
        try:
            atteso = _testo_pagine(impagina(doc, filigrana))
            trovato = _testo_pagine(dati)
        except Exception as e:   # noqa: BLE001
            out["testo_pdf"] = "non confrontabile"
            _declassa_se_valido(out)
            out["motivi"].append(f"testo del PDF non confrontabile ({type(e).__name__})")
            return out
        try:
            import reportlab
            stessa_versione = parti[0] == VERSIONE_APP and f"rl{reportlab.Version}" in parti[2:]
            if stessa_versione:
                gt, attivi = _impronte_grafiche(dati)
                ga, _ = _impronte_grafiche(impagina(doc, filigrana))
                diverse_g = [i + 1 for i in range(max(len(ga), len(gt))) if i >= len(ga) or i >= len(gt) or ga[i] != gt[i]]
                if diverse_g or attivi:
                    out["grafica_pdf"] = "diversa dai dati"
                    out["esito"] = "ALTERATO"
                    if diverse_g:
                        out["motivi"].append("l'aspetto grafico del PDF non corrisponde ai dati sigillati ("
                                             + ("pagina " if len(diverse_g) == 1 else "pagine ") + ", ".join(map(str, diverse_g))
                                             + "): contenuto aggiunto, coperto o sostituito")
                    if attivi:
                        out["motivi"].append("il PDF contiene contenuto attivo non previsto (" + ", ".join(attivi) + ")")
                else:
                    out["grafica_pdf"] = "corrisponde ai dati"
            else:
                # La versione sta nei metadati del PDF, che chi lo modifica controlla: dichiararne una diversa non deve
                # bastare a saltare il controllo. Senza il confronto grafico restano solo i segni di manomissione
                # indipendenti dalla versione e l'esito non può essere VALIDO.
                out["grafica_pdf"] = "non confrontata (PDF creato con un'altra versione dell'impaginatore)"
                segni = _manomissioni_indipendenti_dalla_versione(dati)
                if segni:
                    out["esito"] = "ALTERATO"
                    out["motivi"].append("il PDF contiene elementi non previsti (" + ", ".join(segni) + ")")
                _declassa_se_valido(out)
        except Exception as e:   # noqa: BLE001
            out["grafica_pdf"] = "non confrontabile"
            out["motivi"].append(f"aspetto grafico del PDF non confrontabile ({type(e).__name__})")
            _declassa_se_valido(out)
        if atteso == trovato:
            out["testo_pdf"] = "corrisponde ai dati"
        else:
            diverse = [i + 1 for i in range(max(len(atteso), len(trovato)))
                       if i >= len(atteso) or i >= len(trovato) or atteso[i] != trovato[i]]
            out["testo_pdf"] = "diverso dai dati"
            out["esito"] = "ALTERATO"
            out["motivi"].append("il testo del PDF non corrisponde ai dati sigillati ("
                                 + ("pagina " if len(diverse) == 1 else "pagine ") + ", ".join(map(str, diverse)) + ")")
        if filigrana:
            out["motivi"].append(f"PDF con filigrana «{filigrana}» (prova o dati di esempio)")
    return out
