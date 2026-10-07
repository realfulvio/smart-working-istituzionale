"""Aggregatore: eventi grezzi normalizzati -> JSON giornaliero. Solo funzioni pure, nessun I/O
(a parte la lettura della mappatura predefinita config/applicazioni.json se non ne viene passata una).

Regole (dettaglio nel codice e in schema/giornaliero.schema.json):
- giornata divisa in fasce di 15 minuti dalla mezzanotte locale alla successiva (92/96/100 fasce con l'ora legale);
- stato di ogni fascia: attivita_rilevata | nessuna_attivita_informatica_rilevata | sessione_bloccata |
  sessione_disconnessa | sessione_chiusa | raccolta_sospesa | dato_non_disponibile. Un vuoto NON significa mai
  «assenza di lavoro»; «raccolta_sospesa» = il dipendente ha premuto «Pausa raccolta» (nessun dato raccolto in quel periodo);
- categorie per fascia (office, posta = applicazione di posta in uso, halley, web_generico, rete, interazione_postazione + quelle del CED);
  la rete è solo una categoria informativa: da sola non prova mai l'uso della postazione;
- applicazioni contate per fascia solo come usata sì/no; nessuna durata ricavata dal numero di fasce;
- dati automatici (origine: automatica) e dichiarati dal dipendente (origine: dichiarata) restano separati:
  manuali, osservazioni e segnalazioni non modificano mai fasce né totali rilevati.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import re
from typing import Optional
from zoneinfo import ZoneInfo

from . import SCHEMA_VERSION, __version__
from .mappa import APP_SCONOSCIUTA, Mappa
from .modelli import CATEGORIE_MANUALI, MAX_OSSERVAZIONI, Ingresso, Manuale, Segnalazione

from .configurazione import FASCIA_MIN
FASCIA = dt.timedelta(minutes=FASCIA_MIN)
STATI_FASCIA = ("attivita_rilevata", "nessuna_attivita_informatica_rilevata", "sessione_bloccata",
                "sessione_disconnessa", "sessione_chiusa", "raccolta_sospesa", "dato_non_disponibile")

# transizioni della macchina a stati della sessione
TRANSIZIONI = {"accesso": "attiva", "sblocco": "attiva", "riconnessione": "attiva", "ripresa": "attiva",
               "blocco": "bloccata", "disconnessione": "disconnessa", "sospensione": "sospesa",
               "chiusura": "chiusa", "spegnimento": "chiusa",
               # collector (M3): «Avvia giornata»/«Riprendi» = sessione attiva in quell'istante (il dipendente ha
               # premuto il pulsante); «Chiudi giornata»/«Pausa» = da lì in poi lo stato non è più osservato
               "avvio_raccolta": "attiva", "fine_raccolta": "sconosciuta"}
# stato di sessione prevalente -> stato della fascia (senza evidenze di attività).
# Decisione: sospensione/ibernazione = sessione_chiusa; disconnessione (VDI/RDP) = sessione_disconnessa.
MAPPA_STATO = {"attiva": "nessuna_attivita_informatica_rilevata", "bloccata": "sessione_bloccata",
               "disconnessa": "sessione_disconnessa", "sospesa": "sessione_chiusa", "chiusa": "sessione_chiusa",
               "sconosciuta": "dato_non_disponibile"}
# a parità di durata vince lo stato che compare prima
PRIORITA = ("bloccata", "disconnessa", "sospesa", "chiusa", "attiva", "sconosciuta")
EVIDENZA_POSTAZIONE = ("attivita", "app")          # provano l'uso della postazione (anche sblocco implicito)
FONTI_ATTIVITA = ("attivita", "app", "browser")
FONTE_DI_TIPO = {"web": "browser"}
EVIDENZE_RACCOLTE = ("attivita", "app", "web", "rete")   # ciò che la pausa della raccolta esclude                  # tipo di evento -> fonte in copertura_fonti
RE_ID = re.compile(r"^[a-z0-9_]{1,40}\Z")      # \Z, non $: «$» accetta anche un a-capo finale
SOGLIA_OROLOGIO_S = 120
NOTE_TECNICHE = ("sblocco_implicito", "cambio_orario")
ORIGINE_DATI = {"sessione": "automatica", "fasce": "automatica", "totali.rilevati": "automatica",
                "classificazione": "automatica", "avvisi": "automatica",
                "raccolta": "automatica",
                "manuali": "dichiarata", "osservazioni_dipendente": "dichiarata",
                "segnalazioni_dipendente": "dichiarata", "totali.con_manuali": "combinata"}
# profilo dell'AI locale (stessa pipeline su 8 e 16 GB; cambia solo il modello che riscrive i testi)
PROFILI_AI = {"AI-LIGHT": "~1,5–1,7B parametri", "AI-STANDARD": "~4B parametri"}
SOGLIA_RAM_STANDARD_GB = 14     # le macchine da 16 GB nominali risultano 15,7–15,9 GB a Windows


# ---------------------------------------------------------------------------------------------- utilità
def day_bounds(giorno: dt.date, fuso: str) -> tuple[dt.datetime, dt.datetime]:
    tz = ZoneInfo(fuso)
    a = dt.datetime.combine(giorno, dt.time(0, 0), tzinfo=tz)
    b = dt.datetime.combine(giorno + dt.timedelta(days=1), dt.time(0, 0), tzinfo=tz)
    return a, b


def slot_starts(giorno: dt.date, fuso: str) -> list[dt.datetime]:
    """Inizi delle fasce in tempo assoluto (UTC), così l'ora legale dà 92 o 100 fasce senza ambiguità."""
    a, b = day_bounds(giorno, fuso)
    t, end, out = a.astimezone(dt.timezone.utc), b.astimezone(dt.timezone.utc), []
    while t < end:
        out.append(t)
        t += FASCIA
    return out


