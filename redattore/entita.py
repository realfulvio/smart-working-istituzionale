"""Controllo «tipo di entità» e abbinamento numero↔entità (M7, deterministico).

Il 4B in M6 confondeva applicazioni e categorie («le categorie prevalenti sono … Microsoft Word (270 minuti)») e a volte
attribuiva a un'entità i minuti di un'altra. Le entità si ricavano dai fatti stessi (nessuna lista a parte):
  - applicazioni  dal fatto «Applicazioni rilevate …: Microsoft Word 120 minuti, …»;
  - categorie     dal fatto «Categorie di attività rilevate …: Strumenti d'ufficio 90 minuti, …»;
  - siti          dal fatto «Siti di lavoro riconosciuti: Halley 165 minuti, …»;
  - attività dichiarate (riunione, telefonata…) dai fatti «Attività dichiarata dal dipendente (riunione) dalle … alle …».
Regole:
  E1. tipo: un'entità citata dopo una parola che introduce un altro tipo («categorie …», «applicazioni …», «siti …»)
      nella stessa parte di frase è un errore (es. un'applicazione presentata come categoria e viceversa);
  E2. numero↔entità: i minuti scritti subito dopo un'entità («Microsoft Word (270 minuti)», «Halley per 165 minuti»)
      devono essere quelli di quell'entità nei fatti; vale anche per i minuti scritti subito prima («165 minuti con
      Microsoft Excel»);
  E3. orari↔attività dichiarata: l'intervallo scritto subito dopo un tipo di attività dichiarata («riunione dalle
      11:00 alle 11:45») deve essere quello di un'attività dichiarata di quel tipo.
Un nome che appartiene a più tipi (es. «Halley» sito e «Gestionale Halley» categoria) è ambiguo e non viene giudicato
dalla regola E1. Ogni problema segnalato porta al secondo tentativo o al testo standard: in caso di dubbio il controllo
sbaglia per eccesso di prudenza, mai lasciando passare una confusione.
"""
from __future__ import annotations

import re
import unicodedata

TIPI = {"applicazioni": "app", "categorie": "cat", "siti": "sito"}
NOMI_TIPO = {"app": "un'applicazione", "cat": "una categoria", "sito": "un sito di lavoro"}
# parole che introducono un tipo di entità (radici, confronto su testo normalizzato)
INDICATORI = [(r"categori", "cat"), (r"applicazion", "app"), (r"programm", "app"), (r"\bapp\b", "app"),
              (r"\bsiti\b", "sito"), (r"\bsito\b", "sito"), (r"\bportal", "sito"),
              (r"\buso di\b", "app"), (r"\butilizzo di\b", "app"), (r"\busat", "app"), (r"\butilizzat", "app")]
GENERICHE = {"altra", "applicazione", "applicazioni", "microsoft", "strumenti", "ufficio", "posta", "elettronica",
             "navigazione", "uso", "della", "delle", "dell", "postazione", "servizi", "portale", "online", "sito",
             "agenzia", "gestionale", "comune", "web"}
MANUALI = {"riunione": r"riunion", "telefonata": r"telefon", "lavoro su documenti cartacei": r"cartace",
           "sopralluogo": r"sopralluog", "formazione": r"formazion", "altra attività": r"altra attivit"}
RE_VOCE = re.compile(r"^\s*(.+?)(?:\s+(\d+)\s+minuti)?\s*$")   # B4: i fatti non portano più i minuti
# E2b: minuti scritti PRIMA dell'entità («165 minuti con Microsoft Excel», «per 45 minuti il Browser»): senza questo
# controllo due numeri scambiati tra due entità passavano, perché E2 guarda solo il numero dopo il nome
RE_MIN_PRIMA = re.compile(r"(\d+)\s+minut[io]\s+(?:(?:di|con|su|in|per|tra|nel|nella|nello|sul|sulla|uso|dell'uso|l'uso|dall'uso|il|lo|la|l'|i|le|gli)\s*){0,4}$")
RE_MIN = re.compile(r"^[\s(:,]*(?:[a-zà-ù']+\s+){0,4}?(\d+)\s+minut")
_T = r"([01]?\d|2[0-4])\s?[:.]\s?([0-5]\d)"
RE_INTERVALLO = re.compile(r"(?:dalle\s+" + _T + r"\s+alle\s+" + _T + r"|tra\s+le\s+" + _T + r"\s+e\s+le\s+" + _T
                           + r"|" + _T + r"\s?[–—-]\s?" + _T + ")")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", (s or "").lower()).replace("’", "'")
    return " ".join(s.split())


def entita_dai_fatti(fatti: list[dict]) -> dict[str, list[tuple[str, int, int]]]:
    """{"app": [(etichetta normalizzata, minuti, id fatto)], "cat": [...], "sito": [...]}."""
    out = {"app": [], "cat": [], "sito": []}
    for f in fatti:
        t = f["testo"]
        tipo = {"applicazioni": "app", "categorie": "cat", "siti": "sito"}.get(f.get("tipo"))
        if not tipo or ":" not in t:
            continue
        for voce in t.split(":", 1)[1].rstrip(".").split(","):
            m = RE_VOCE.match(voce)
            if m:
                out[tipo].append((norm(m.group(1)), int(m.group(2)) if m.group(2) else -1, f["id"]))
    return out


def _alias(etichetta: str) -> set[str]:
    out = {etichetta}
    for w in re.findall(r"[a-zà-ù]{4,}", etichetta):
        if w not in GENERICHE:
            out.add(w)
    return out


