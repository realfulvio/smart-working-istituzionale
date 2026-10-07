"""Formato degli eventi grezzi normalizzati (ingresso dell'aggregatore) e loro lettura.

Ogni riga di raw.jsonl è un oggetto JSON con il campo obbligatorio ``tipo``. Gli eventi con un istante
hanno ``ts`` in ISO 8601 **con fuso** (es. ``2026-10-02T08:30:12+02:00``). Tipi ammessi:

  meta        (una sola riga, senza ts) metadati della giornata
  sessione    ts, evento ∈ {accesso, blocco, sblocco, disconnessione, riconnessione,
                            sospensione, ripresa, chiusura, spegnimento}
  attivita    ts                     attività generica della postazione (es. input rilevato)
  app         ts, app | exe          uso di un'applicazione: id canonico (word, halley…) oppure nome dell'eseguibile
                                     (WINWORD.EXE) risolto con config/applicazioni.json; l'eseguibile non esce mai
  web         ts, [sito | dominio]   visita a un sito: etichetta della whitelist o solo il dominio (mai l'URL);
                                     un dominio fuori whitelist è scartato (web generico)
  raccolta    ts, evento ∈ {pausa, ripresa}   «Pausa raccolta» premuta dal dipendente
  rete        ts, [operazioni]       numero di operazioni di rete (solo conteggio; 'byte' ignorato)
  posta       NON più rilevata (bonifica B2): righe di vecchi grezzi ignorate con un avviso
  manuale     inizio, fine, categoria ∈ {riunione, telefonata, cartaceo, sopralluogo, formazione, altro},
              [descrizione ≤ 200]    (origine: dichiarata)
  segnalazione [fascia | dalle, alle], campo, nota ≤ 200   «dato apparentemente errato» (origine: dichiarata)
  osservazione testo                 (origine: dichiarata)
  orologio    ts, delta_s            cambio dell'ora di sistema registrato dalla fonte (solo avviso)

Campi vietati in ingresso (scartati con un avviso, mai riportati): oggetto, subject, file, path, percorso,
nome_file, url, mittente, destinatario, corpo, testo_mail. Vedi PRIVACY.md.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Iterable, Optional

from .mappa import solo_host

EVENTI_SESSIONE = ("accesso", "blocco", "sblocco", "disconnessione", "riconnessione",
                   "sospensione", "ripresa", "chiusura", "spegnimento", "avvio_raccolta", "fine_raccolta")
CATEGORIE_MANUALI = ("riunione", "telefonata", "cartaceo", "sopralluogo", "formazione", "altro", "videoconferenza", "amministrativa_offline")
# campi che il dipendente può segnalare come apparentemente errati (riferimento, mai modifica)
AVVISO_POSTA = "eventi di posta di un vecchio file grezzo ignorati (la posta non è più rilevata)"
CAMPI_SEGNALABILI = ("stato", "applicazioni", "categorie", "rete", "sessione", "posta", "totali", "altro")
CAMPI_DI_FASCIA = ("stato", "applicazioni", "categorie", "rete")      # richiedono il riferimento a una fascia
STATI_COPERTURA = ("completa", "parziale", "non_disponibile", "non_installato")
MODALITA = ("consuntivo", "collector")
STATI_SESSIONE = ("attiva", "bloccata", "disconnessa", "sospesa", "chiusa", "sconosciuta")

# Nomi di campo che non devono mai entrare nel JSON giornaliero (privacy, minimizzazione).
CAMPI_VIETATI = frozenset({"oggetto", "subject", "file", "path", "percorso", "nome_file", "filename", "url",
                           "mittente", "destinatario", "destinatari", "corpo", "body", "testo_mail", "titolo"})

MAX_DESCRIZIONE = 200          # descrizione delle attività manuali
MAX_NOTA_SEGNALAZIONE = 200
MAX_OSSERVAZIONI = 500        # osservazioni libere del dipendente (decisione del 02/10/2026)
EVENTI_RACCOLTA = ("pausa", "ripresa")
RE_ORA = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"


class ErroreIngresso(ValueError):
    """Riga di raw.jsonl non valida."""


def parse_ts(v, campo: str = "ts") -> dt.datetime:
    if not isinstance(v, str):
        raise ErroreIngresso(f"{campo}: atteso un istante ISO 8601")
    try:
        t = dt.datetime.fromisoformat(v)
    except ValueError as e:
        raise ErroreIngresso(f"{campo}: istante non valido ({v!r})") from e
    if t.tzinfo is None:
        raise ErroreIngresso(f"{campo}: manca il fuso orario ({v!r}); serve l'offset, es. +02:00")
    return t


@dataclass
class Meta:
    giorno: dt.date
    fuso: str = "Europe/Rome"
    dipendente: dict = field(default_factory=dict)
    postazione: dict = field(default_factory=dict)
    versioni: dict = field(default_factory=dict)
    presa_visione: Optional[dict] = None
    modalita: str = "consuntivo"
    copertura_fonti: dict = field(default_factory=dict)
    stato_iniziale_sessione: str = "sconosciuta"
    dati_tecnici_postazione: dict = field(default_factory=dict)


@dataclass
class Evento:
    tipo: str                     # sessione | attivita | app | web | rete | orologio
    ts: dt.datetime
    evento: str = ""              # per sessione
    app: str = ""                 # per app (id canonico)
    exe: str = ""                 # per app: nome dell'eseguibile, solo per la risoluzione (mai in uscita)
    sito: str = ""                # per web: etichetta della whitelist
    dominio: str = ""             # per web: dominio, solo per la risoluzione (mai in uscita)
    operazioni: int = 0           # per rete
    delta_s: int = 0              # per orologio


@dataclass
class Manuale:
    inizio: dt.datetime
    fine: dt.datetime
    categoria: str
    descrizione: str = ""
    troncata: bool = False


@dataclass
class Segnalazione:
    """«Dato apparentemente errato»: riferimento a una fascia (o a un dato di giornata) + nota. Non altera nulla."""
    campo: str
    nota: str
    fascia: Optional[int] = None
    dalle: str = ""
    alle: str = ""
    troncata: bool = False


@dataclass
class Ingresso:
    meta: Meta
    eventi: list = field(default_factory=list)
    manuali: list = field(default_factory=list)
    osservazioni: list = field(default_factory=list)
    avvisi: list = field(default_factory=list)
    segnalazioni: list = field(default_factory=list)


def _pulisci(rec: dict, avvisi: list, riga: int) -> dict:
    vietati = sorted(k for k in rec if k.lower() in CAMPI_VIETATI)
    for k in vietati:
        avvisi.append(f"riga {riga}: campo vietato '{k}' scartato (privacy)")
        rec = {kk: vv for kk, vv in rec.items() if kk != k}
    return rec


def _meta(rec: dict) -> Meta:
    try:
        giorno = dt.date.fromisoformat(rec["giorno"])
    except (KeyError, ValueError) as e:
        raise ErroreIngresso("meta: 'giorno' AAAA-MM-GG obbligatorio") from e
    modalita = rec.get("modalita", "consuntivo")
    if modalita not in MODALITA:
        raise ErroreIngresso(f"meta: modalita deve essere una tra {MODALITA}")
    cop = rec.get("copertura_fonti", {}) or {}
    for k, v in cop.items():
        if v not in STATI_COPERTURA:
            raise ErroreIngresso(f"meta: copertura_fonti.{k} deve essere una tra {STATI_COPERTURA}")
    st = rec.get("stato_iniziale_sessione", "sconosciuta")
    if st not in STATI_SESSIONE:
        raise ErroreIngresso(f"meta: stato_iniziale_sessione deve essere uno tra {STATI_SESSIONE}")
    return Meta(giorno=giorno, fuso=rec.get("fuso", "Europe/Rome"), dipendente=rec.get("dipendente", {}) or {},
                postazione=rec.get("postazione", {}) or {}, versioni=rec.get("versioni", {}) or {},
                presa_visione=rec.get("presa_visione"), modalita=modalita, copertura_fonti=dict(cop),
                stato_iniziale_sessione=st, dati_tecnici_postazione=rec.get("dati_tecnici_postazione", {}) or {})


def parse_records(records: Iterable[dict]) -> Ingresso:
    """Converte i record grezzi (già decodificati) nell'ingresso tipizzato. Funzione pura."""
    meta: Optional[Meta] = None
    eventi, manuali, osservazioni, avvisi, segnalazioni = [], [], [], [], []
    for i, rec in enumerate(records, 1):
        if not isinstance(rec, dict) or "tipo" not in rec:
            raise ErroreIngresso(f"riga {i}: manca il campo 'tipo'")
        rec = _pulisci(rec, avvisi, i)
        t = rec["tipo"]
        if t == "meta":
            if meta is not None:
                raise ErroreIngresso(f"riga {i}: più di un record 'meta'")
            meta = _meta(rec)
        elif t == "sessione":
            ev = rec.get("evento")
            if ev not in EVENTI_SESSIONE:
                raise ErroreIngresso(f"riga {i}: evento di sessione non valido ({ev!r})")
            eventi.append(Evento("sessione", parse_ts(rec.get("ts")), evento=ev))
        elif t == "attivita":
            eventi.append(Evento("attivita", parse_ts(rec.get("ts"))))
        elif t == "app":
            app = str(rec.get("app", "") or "").strip().lower()
            exe = str(rec.get("exe", "") or "").strip()
            if not app and not exe:
                raise ErroreIngresso(f"riga {i}: 'app' o 'exe' obbligatorio")
            eventi.append(Evento("app", parse_ts(rec.get("ts")), app=app, exe=exe))
        elif t == "web":
            eventi.append(Evento("web", parse_ts(rec.get("ts")), sito=str(rec.get("sito", "") or "").strip().lower(),
                                 dominio=solo_host(rec.get("dominio", ""))))
        elif t == "raccolta":
            ev = rec.get("evento")
            if ev not in EVENTI_RACCOLTA:
                raise ErroreIngresso(f"riga {i}: evento di raccolta non valido ({ev!r}); ammessi {EVENTI_RACCOLTA}")
            eventi.append(Evento("raccolta", parse_ts(rec.get("ts")), evento=ev))
        elif t == "rete":
            n = int(rec.get("operazioni", 1) or 1)
            if n < 1:
                raise ErroreIngresso(f"riga {i}: 'operazioni' deve essere ≥ 1")
            eventi.append(Evento("rete", parse_ts(rec.get("ts")), operazioni=n))
        elif t == "posta":           # bonifica B2: la posta non si rileva più; nessun dato della riga viene letto
            if AVVISO_POSTA not in avvisi:
                avvisi.append(AVVISO_POSTA)
        elif t == "manuale":
            cat = rec.get("categoria")
            if cat not in CATEGORIE_MANUALI:
                raise ErroreIngresso(f"riga {i}: categoria manuale non valida ({cat!r})")
            a, b = parse_ts(rec.get("inizio"), "inizio"), parse_ts(rec.get("fine"), "fine")
            if b <= a:
                raise ErroreIngresso(f"riga {i}: 'fine' deve essere dopo 'inizio'")
            d = str(rec.get("descrizione", "") or "").strip()
            manuali.append(Manuale(a, b, cat, d[:MAX_DESCRIZIONE], len(d) > MAX_DESCRIZIONE))
        elif t == "segnalazione":
            segnalazioni.append(_segnalazione(rec, i))
        elif t == "orologio":
            eventi.append(Evento("orologio", parse_ts(rec.get("ts")), delta_s=int(rec.get("delta_s", 0) or 0)))
        elif t == "osservazione":
            osservazioni.append(str(rec.get("testo", "") or "").strip()[:10000])   # limite di 500 applicato in revisione
        else:
            avvisi.append(f"riga {i}: tipo sconosciuto '{t}' ignorato")
    if meta is None:
        raise ErroreIngresso("manca il record 'meta'")
    return Ingresso(meta, eventi, manuali, osservazioni, avvisi, segnalazioni)