def _loc(t: dt.datetime, tz: ZoneInfo) -> dt.datetime:
    return t.astimezone(tz)


def iso(t: dt.datetime, tz: ZoneInfo) -> str:
    return _loc(t, tz).isoformat(timespec="seconds")


def hhmm(t: dt.datetime, tz: ZoneInfo) -> str:
    return _loc(t, tz).strftime("%H:%M")


def _fine_label(fine_iso: str, end: dt.datetime, tz: ZoneInfo) -> str:
    t = dt.datetime.fromisoformat(fine_iso)
    return "24:00" if t >= end else hhmm(t, tz)


def merge(intervals: list[tuple[dt.datetime, dt.datetime]]) -> list[tuple[dt.datetime, dt.datetime]]:
    out: list[list[dt.datetime]] = []
    for a, b in sorted(intervals):
        if b <= a:
            continue
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def minutes(intervals) -> int:
    return int(round(sum((b - a).total_seconds() for a, b in intervals) / 60))


def intersect(xs, ys) -> list[tuple[dt.datetime, dt.datetime]]:
    out, i, j = [], 0, 0
    xs, ys = merge(xs), merge(ys)
    while i < len(xs) and j < len(ys):
        a, b = max(xs[i][0], ys[j][0]), min(xs[i][1], ys[j][1])
        if a < b:
            out.append((a, b))
        if xs[i][1] < ys[j][1]:
            i += 1
        else:
            j += 1
    return out