def indice(fatti: list[dict]) -> list[tuple[str, str, str]]:
    """[(alias, tipo, etichetta)], solo alias non ambigui (un alias di più tipi viene tolto), dal più lungo."""
    ent = entita_dai_fatti(fatti)
    per_alias: dict[str, set] = {}
    etich: dict[tuple, str] = {}
    for tipo, voci in ent.items():
        for et, _m, _i in voci:
            for a in _alias(et):
                per_alias.setdefault(a, set()).add(tipo)
                etich[(a, tipo)] = et
    # un nome di categoria che contiene il nome di un sito (Gestionale Halley / Halley) rende ambigua la radice comune
    out = [(a, next(iter(t)), etich[(a, next(iter(t)))]) for a, t in per_alias.items() if len(t) == 1]
    return sorted(out, key=lambda x: -len(x[0]))


def _menzioni(testo_n: str, idx) -> list[tuple[int, int, str, str]]:
    """[(inizio, fine, tipo, etichetta)] senza sovrapposizioni (prima gli alias più lunghi)."""
    prese, out = [], []
    for a, tipo, et in idx:
        for m in re.finditer(r"(?<![a-zà-ù])" + re.escape(a) + r"(?![a-zà-ù])", testo_n):
            if any(m.start() < b and a0 < m.end() for a0, b in prese):
                continue
            prese.append((m.start(), m.end()))
            out.append((m.start(), m.end(), tipo, et))
    return sorted(out)


def _parti(testo_n: str) -> list[tuple[int, str]]:
    """Parti di frase separate da «;» o da congiunzioni che cambiano argomento (posizione iniziale, testo)."""
    out, pos = [], 0
    for seg in re.split(r"(;|\.\s|, mentre |, con l'uso |, tra le applicazioni |, e tra )", testo_n):
        out.append((pos, seg)); pos += len(seg)
    return out


def controlla_frase(testo: str, citati: list[dict], tutti: list[dict], tag: str) -> list[str]:
    problemi = []
    tn = norm(testo)
    idx = indice(tutti)
    if not idx and not any(f.get("tipo") == "manuale" for f in citati):
        return problemi
    ment = _menzioni(tn, idx)
    # E1: tipo dell'entità rispetto all'ultima parola-indicatore della stessa parte di frase
    for p0, seg in _parti(tn):
        p1 = p0 + len(seg)
        ind = []
        for r, tipo in INDICATORI:
            for m in re.finditer(r, seg):
                if not any(a <= p0 + m.start() < b for a, b, _t, _e in ment):     # parola dentro un nome (es. «Altra applicazione»)
                    ind.append((p0 + m.start(), tipo))
        ind.sort()
        for a, b, tipo, et in ment:
            if not p0 <= a < p1:
                continue
            prec = [t for pos, t in ind if pos < a]
            if prec and prec[-1] != tipo:
                problemi.append(f"{tag}: «{et}» è {NOMI_TIPO[tipo]}, non {NOMI_TIPO[prec[-1]]} (tipo di entità)")
    # E2: minuti subito dopo l'entità
    ent = entita_dai_fatti(citati)
    for k, (a, b, tipo, et) in enumerate(ment):
        fine = ment[k + 1][0] if k + 1 < len(ment) else len(tn)
        m = RE_MIN.match(tn[b:min(fine, b + 45)])
        if not m:
            continue
        n = int(m.group(1))
        validi = {mm for e, mm, _i in ent[tipo] if e == et}
        if validi and n not in validi:
            problemi.append(f"{tag}: «{n} minuti» attribuiti a «{et}», che nei fatti citati ha "
                            + " o ".join(f"{x} minuti" for x in sorted(validi)) + " (abbinamento numero↔entità)")
    for a, b, tipo, et in ment:
        m = RE_MIN_PRIMA.search(tn[max(0, a - 60):a])
        if not m:
            continue
        n = int(m.group(1))
        validi = {mm for e, mm, _i in ent[tipo] if e == et}
        if validi and n not in validi:
            problemi.append(f"{tag}: «{n} minuti» scritti prima di «{et}», che nei fatti citati ha "
                            + " o ".join(f"{x} minuti" for x in sorted(validi)) + " (abbinamento numero↔entità)")
    # E3: orari dopo un tipo di attività dichiarata
    dich = {}
    for f in citati:
        if f.get("tipo") == "manuale":
            m = re.search(r"\(([^)]+)\) dalle (\d\d:\d\d) alle (\d\d:\d\d)", f["testo"])
            if m:
                dich.setdefault(m.group(1), set()).add((m.group(2), m.group(3)))
    if dich:
        pos_cat = sorted((m.start(), cat) for cat, r in MANUALI.items() for m in re.finditer(r"(?<![a-zà-ù])" + r, tn))
        for k, (a, cat) in enumerate(pos_cat):
            fine = pos_cat[k + 1][0] if k + 1 < len(pos_cat) else len(tn)
            m = RE_INTERVALLO.search(tn, a, min(fine, a + 60))
            if not m or cat not in dich:
                continue
            g = [x for x in m.groups() if x is not None]
            iv = (f"{int(g[0]):02d}:{g[1]}", f"{int(g[2]):02d}:{g[3]}")
            if iv not in dich[cat]:
                problemi.append(f"{tag}: l'intervallo {iv[0]}–{iv[1]} è attribuito a «{cat}» ma nei fatti citati "
                                f"quella attività dichiarata ha orari diversi (abbinamento orari↔attività)")
    return problemi