def _segnalazione(rec: dict, i: int) -> Segnalazione:
    import re
    campo = rec.get("campo")
    if campo not in CAMPI_SEGNALABILI:
        raise ErroreIngresso(f"riga {i}: campo della segnalazione non valido ({campo!r}); ammessi {CAMPI_SEGNALABILI}")
    fascia = rec.get("fascia")
    if fascia is not None and (not isinstance(fascia, int) or isinstance(fascia, bool) or fascia < 0):
        raise ErroreIngresso(f"riga {i}: 'fascia' deve essere il numero della fascia (intero ≥ 0)")
    dalle, alle = str(rec.get("dalle", "") or ""), str(rec.get("alle", "") or "")
    for v, nome in ((dalle, "dalle"), (alle, "alle")):
        if v and not re.match(RE_ORA, v):
            raise ErroreIngresso(f"riga {i}: '{nome}' deve essere HH:MM")
    if alle and not dalle:
        raise ErroreIngresso(f"riga {i}: 'alle' richiede 'dalle'")
    if campo in CAMPI_DI_FASCIA and fascia is None and not dalle:
        raise ErroreIngresso(f"riga {i}: una segnalazione su '{campo}' deve indicare la fascia ('fascia' o 'dalle')")
    nota = str(rec.get("nota", "") or "").strip()
    if not nota:
        raise ErroreIngresso(f"riga {i}: la segnalazione richiede una nota")
    return Segnalazione(campo, nota[:MAX_NOTA_SEGNALAZIONE], fascia, dalle, alle, len(nota) > MAX_NOTA_SEGNALAZIONE)