# ---------------------------------------------------------------------------------- linea della sessione
def session_timeline(inp: Ingresso, start: dt.datetime, end: dt.datetime, avvisi: list):
    """Restituisce (segmenti, eventi_sessione). segmenti = [(inizio, fine, stato)] che coprono [start, end).

    - gli eventi precedenti la mezzanotte servono solo a stabilire lo stato iniziale (giornata a cavallo);
    - un'evidenza della postazione (attivita/app) con sessione non attiva implica uno «sblocco implicito»;
    - con stato sconosciuto l'evidenza rende attiva la fascia ma non cambia lo stato (non si inventa la sessione).
    """
    tz = ZoneInfo(inp.meta.fuso)
    stato = inp.meta.stato_iniziale_sessione
    sess = [e for e in inp.eventi if e.tipo == "sessione"]
    evid = [e for e in inp.eventi if e.tipo in EVIDENZA_POSTAZIONE]
    # ordine stabile: per istante, poi gli eventi di sessione prima delle evidenze
    stream = sorted([(e.ts, 0, i, e) for i, e in enumerate(sess)] + [(e.ts, 1, i, e) for i, e in enumerate(evid)],
                    key=lambda x: (x[0], x[1], x[2]))
    changes: list[tuple[dt.datetime, str]] = []
    eventi_out, impliciti = [], 0
    for ts, kind, _, e in stream:
        if ts >= end:
            break
        if kind == 0:
            nuovo = TRANSIZIONI[e.evento]
            if ts < start:
                stato = nuovo
                continue
            eventi_out.append({"ora": hhmm(ts, tz), "ts": iso(ts, tz), "evento": e.evento})
            if nuovo != stato:
                changes.append((ts, nuovo))
            stato = nuovo
        else:
            if stato in ("bloccata", "disconnessa", "sospesa", "chiusa"):
                if ts >= start:
                    changes.append((ts, "attiva"))
                    eventi_out.append({"ora": hhmm(ts, tz), "ts": iso(ts, tz), "evento": "sblocco",
                                       "implicito": True})
                    impliciti += 1
                stato = "attiva"
    if impliciti:
        avvisi.append(f"{impliciti} sblocchi impliciti: attività della postazione con sessione non attiva "
                      "(evento di sblocco/accesso non registrato dalla fonte)")
    # stato a mezzanotte = stato dopo gli eventi < start; ricostruisco i segmenti
    init = inp.meta.stato_iniziale_sessione
    for ts, kind, _, e in stream:
        if ts >= start:
            break
        if kind == 0:
            init = TRANSIZIONI[e.evento]
        elif init in ("bloccata", "disconnessa", "sospesa", "chiusa"):
            init = "attiva"
    segs, cur_t, cur_s = [], start, init
    for ts, nuovo in changes:
        if ts > cur_t:
            segs.append((cur_t, ts, cur_s))
        cur_t, cur_s = max(cur_t, ts), nuovo
    segs.append((cur_t, end, cur_s))
    return [s for s in segs if s[1] > s[0]], eventi_out, init


# ------------------------------------------------------------------------------------------- copertura
def coverage(inp: Ingresso) -> dict:
    """copertura_fonti dichiarata dalla fonte; una fonte non dichiarata ma con eventi vale «parziale»."""
    cop = dict(inp.meta.copertura_fonti)
    presenti = {FONTE_DI_TIPO.get(e.tipo, e.tipo) for e in inp.eventi}
    for f in ("sessione", "attivita", "app", "rete", "browser"):
        if f not in cop:
            cop[f] = "parziale" if f in presenti else "non_disponibile"
    return dict(sorted(cop.items()))


def profilo_ai(postazione: dict) -> dict:
    """AI-LIGHT (≤ 8 GB, ~1,5–1,7B) o AI-STANDARD (≥ 16 GB nominali, ~4B); il CED può forzarlo nel meta."""
    forzato = postazione.get("profilo_ai")
    if isinstance(forzato, str) and forzato in PROFILI_AI:
        p, crit = forzato, "impostato_ced"
    else:
        ram = postazione.get("ram_gb")
        if not isinstance(ram, (int, float)) or isinstance(ram, bool) or ram <= 0:
            p, crit = "AI-LIGHT", "ram_non_rilevata"
        else:
            p, crit = ("AI-STANDARD" if ram >= SOGLIA_RAM_STANDARD_GB else "AI-LIGHT"), "ram_rilevata"
    return {"profilo": p, "modello_indicativo": PROFILI_AI[p], "criterio": crit}


def _postazione(post: dict) -> dict:
    out = {k: post[k] for k in ("host", "tipo", "ram_gb") if k in post}
    out["profilo_ai"] = profilo_ai(post)
    return out


def _state_at(segs, t: dt.datetime) -> str:
    for sa, sb, st in segs:
        if sa <= t < sb:
            return st
    return "sconosciuta"


def pause_raccolta(eventi, start: dt.datetime, end: dt.datetime) -> list:
    """Intervalli [inizio, fine) di pausa della raccolta nella giornata. Una pausa del giorno prima non ripresa vale
    da mezzanotte; una pausa non ripresa entro la giornata dura fino a mezzanotte (o fino a «Chiudi giornata»)."""
    # «Chiudi giornata» durante una pausa (fine_raccolta) chiude anche la pausa: dopo non c'è più nulla da osservare
    ev = sorted([(e.ts, e.evento) for e in eventi if e.tipo == "raccolta"]
                + [(e.ts, "ripresa") for e in eventi if e.tipo == "sessione" and e.evento == "fine_raccolta"])
    out, inizio = [], None
    for t, k in ev:
        if t >= end:
            break
        if k == "pausa" and inizio is None:
            inizio = max(t, start)
        elif k == "ripresa" and inizio is not None:
            if t > start and t > inizio:
                out.append((inizio, t))
            inizio = None
    if inizio is not None:
        out.append((inizio, end))
    return [(a, b) for a, b in out if b > a]