def read_jsonl(path: str) -> Ingresso:
    recs = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ErroreIngresso(f"riga {n}: JSON non valido ({e.msg})") from e
    return parse_records(recs)


def read_revisione(path: str) -> Ingresso:
    """File della revisione del dipendente: righe 'manuale', 'segnalazione', 'osservazione' (niente meta)."""
    recs = [{"tipo": "meta", "giorno": "2000-01-01"}]
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if line and not line.startswith("#"):
                try:
                    r = json.loads(line)
                except json.JSONDecodeError as e:
                    raise ErroreIngresso(f"riga {n}: JSON non valido ({e.msg})") from e
                if r.get("tipo") not in ("manuale", "segnalazione", "osservazione"):
                    raise ErroreIngresso(f"riga {n}: attesi solo 'manuale', 'segnalazione' o 'osservazione'")
                recs.append(r)
    return parse_records(recs)


def read_jsonl_manuali(path: str) -> list:
    """File delle sole attività manuali (compatibilità)."""
    recs = [{"tipo": "meta", "giorno": "2000-01-01"}]
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if line and not line.startswith("#"):
                try:
                    r = json.loads(line)
                except json.JSONDecodeError as e:
                    raise ErroreIngresso(f"riga {n}: JSON non valido ({e.msg})") from e
                if r.get("tipo") != "manuale":
                    raise ErroreIngresso(f"riga {n}: atteso tipo 'manuale'")
                recs.append(r)
    return parse_records(recs).manuali