# ------------------------------------------------------------------------------------------- aggregazione
def aggregate(inp: Ingresso, mappa: Optional[Mappa] = None) -> dict:
    """Funzione pura: stesso ingresso (e stessa mappatura) -> stesso JSON (senza sigilli)."""
    mappa = mappa or Mappa.predefinita()
    m = inp.meta
    tz = ZoneInfo(m.fuso)
    start, end = day_bounds(m.giorno, m.fuso)
    end_utc = end.astimezone(dt.timezone.utc)
    avvisi = list(inp.avvisi)

    fuori = [e for e in inp.eventi if not (start <= e.ts < end) and e.tipo not in ("sessione", "raccolta")]
    if fuori:
        avvisi.append(f"{len(fuori)} eventi fuori dalla giornata ignorati (appartengono al giorno precedente o successivo)")
    # copie: l'ingresso non viene mai modificato
    eventi = [dataclasses.replace(e) for e in inp.eventi if start <= e.ts < end or e.tipo in ("sessione", "raccolta")]

    # identificatori ammessi (niente nomi di file, oggetti, URL); l'eseguibile si traduce in id e poi si scarta
    non_conformi = 0
    for e in eventi:
        if e.tipo == "app":
            if e.exe:
                e.app, e.exe = mappa.da_exe(e.exe), ""
                if e.app == APP_SCONOSCIUTA[0]:        # bonifica B5: eseguibile non ammesso -> solo «attività», senza nome
                    e.tipo, e.app = "attivita", ""
            elif not RE_ID.match(e.app):
                non_conformi += 1
                e.app = ""
        if e.tipo == "web" and e.dominio:              # il dominio serve solo a trovare il sito in whitelist
            e.sito, e.dominio = (e.sito or mappa.da_dominio(e.dominio)), ""
        if e.tipo == "web" and e.sito and not RE_ID.match(e.sito):
            avvisi.append("un'etichetta di sito non conforme ignorata (considerata web generico)")
            e.sito = ""
    if non_conformi:
        avvisi.append(f"{non_conformi} nomi di applicazione non conformi scartati (ammessi solo identificativi a-z0-9_)")
    eventi = [e for e in eventi if not (e.tipo == "app" and not e.app)]

    # pause della raccolta («Pausa raccolta»): nessun dato raccolto; eventi eventualmente presenti scartati
    pause = pause_raccolta(eventi, start, end)
    dentro_pausa = [e for e in eventi if e.tipo in EVIDENZE_RACCOLTE and any(a <= e.ts < b for a, b in pause)]
    if dentro_pausa:
        avvisi.append(f"{len(dentro_pausa)} eventi registrati durante la pausa della raccolta scartati")
        ids = {id(e) for e in dentro_pausa}
        eventi = [e for e in eventi if id(e) not in ids]

    # deduplica (stessa fonte, stesso istante, stessi campi)
    seen, dedup = set(), []
    for e in eventi:
        k = (e.tipo, e.ts, e.evento, e.app, e.sito, e.operazioni, e.delta_s)
        if k in seen:
            continue
        seen.add(k)
        dedup.append(e)
    if len(dedup) < len(eventi):
        avvisi.append(f"{len(eventi) - len(dedup)} eventi duplicati scartati")
    eventi = sorted(dedup, key=lambda e: (e.ts, e.tipo, e.evento, e.app, e.sito, e.operazioni, e.delta_s))

    # cambi dell'ora di sistema: |delta| ≥ 120 s -> avviso e fasce marcate in [ts-|delta|, ts+|delta|]
    finestre_orologio = []
    for e in eventi:
        if e.tipo == "orologio" and abs(e.delta_s) >= SOGLIA_OROLOGIO_S:
            d = dt.timedelta(seconds=abs(e.delta_s))
            finestre_orologio.append((e.ts - d, e.ts + d))
            avvisi.append(f"cambio dell'ora di sistema alle {hhmm(e.ts, tz)} ({e.delta_s:+d} s): le fasce vicine sono "
                          "marcate 'cambio_orario' e i loro orari possono essere imprecisi")

    inp2 = Ingresso(m, eventi, inp.manuali, inp.osservazioni)
    segs, eventi_sessione, stato_iniziale = session_timeline(inp2, start, end, avvisi)
    impliciti = [dt.datetime.fromisoformat(e["ts"]) for e in eventi_sessione if e.get("implicito")]
    cop = coverage(inp2)
    attivita_coperta = any(cop.get(f) in ("completa", "parziale") for f in FONTI_ATTIVITA)

    starts = slot_starts(m.giorno, m.fuso)
    fasce, app_usate, cat_usate, siti_usati = [], set(), set(), set()
    for n, a in enumerate(starts):
        b = min(a + FASCIA, end_utc)
        durate = {s: 0.0 for s in PRIORITA}
        for sa, sb, st in segs:
            x, y = max(sa, a), min(sb, b)
            if x < y:
                durate[st] += (y - x).total_seconds()
        dentro = [e for e in eventi if a <= e.ts < b]
        sospesa = sum((min(y, b) - max(x, a)).total_seconds() for x, y in pause if x < b and a < y)
        apps, cats, siti, evid = set(), set(), set(), {}
        attiva_prova, rete_op = False, 0
        for e in dentro:
            if e.tipo in ("attivita", "app", "web", "rete"):
                evid[e.tipo] = evid.get(e.tipo, 0) + 1
            if e.tipo == "app":                     # uso di un'applicazione: prova l'uso della postazione
                apps.add(e.app)
                cats.add(mappa.app(e.app)[1])
                attiva_prova = True
            elif e.tipo == "attivita":
                cats.add("interazione_postazione")
                attiva_prova = True
            elif e.tipo == "web" and _state_at(segs, e.ts) == "attiva":
                cats.add(mappa.sito(e.sito)[1] if e.sito in mappa.siti else "web_generico")
                if e.sito in mappa.siti:
                    siti.add(e.sito)
                attiva_prova = True
            elif e.tipo == "rete":                  # solo categoria e conteggio: mai prova di interazione
                cats.add("rete")
                rete_op += e.operazioni
        # il browser vale come «navigazione generica» solo se nella fascia non c'è un sito riconosciuto (es. Halley)
        if siti and "web_generico" in cats and not any(e.tipo == "web" and e.sito not in mappa.siti
                                                         and _state_at(segs, e.ts) == "attiva" for e in dentro) \
                and not any(mappa.sito(x)[1] == "web_generico" for x in siti):
            cats.discard("web_generico")
        if attiva_prova:
            stato = "attivita_rilevata"
        elif sospesa and sospesa * 2 >= (b - a).total_seconds():
            stato = "raccolta_sospesa"            # pausa per almeno metà fascia: stato a sé, mai «assenza di lavoro»
        else:
            prevalente = max(PRIORITA, key=lambda s: (durate[s], -PRIORITA.index(s)))
            stato = MAPPA_STATO[prevalente]
            if stato == "nessuna_attivita_informatica_rilevata" and not attivita_coperta:
                stato = "dato_non_disponibile"
        note = []
        if any(a <= t < b for t in impliciti):
            note.append("sblocco_implicito")
        if any(x < b and a < y for x, y in finestre_orologio):
            note.append("cambio_orario")
        app_usate |= apps
        cat_usate |= cats
        siti_usati |= siti
        fasce.append({"n": n, "inizio": iso(a, tz), "fine": iso(b, tz), "ora": hhmm(a, tz), "stato": stato,
                      "origine": "automatica", "app": sorted(apps), "categorie": sorted(cats), "siti": sorted(siti),
                      "evidenze": dict(sorted(evid.items())), "rete": bool(rete_op), "note_tecniche": note})

    rilevati = compute_rilevati(fasce, m.giorno, m.fuso)

    # ----------------------------------------------------------------------------------------- sessione
    minuti_sessione = {s: 0 for s in PRIORITA}
    for sa, sb, st in segs:
        minuti_sessione[st] += (sb - sa).total_seconds() / 60
    espliciti = [e for e in eventi_sessione if not e.get("implicito")]
    sessione = {
        "stato_iniziale": stato_iniziale,
        "primo_evento": espliciti[0]["ora"] if espliciti else None,
        "ultimo_evento": espliciti[-1]["ora"] if espliciti else None,
        "eventi": eventi_sessione,
        
    }

    classificazione = {
        "versione_mappa": mappa.versione,
        "applicazioni": {a: {"etichetta": mappa.app(a)[0], "categoria": mappa.app(a)[1]} for a in sorted(app_usate)},
        "categorie": {c: mappa.etichetta_categoria(c) for c in sorted(cat_usate)},
        "siti": {x: {"etichetta": mappa.sito(x)[0], "categoria": mappa.sito(x)[1]} for x in sorted(siti_usati)},
    }
    raccolta = {"pause": [{"inizio": iso(x, tz), "fine": iso(y, tz), "dalle": hhmm(x, tz),
                           "alle": "24:00" if y >= end else hhmm(y, tz)} for x, y in pause],
                }

    doc = {
        "schema": SCHEMA_VERSION,
        "identita_documento": __import__("resoconto.identita", fromlist=["snapshot"]).snapshot(),
        "giorno": m.giorno.isoformat(),
        "fuso": m.fuso,
        "dipendente": {k: v for k, v in m.dipendente.items() if k in ("nome", "ufficio", "matricola")},
        "versioni": {**m.versioni, "aggregatore": __version__, "mappa_applicazioni": mappa.versione},
        "presa_visione": m.presa_visione,
        "modalita": m.modalita,
        "copertura_fonti": cop,
        "origine_dati": {"sessione": "automatic", "fasce": "automatic", "totali.rilevati": "automatic",
                         "classificazione": "automatic", "avvisi": "automatic", "raccolta": "automatic",
                         "manuali": "declared", "osservazioni_dipendente": "observation",
                         "segnalazioni_dipendente": "observation", "sintesi_ai": "AI-generated"},
        "classificazione": classificazione,
        "sessione": sessione,
        "raccolta": raccolta,
        "fasce": fasce,
        "totali": {"rilevati": rilevati, "con_manuali": {}},
        "manuali": [],
        "osservazioni_dipendente": "",
        "segnalazioni_dipendente": [],
        "avvisi": sorted(avvisi),
        "avvisi_revisione": [],
        "sintesi_ai": None,
        "integrita": {"sigillo_tecnico": None, "sigillo_finale": None},
    }
    if m.dati_tecnici_postazione:
        from collector.postazione import minimizza
        doc["dati_tecnici_postazione"] = minimizza(m.dati_tecnici_postazione)
    return apply_review(doc, inp.manuali, "\n".join(o for o in inp.osservazioni if o), inp.segnalazioni)


def compute_rilevati(fasce: list, giorno, fuso: str) -> dict:
    """Totali tecnici ricalcolabili dalle sole fasce (usato anche dalla verifica di coerenza)."""
    tz = ZoneInfo(fuso)
    if isinstance(giorno, str):
        giorno = dt.date.fromisoformat(giorno)
    _, end = day_bounds(giorno, fuso)
    conta = {s: 0 for s in STATI_FASCIA}
    per_app: dict[str, int] = {}
    per_cat: dict[str, int] = {}
    per_sito: dict[str, int] = {}
    for f in fasce:
        for x in f.get("siti", []):
            per_sito[x] = per_sito.get(x, 0) + 1
        conta[f["stato"]] += 1
        for ap in f["app"]:
            per_app[ap] = per_app.get(ap, 0) + 1
        for c in f["categorie"]:
            per_cat[c] = per_cat.get(c, 0) + 1
    attive = [f for f in fasce if f["stato"] == "attivita_rilevata"]
    ordina = lambda d: sorted(d.items())  # noqa: E731
    return {
        "durata_fascia_min": int((dt.datetime.fromisoformat(fasce[0]["fine"]) - dt.datetime.fromisoformat(fasce[0]["inizio"])).total_seconds() / 60) if fasce else FASCIA_MIN,
        "numero_fasce": len(fasce),
        "fasce_per_stato": conta,
        
        
        "prima_attivita": attive[0]["ora"] if attive else None,
        "ultima_attivita": _fine_label(attive[-1]["fine"], end, tz) if attive else None,
        "per_applicazione": [{"app": k, "fasce": v} for k, v in ordina(per_app)],
        "per_categoria": [{"categoria": k, "fasce": v} for k, v in ordina(per_cat)],
        "per_sito": [{"sito": k, "fasce": v} for k, v in ordina(per_sito)],
        "fasce_con_rete": sum(1 for f in fasce if f["rete"]),
        
        "fasce_con_note_tecniche": sum(1 for f in fasce if f["note_tecniche"]),
    }


# ------------------------------------------------------------------------------------- revisione dipendente
def _manual_intervals(doc: dict) -> list:
    return [(dt.datetime.fromisoformat(x["inizio"]), dt.datetime.fromisoformat(x["fine"])) for x in doc["manuali"]]


def _active_intervals(doc: dict) -> list:
    return [(dt.datetime.fromisoformat(f["inizio"]), dt.datetime.fromisoformat(f["fine"]))
            for f in doc["fasce"] if f["stato"] == "attivita_rilevata"]


def compute_con_manuali(doc: dict) -> dict:
    return {"numero_attivita_dichiarate": len(doc["manuali"])}


def _hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def _risolvi_segnalazione(doc: dict, s: Segnalazione) -> tuple[Optional[int], Optional[int]]:
    """Riferimento -> (fascia_da, fascia_a). Con l'ora ripetuta (ritorno all'ora solare) vale la prima occorrenza."""
    fasce = doc["fasce"]
    if s.fascia is not None:
        if s.fascia >= len(fasce):
            raise ValueError(f"segnalazione: la fascia {s.fascia} non esiste (la giornata ha {len(fasce)} fasce)")
        return s.fascia, s.fascia
    if not s.dalle:
        return None, None
    a = _hm(s.dalle)
    da = next((f["n"] for f in fasce if _hm(f["ora"]) <= a < _hm(f["ora"]) + doc["totali"]["rilevati"]["durata_fascia_min"]), None)
    if da is None:
        raise ValueError(f"segnalazione: nessuna fascia alle {s.dalle}")
    if not s.alle:
        return da, da
    b = _hm(s.alle)
    if b <= a:
        raise ValueError("segnalazione: 'alle' deve essere dopo 'dalle'")
    fa = [f["n"] for f in fasce[da:] if _hm(f["ora"]) < b and _hm(f["ora"]) >= _hm(fasce[da]["ora"])]
    return da, (fa[-1] if fa else da)


def apply_review(doc: dict, manuali: list[Manuale], osservazioni: str = "",
                 segnalazioni: list[Segnalazione] = ()) -> dict:
    """Aggiunge attività manuali, osservazioni e segnalazioni del dipendente (origine: dichiarata).
    NON tocca la parte tecnica (fasce, rilevati, sessione...): una segnalazione è un riferimento + nota.

    Le voci manuali sono ritagliate alla giornata; quelle interamente fuori sono scartate con un avviso.
    """
    tz = ZoneInfo(doc["fuso"])
    start, end = day_bounds(dt.date.fromisoformat(doc["giorno"]), doc["fuso"])
    out = dict(doc)
    rev = list(doc.get("avvisi_revisione", []))
    voci = list(doc.get("manuali", []))
    for mm in sorted(manuali, key=lambda x: (x.inizio, x.fine, x.categoria)):
        if mm.categoria not in CATEGORIE_MANUALI:
            raise ValueError(f"categoria manuale non valida: {mm.categoria}")
        a, b = max(mm.inizio, start), min(mm.fine, end)
        if b <= a:
            rev.append("un'attività manuale fuori dalla giornata è stata scartata")
            continue
        voce = {"id": f"m{len(voci) + 1}", "categoria": mm.categoria, "inizio": iso(a, tz), "fine": iso(b, tz),
                "minuti": int(round((b - a).total_seconds() / 60)), "descrizione": mm.descrizione,
                "origine": "dichiarata"}
        if (a, b) != (mm.inizio, mm.fine):
            voce["ritagliata"] = True
            rev.append(f"attività manuale {voce['id']} ritagliata ai limiti della giornata")
        if mm.troncata:
            rev.append(f"descrizione dell'attività manuale {voce['id']} accorciata a 200 caratteri")
        voci.append(voce)
    out["manuali"] = voci
    segn = list(doc.get("segnalazioni_dipendente", []))
    for s in segnalazioni:
        da, fa = _risolvi_segnalazione(doc, s)
        sid = f"s{len(segn) + 1}"
        segn.append({"id": sid, "campo": s.campo, "fascia_da": da, "fascia_a": fa,
                     "dalle": doc["fasce"][da]["ora"] if da is not None else None,
                     "alle": _fine_label(doc["fasce"][fa]["fine"], end, tz) if fa is not None else None,
                     "nota": s.nota, "origine": "dichiarata"})
        if s.troncata:
            rev.append(f"nota della segnalazione {sid} accorciata a 200 caratteri")
    out["segnalazioni_dipendente"] = segn
    out["avvisi_revisione"] = rev
    if out.get("sintesi_ai"):
        # la revisione cambia i fatti: la sintesi precedente non è più valida e va rigenerata («Genera resoconto»)
        out["sintesi_ai"] = None
        rev.append("sintesi della giornata annullata dalla revisione: va rigenerata")
    out.setdefault("sintesi_ai", None)
    if osservazioni:
        testo = doc.get("osservazioni_dipendente", "") + ("\n" if doc.get("osservazioni_dipendente") else "") + osservazioni
        if len(testo) > MAX_OSSERVAZIONI:
            rev.append(f"osservazioni accorciate a {MAX_OSSERVAZIONI} caratteri")
        out["osservazioni_dipendente"] = testo[:MAX_OSSERVAZIONI]
    t = dict(doc["totali"])
    t["con_manuali"] = compute_con_manuali(out)
    out["totali"] = t
    return out
