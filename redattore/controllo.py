"""Controllo anti-invenzione della sintesi (deterministico, nessuna AI).

Una sintesi è accettata solo se, frase per frase:
  1. struttura: da 3 a 6 frasi, ognuna con almeno un riferimento a fatti esistenti, lunghezza ragionevole;
  2. orari: ogni orario (08:30, 8.30) compare tra gli orari dei fatti citati da quella frase;
  3. numeri: ogni altro numero compare tra i numeri dei fatti citati (date comprese); i numeri scritti in lettere
     («due», «mezz'ora»…) sono ammessi solo se la stessa parola compare nei fatti citati;
  4. lessico: mai «produttività», «inattivo», «ozio» e simili; i termini valutativi («ottimo», «scarso»,
     «efficiente»…) solo se compaiono testualmente in un fatto citato (es. nella descrizione del dipendente);
  5. dichiarato: una frase che cita un'attività dichiarata deve dire «dichiarata/e»; una segnalazione «segnalato/a» o
     «dichiarato/a»; le osservazioni «osservazioni» o «dichiarato/a»; il totale combinato «dichiarate»;
  2b. intervalli: «dalle X alle Y» / «tra le X e le Y» / «X–Y» devono comparire entrambi nello stesso fatto citato;
  6. nessun fatto esterno: nomi di applicazioni, siti, categorie, tipi di attività, giorni e mesi citati nella frase
     devono comparire nei fatti citati.
Rafforzamenti M6:
  7. al massimo MAX_FATTI_FRASE fatti citati per frase (citare tutto renderebbe il controllo inutile);
  8. abbinamento quantità↔unità: «255 minuti», «3 ore», «5 messaggi» devono comparire con la stessa unità in un fatto
     citato (non basta che il numero compaia altrove);
  9. abbinamento rilevato/dichiarato: in una parte di frase che parla di attività «rilevata» ogni orario e quantità deve
     venire da un fatto (o parte di fatto) automatico; in una parte che parla di attività «dichiarata»/segnalata da un
     fatto dichiarato (i totali combinati sono divisi nelle loro parti);
 10. conteggi: «2 segnalazioni», «tre attività dichiarate», «una segnalazione» devono corrispondere al numero di fatti
     di quel tipo.
Rafforzamenti M7 (redattore/entita.py): 11. tipo di entità (un'applicazione non presentata come categoria e viceversa);
 12. abbinamento minuti↔entità e orari↔attività dichiarata.
Rafforzamenti della revisione indipendente:
 13. nessun carattere invisibile (formato Unicode, es. spazio a larghezza zero, trattino morbido) né lettere non latine
     (omografi): aggirano le liste di parole vietate;
 14. numeri in lettere anche composti («trentacinque», «diciotto», «duecento») e «mezzogiorno/mezzanotte/all'una»;
 15. orari senza minuti («alle 17», «ore 9»): l'ora deve comparire in un orario dei fatti citati;
 16. nomi propri (parola con l'iniziale maiuscola a metà frase: applicazioni, siti, categorie, persone) devono comparire
     nei fatti citati: le liste fisse (ATTIVITA, PAROLE_MAPPA) non conoscono i nomi inventati («Photoshop»);
 17. un numero seguito da un nome che non è tra le unità note («255 documenti») deve comparire con lo stesso nome nei fatti.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata

from . import entita

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RE_ORA = re.compile(r"(?<![\d:.,])([01]?\d|2[0-4])\s?[:.]\s?([0-5]\d)(?![\d:.,]*\d)")
RE_NUM = re.compile(r"(?<![\w])\d+(?:[.,]\d+)*")
NUMERI_LETTERE = ["zero", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove", "dieci", "undici",
                  "dodici", "tredici", "quattordici", "quindici", "sedici", "venti", "trenta", "quaranta",
                  "quarantacinque", "cinquanta", "sessanta", "settanta", "ottanta", "novanta", "cento", "mille",
                  "mezzogiorno", "mezzanotte", "all'una", "mezz'ora", "mezzora", "mezza", "mezzo", "metà", "un'ora", "una ora", "un ora", "un quarto",
                  "un paio", "una decina", "una ventina", "una trentina", "qualche", "alcune", "alcuni", "diversi", "diverse",
                  "numerosi", "numerose", "vari", "varie", "doppio", "triplo", "dozzina", "paio",
                  "primo pomeriggio", "tarda mattinata"]
VIETATI_ASSOLUTI = ["produttiv", "improduttiv", "inattiv", "inoperos", "ozio", "ozios", "pigr", "fannull",
                    "perditempo", "scansafatic", "assenteis", "nullafacen", "sfaticat", "svogliat", "lavativ"]
VALUTATIVI = ["ottim", "eccellent", "buon", "brav", "scars", "insufficient", "sufficient", "efficien", "rendiment",
              "diligen", "negligen", "proficu", "lodevol", "encomiabil", "positiv", "negativ", "impegnat", "impegno",
              "intens", "solerte", "zelo", "puntual", "ritard", "assenz", "assente", "distrazion", "svago",
              "non lavorativ", "personal", "privat", "molt", "poco", "pochi", "poche", "notevol", "significativ",
              "considerevol", "elevat", "ridott", "regolar", "costant", "continuativ", "proficuo", "performance",
              "prestazion", "merit", "demerit", "giudizi", "valutat", "soddisfacent", "carent", "lent", "veloc", "rapid"]
ATTIVITA = ["riunion", "telefon", "chiamat", "videochiamat", "videoconferenz", "incontr", "sopralluog", "cartace",
            "formazion", "webinar", "corso", "sportell", "cantier", "pranzo", "pausa pranzo", "protocoll", "pec",
            "teams", "zoom", "meet", "webmail", "smart working", "telelavoro", "trasferta", "ferie", "permesso",
            "malattia", "straordinari", "contribuent", "cittadin", "utent", "pratica", "pratiche", "delibera",
            "determina", "verbale", "relazione", "progett", "assistenza", "archivi", "scansion", "stampa", "fattur",
            "ticket", "halley", "word", "excel", "outlook", "powerpoint", "browser", "pdf", "libreoffice", "posta",
            "mail", "messaggi", "siti", "sito", "portal", "gestional", "agenzia", "entrate", "ufficio", "office",
            "navigazion", "applicazion", "segnalazion", "osservazion", "sospes", "pausa", "bloccat", "disconness",
            "spento", "spenta", "chiusa", "chiuso", "sessione"]
DICHIARATO = {"manuale": ("dichiarat",), "totale_complessivo": ("dichiarat",),
              "segnalazione": ("segnalat", "segnalazion", "dichiarat"),
              "osservazioni": ("osservazion", "dichiarat")}
PAROLE_INTERE = {"posta", "pec", "meet", "zoom", "teams", "word", "pdf", "sito", "siti", "mail", "office", "corso",
                 "sera", "notte", "ieri", "domani", "spento", "spenta", "chiusa", "chiuso", "pausa", "stampa", "sessione"}
GENERE = {"chiusa", "chiuso", "spento", "spenta"}
GIORNI_MESI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica", "gennaio", "febbraio",
               "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre",
               "dicembre", "mattin", "pomeriggio", "sera", "notte", "ieri", "domani"]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s.lower()).replace("’", "'").replace("`", "'")
    return " ".join(s.split())


def _parole_mappa() -> list[str]:
    """Etichette di applicazioni, siti e categorie della mappatura CED (parole distintive, ≥ 4 lettere)."""
    try:
        with open(os.path.join(RADICE, "config", "applicazioni.json"), encoding="utf-8") as f:
            m = json.load(f)
    except OSError:
        return []
    comuni = {"della", "delle", "degli", "dello", "dell'", "microsoft", "servizi", "servizio", "online", "comune",
              "nazionale", "pubblica", "amministrazione", "strumenti", "sistema", "sistemi", "portale", "regione",
              "emilia", "romagna", "ministero", "italia", "italiana", "generale", "altra", "dati", "area", "uso", "giorno",
              "accesso", "blocco", "alto", "enti", "carta", "codice", "digitale", "diretta", "funzione", "desktop",
              "cloud", "console", "able", "goto", "forms", "banca", "elettronica", "postazione"}
    out = set()
    et = [v["etichetta"] for v in m.get("applicazioni", {}).values()] + [v["etichetta"] for v in m.get("siti", {}).values()]
    et += list(m.get("categorie", {}).values())
    for e in et:
        for w in re.findall(r"[a-zà-ù]{4,}", _norm(e)):
            if w not in comuni:
                out.add(w[:-1] if len(w) > 5 and w[-1] in "aeiou" else w)
    generiche = {"regis", "registr", "line", "local", "note", "self", "sole", "unica", "unico", "comunal", "tecnic",
                 "informatic", "informativ", "uffici", "firma", "modul", "catalog", "certificat", "dichiarazion",
                 "segnalazion", "virtual", "updat", "remot", "traffic"}
    return sorted(out - generiche)


PAROLE_MAPPA = _parole_mappa()


def orari(testo: str) -> set[str]:
    return {f"{int(h):02d}:{m}" for h, m in RE_ORA.findall(testo)}


def numeri(testo: str) -> set[str]:
    t = RE_ORA.sub(" ", testo)
    out = set()
    for x in RE_NUM.findall(t):
        x = x.rstrip(".,")
        out.add(x.lstrip("0") or "0")
    return out


def _contiene(testo_n: str, termine: str) -> bool:
    return re.search(r"(?<![a-zà-ù])" + re.escape(termine), testo_n) is not None


_T = r"([01]?\d|2[0-4])\s?[:.]\s?([0-5]\d)"
RE_COPPIE = [re.compile(r"\bdalle\s+" + _T + r"\s+alle\s+" + _T), re.compile(r"\btra\s+le\s+" + _T + r"\s+e\s+le\s+" + _T),
             re.compile(r"\bdal(?:le)?\s+" + _T + r"\s+al(?:le)?\s+" + _T), re.compile(_T + r"\s?[–—-]\s?" + _T)]


def coppie(testo: str) -> set[tuple[str, str]]:
    """Intervalli orari citati («dalle 11:00 alle 11:45», «tra le 08:00 e le 13:30», «10:30–10:45»)."""
    out = set()
    for r in RE_COPPIE:
        for h1, m1, h2, m2 in r.findall(testo):
            out.add((f"{int(h1):02d}:{m1}", f"{int(h2):02d}:{m2}"))
    return out


_U = r"(?:uno|un|due|tre|tré|quattro|cinque|sei|sette|otto|nove)"
_TEEN = r"(?:dieci|undici|dodici|tredici|quattordici|quindici|sedici|diciassette|diciotto|diciannove)"
_DEC = r"(?:vent|trent|quarant|cinquant|sessant|settant|ottant|novant)(?:i|a)?"
RE_NUMERO_PAROLA = re.compile(rf"(?:(?:mille|{_U}mila))?(?:{_U}?cento)?(?:{_TEEN}|{_DEC}{_U}?|{_U})?")
PAROLE_NUMERO_AMBIGUE = {"un", "uno", "una"}
RE_ORA_BREVE = re.compile(r"(?<![\w:.,])(?:alle|dalle|fino alle|entro le|verso le|intorno alle|dopo le|prima delle|tra le|e le|ore|h)"
                          r"\s+(?:ore\s+)?([01]?\d|2[0-4])(?![\d:.,]*\d|\s*(?:minut|or[ae]|fasc|messagg|volt|giorn|paus|segnalaz|attivit|%))")
RE_NOME_PROPRIO = re.compile(r"[A-ZÀ-Ý][\wÀ-ÿ&+-]*")
NOMI_PROPRI_AMMESSI = {"pc"}
STOP_NUMERO_NOME = {"di", "e", "a", "in", "per", "su", "da", "con", "la", "il", "lo", "i", "le", "gli", "un", "una", "del", "della",
                    "dei", "delle", "al", "alla", "alle", "ai", "circa", "tra", "fra", "o", "ma", "che", "non", "ha", "è", "sono",
                    "dalle", "dal", "nel", "nella", "nelle", "nei", "come", "se", "ore", "ora", "dell", "all", "nell", "sull", "dall",
                    "quest", "quell"}      # elisioni: «2026 l'attività» → «2026», «l», «attività»


def _ripulisci(testo: str) -> str:
    """NFKC e senza caratteri di formato Unicode (spazio a larghezza zero, trattino morbido, …)."""
    return "".join(c for c in unicodedata.normalize("NFKC", testo) if unicodedata.category(c) != "Cf")


def caratteri_sospetti(testo: str) -> list[str]:
    """Caratteri invisibili e lettere non latine (omografi cirillici/greci) presenti nel testo."""
    out = {f"U+{ord(c):04X}" for c in testo if unicodedata.category(c) == "Cf"}
    out |= {f"U+{ord(c):04X}" for c in testo if c.isalpha() and "LATIN" not in unicodedata.name(c, "LATIN")}
    return sorted(out)


def numeri_in_lettere(testo_n: str) -> list[str]:
    """Parole che sono un numero scritto in lettere, anche composto («trentacinque», «duecentodieci»)."""
    return [w for w in re.findall(r"[a-zà-ù]+", testo_n)
            if w not in PAROLE_NUMERO_AMBIGUE and len(w) >= 3 and RE_NUMERO_PAROLA.fullmatch(w)]


def ore_senza_minuti(testo: str) -> list[int]:
    """Ore citate senza minuti («alle 17», «ore 9»)."""
    return [int(m.group(1)) for m in RE_ORA_BREVE.finditer(_norm(RE_CITAZIONE.sub(" ", testo)))]


def nomi_propri(testo: str) -> list[str]:
    """Parole con l'iniziale maiuscola a metà frase (fuori dalle citazioni tra virgolette)."""
    t = RE_CITAZIONE.sub(" ", testo)
    out = []
    for m in RE_NOME_PROPRIO.finditer(t):
        prima = t[:m.start()].rstrip(" 	\"'«»“”(-–—")
        if not prima or prima[-1] in ".!?:;":
            continue                                       # inizio di frase
        out.append(m.group(0))
    return out


def numeri_con_nome(testo_n: str) -> list[tuple[str, str]]:
    """(numero, parola successiva) per i numeri seguiti da una parola che non è una stop word (orari esclusi)."""
    toks = RE_TOK.findall(RE_ORA.sub(" ", testo_n))
    return [(x.lstrip("0") or "0", toks[i + 1]) for i, x in enumerate(toks[:-1])
            if x[0].isdigit() and not toks[i + 1][0].isdigit() and len(toks[i + 1]) > 2
            and toks[i + 1] not in STOP_NUMERO_NOME]


MAX_FATTI_FRASE = 4
UNITA = [("minut", "minut"), ("ore", "or"), ("ora", "or"), ("messagg", "messagg"), ("ricevut", "ricevut"),
         ("inviat", "inviat"), ("rispost", "rispost"), ("lett", "lett"), ("fasc", "fasc"),
         ("segnalazion", "segnalazion"), ("attivit", "attivit"), ("sospension", "sospension"), ("paus", "paus")]
RE_TOK = re.compile(r"\d+(?:[.,]\d+)*|[a-zà-ù]+")
RE_AUTO = re.compile(r"(?<![a-zà-ù])rilev")
RE_DICH = re.compile(r"dichiar|segnal|osservazion")
RE_SEGMENTI = re.compile(r",\s+|;\s+|:\s+|\s+(?:ma|mentre)\s+|\s+e\s+(?=(?:il dipendente|risult|si rilev|è stat|sono stat))")
RE_CITAZIONE = re.compile(r"(?:(?<=\s)|(?<=^)|(?<=[:(]))'[^']{2,}'(?![a-zà-ù])|\"[^\"]*\"|«[^»]*»")
NUM_LETTERE_VAL = {"una": 1, "un": 1, "uno": 1, "un'": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5, "sei": 6,
                   "sette": 7, "otto": 8, "nove": 9, "dieci": 10}
RE_CONTEGGIO = re.compile(r"(?<![\w'])(\d+|una|uno|un'|un|due|tre|quattro|cinque|sei|sette|otto|nove|dieci)\s*"
                          r"(segnalazion[ei]|attività dichiarat[ae]|sospension[ei]|pausa|pause)(?![a-zà-ù])")

# «il dipendente ha dichiarato due attività: …» (conteggio prima del nome)
RE_CONTEGGIO_DICH = re.compile(r"dichiarat\w*\s+(\d+|due|tre|quattro|cinque|sei|sette|otto|nove|dieci)\s+attività(?![a-zà-ù])")


def _unita(tok: str) -> str | None:
    if tok in ("ore", "ora"):
        return "or"
    for stem, u in UNITA:
        if stem not in ("ore", "ora") and tok.startswith(stem):
            return u
    return None


def quantita(testo_n: str) -> list[tuple[str, str]]:
    """Coppie (numero, unità) nel testo normalizzato: «255 minuti» → ("255", "minut") (unità subito dopo il numero)."""
    t = RE_ORA.sub(" ", testo_n)
    toks = RE_TOK.findall(t)
    out = []
    for i, x in enumerate(toks[:-1]):
        if x[0].isdigit():
            u = _unita(toks[i + 1])
            if u:
                out.append((x.lstrip("0") or "0", u))
    return out


def _quantita_fatto(testo_n: str) -> set[tuple[str, str]]:
    """Nel fatto ogni numero vale con tutte le unità consecutive che lo seguono («3 messaggi inviati»)."""
    t = RE_ORA.sub(" ", testo_n)
    toks = RE_TOK.findall(t)
    out = set()
    for i, x in enumerate(toks):
        if x[0].isdigit():
            for y in toks[i + 1:i + 4]:          # unità consecutive: «3 messaggi inviati»
                u = _unita(y)
                if not u:
                    break
                out.add((x.lstrip("0") or "0", u))
    return out


def _numeri_con_nome_fatti(base_n: str) -> list[tuple[str, str]]:
    """Come numeri_con_nome ma sui fatti: ogni numero vale con le parole che lo seguono entro tre posizioni."""
    toks = RE_TOK.findall(RE_ORA.sub(" ", base_n))
    out = []
    for i, x in enumerate(toks):
        if x[0].isdigit():
            out += [(x.lstrip("0") or "0", y) for y in toks[i + 1:i + 4] if not y[0].isdigit()]
    return out


def _etichetta(seg_n: str) -> str | None:
    a, d = bool(RE_AUTO.search(seg_n)), bool(RE_DICH.search(seg_n))
    return "auto" if a and not d else "dich" if d and not a else "misto" if a and d else None


def parti_fatto(f: dict) -> list[tuple[str, str]]:
    """Il fatto diviso in parti con la loro origine (il totale combinato: parte dichiarata + parte complessiva)."""
    out = []
    for parte in f["testo"].split(";"):
        e = _etichetta(_norm(parte))
        orig = f["origine"]
        if orig == "osservazione":
            orig = "dichiarato"  # attribuzione degli orari umani, mantenendo distinta la provenienza del fatto
        if f["origine"] == "combinato":
            orig = "dichiarato" if e == "dich" else "automatico" if e == "auto" else "combinato"
        out.append((_norm(parte), orig))
    return out


def segmenti(testo_n: str) -> list[tuple[str, str | None]]:
    """Parti della frase con l'etichetta rilevato/dichiarato (una parte senza etichetta eredita la precedente)."""
    out, prec = [], None
    for seg in RE_SEGMENTI.split(testo_n):
        if not seg.strip():
            continue
        e = _etichetta(RE_CITAZIONE.sub(" ", seg))
        if e is None:
            e = prec
        out.append((seg, e)); prec = e
    return out


def _conteggi_fatti(fatti: list[dict]) -> dict[str, int]:
    pause = sum(1 for f in fatti if f["tipo"] == "pausa" and f["testo"].startswith("Raccolta dei dati sospesa"))
    for f in fatti:
        m = re.match(r"Altre (\d+) sospensioni", f["testo"]) if f["tipo"] == "pausa" else None
        if m:
            pause += int(m.group(1))
    return {"segnalazion": sum(1 for f in fatti if f["tipo"] == "segnalazione"),
            "attività dichiarat": sum(1 for f in fatti if f["tipo"] == "manuale"), "sospension": pause, "paus": pause}


def _parola(testo_n: str, w: str) -> bool:
    return re.search(r"(?<![a-zà-ù'])" + re.escape(w) + r"(?![a-zà-ù])", testo_n) is not None


def controlla(frasi: list[dict], fatti: list[dict], min_frasi: int = 3, max_frasi: int = 6,
              max_fatti: int | None = MAX_FATTI_FRASE, testo_dipendente: bool = False) -> dict:
    """Restituisce {"esito": "superato"|"non_superato", "problemi": [...] } (problemi con la frase di riferimento).
    testo_dipendente=True: testo modificato dal dipendente (dichiarato), confrontato con tutti i fatti; non serve dire
    «dichiarato» a ogni frase perché l'intera sintesi è già marcata come dichiarata."""
    per_id = {f["id"]: f for f in fatti}
    conteggi = _conteggi_fatti(fatti)
    # nomi di categorie/applicazioni/siti che contengono parole come «segnalazioni» o «rilevazioni» (es. «Assistenza
    # e segnalazioni»): per l'etichetta rilevato/dichiarato della parte di frase valgono come nomi, non come parole
    nomi_ambigui = sorted({e for voci in entita.entita_dai_fatti(fatti).values() for e, _, _ in voci
                           if RE_DICH.search(e) or RE_AUTO.search(e)}, key=len, reverse=True)
    problemi: list[str] = []
    if not isinstance(frasi, list) or not min_frasi <= len(frasi) <= max_frasi:
        problemi.append(f"servono da {min_frasi} a {max_frasi} frasi (trovate {len(frasi) if isinstance(frasi, list) else 0})")
    for i, fr in enumerate(frasi if isinstance(frasi, list) else [], 1):
        testo = (fr.get("testo") or "").strip() if isinstance(fr, dict) else ""
        ids = fr.get("fatti") if isinstance(fr, dict) else None
        tag = f"frase {i}"
        if not testo:
            problemi.append(f"{tag}: vuota"); continue
        sospetti = caratteri_sospetti(unicodedata.normalize("NFKC", testo))
        if sospetti:
            problemi.append(f"{tag}: caratteri invisibili o non latini nel testo {sospetti[:4]}")
        testo = _ripulisci(testo)
        if not testo.endswith((".", ".)", ".»", ".\"")):
            problemi.append(f"{tag}: frase incompleta (non termina con il punto)")
        if re.search(r"\bdipendente\s+(?:ha|abbia|aveva)\s+(?:registrat|svolt|lavorat|effettuat|compiut|eseguit|utilizzat|usat)",
                     _norm(testo)) and "dichiarat" not in _norm(testo):
            problemi.append(f"{tag}: attribuisce al dipendente un dato rilevato dalla postazione")
        if len(testo) > 400:
            problemi.append(f"{tag}: troppo lunga ({len(testo)} caratteri)")
        if not isinstance(ids, list) or not ids:
            problemi.append(f"{tag}: nessun fatto citato"); continue
        sconosciuti = [x for x in ids if x not in per_id]
        if sconosciuti:
            problemi.append(f"{tag}: fatti inesistenti {sconosciuti}"); continue
        if max_fatti and len(set(ids)) > max_fatti:
            problemi.append(f"{tag}: cita {len(set(ids))} fatti (massimo {max_fatti}): citare solo i fatti usati")
        citati = [per_id[x] for x in ids]
        base = " ".join(f["testo"] for f in citati)
        base_n, testo_n = _norm(base), _norm(testo)
        # 10. conteggi («2 segnalazioni», «una segnalazione»): i numeri di conteggio corretti sono ammessi
        conteggi_ok: set[str] = set()
        trovati = RE_CONTEGGIO.findall(testo_n) + [(n, "attività dichiarat") for n in RE_CONTEGGIO_DICH.findall(testo_n)]
        for num, nome in trovati:
            chiave = next(k for k in conteggi if nome.startswith(k))
            val = int(num) if num.isdigit() else NUM_LETTERE_VAL[num]
            vero = conteggi[chiave]
            singolare = num in ("una", "uno", "un'", "un")
            citati_tipo = sum(1 for f in citati if (chiave == "segnalazion" and f["tipo"] == "segnalazione")
                              or (chiave == "attività dichiarat" and f["tipo"] == "manuale")
                              or (chiave in ("sospension", "paus") and f["tipo"] == "pausa"))
            if singolare:
                if vero >= 2 and citati_tipo >= 2:
                    problemi.append(f"{tag}: conteggio errato: «{num} {nome}» ma i fatti citati ne riportano {citati_tipo}")
            elif val != vero:
                problemi.append(f"{tag}: conteggio errato: «{num} {nome}» ma nei fatti ne risultano {vero}")
            else:
                conteggi_ok.add(num)
        # 8./9. abbinamento quantità↔unità e rilevato/dichiarato
        parti = [p for f in citati for p in parti_fatto(f)]
        ammessi = {"auto": ("automatico", "combinato"), "dich": ("dichiarato", "combinato")}
        testo_seg = testo_n
        for nome in nomi_ambigui:
            testo_seg = re.sub(r"(?<![a-zà-ù])" + re.escape(nome) + r"(?![a-zà-ù])", "voce", testo_seg)
        for seg, et in segmenti(testo_seg):
            seg_q = RE_CITAZIONE.sub(" ", seg)
            fonti = [p for p, o in parti if et not in ammessi or o in ammessi[et]]
            for q in quantita(seg_q):
                if q[0] in conteggi_ok and q[1] in ("segnalazion", "attivit", "sospension", "paus"):
                    continue
                if q[0] not in numeri(base):
                    continue                                   # già segnalato come numero non presente
                if not any(q in _quantita_fatto(p) for p, o in parti):
                    problemi.append(f"{tag}: «{q[0]} {q[1]}…» non compare con questa unità nei fatti citati {ids}")
                elif not any(q in _quantita_fatto(p) for p in fonti):
                    problemi.append(f"{tag}: «{q[0]} {q[1]}…» viene da un dato "
                                    + ("dichiarato ma è attribuito all'attività rilevata" if et == "auto"
                                       else "rilevato ma è attribuito al dipendente (dichiarato)"))
            if et in ammessi:
                for o in sorted(orari(seg_q) & orari(base)):
                    if not any(o in orari(p) for p in fonti):
                        problemi.append(f"{tag}: orario {o} viene da un dato "
                                        + ("dichiarato ma è attribuito all'attività rilevata" if et == "auto"
                                           else "rilevato ma è attribuito al dipendente (dichiarato)"))
        for o in sorted(orari(testo) - orari(base)):
            problemi.append(f"{tag}: orario {o} non presente nei fatti citati {ids}")
        for a, b in sorted(coppie(testo)):
            if not any({a, b} <= orari(f["testo"]) for f in citati):
                problemi.append(f"{tag}: l'intervallo {a}–{b} non compare in un unico fatto citato (orari di fatti diversi)")
        for n in sorted(numeri(testo) - numeri(base) - conteggi_ok, key=lambda x: (len(x), x)):
            problemi.append(f"{tag}: numero {n} non presente nei fatti citati {ids}")
        for w in NUMERI_LETTERE:
            if w in conteggi_ok:
                continue
            if _parola(testo_n, w) and not _parola(base_n, w):
                problemi.append(f"{tag}: numero in lettere «{w}» (usare le cifre dei fatti)")
        for w in numeri_in_lettere(testo_n):
            if w not in conteggi_ok and not _parola(base_n, w):
                problemi.append(f"{tag}: numero in lettere «{w}» (usare le cifre dei fatti)")
        orari_base = {o[:2] for o in orari(base)}
        for h in ore_senza_minuti(testo):
            if f"{h:02d}" not in orari_base and not (h == 24 and "00" in orari_base):
                problemi.append(f"{tag}: ora «{h}» senza minuti non corrisponde a nessun orario dei fatti citati {ids}")
        for nome in nomi_propri(testo):
            if nome.lower() in NOMI_PROPRI_AMMESSI or nome.lower() in GIORNI_MESI:
                continue
            if not _contiene(base_n, _norm(nome)):
                problemi.append(f"{tag}: nome «{nome}» non compare nei fatti citati {ids}")
        for num, nome in numeri_con_nome(RE_CITAZIONE.sub(" ", testo_n)):
            if (num, nome[:5]) in {(n, y[:5]) for n, y in _numeri_con_nome_fatti(base_n)} or num in conteggi_ok:
                continue
            if _unita(nome) or num not in numeri(base):
                continue                                       # unità note: regole 8/9; numero assente: già segnalato
            problemi.append(f"{tag}: «{num} {nome}…» il numero compare nei fatti citati ma non con questo nome")
        for w in VIETATI_ASSOLUTI:
            if _contiene(testo_n, w):
                problemi.append(f"{tag}: termine vietato «{w}…»")
        for w in VALUTATIVI:
            if _contiene(testo_n, w) and not _contiene(base_n, w):
                problemi.append(f"{tag}: termine valutativo «{w}…» non presente nei fatti citati")
        for w in ATTIVITA + PAROLE_MAPPA + GIORNI_MESI:
            trova = _parola if w in PAROLE_INTERE else _contiene
            radice = w[:-1] if w in GENERE else w           # «PC chiuso» / «sessione chiusa»: stessa parola
            if trova(testo_n, w) and not _contiene(base_n, radice):
                problemi.append(f"{tag}: «{w}» non compare nei fatti citati {ids}")
        for f in ([] if testo_dipendente else citati):
            req = DICHIARATO.get(f["tipo"])
            if req and not any(_contiene(testo_n, r) for r in req):
                problemi.append(f"{tag}: cita il fatto {f['id']} ({f['origine']}) senza dire che è "
                                + ("segnalato" if f["tipo"] == "segnalazione" else "dichiarato") + " dal dipendente")
        if not testo_dipendente and len({f["origine"] for f in citati if f["tipo"] != "giorno"}) > 1:
            problemi.append(f"{tag}: frase con provenienze diverse; separare rilevato, dichiarato e osservazioni")
        # M7: tipo di entità (app/categorie/siti) e abbinamento numero/orari ↔ entità
        problemi += entita.controlla_frase(testo, citati, fatti, tag)
        # un'attività dichiarata non può essere presentata come rilevata
        # (collaudo ALFA B8: «non rilevata» / «mai rilevata» non sono falsi positivi)
        testo_rilev = re.sub(r"\b(?:non|mai)\s+rilevat\w*", " ", testo_n)
        if (not testo_dipendente and any(f["origine"] == "dichiarato" for f in citati)
                and re.search(r"\brilevat", testo_rilev)
                and not any(f["origine"] != "dichiarato" for f in citati)):
            problemi.append(f"{tag}: attività dichiarata descritta come «rilevata»")
    # niente duplicati (stessi problemi ripetuti)
    visti, uniq = set(), []
    for p in problemi:
        if p not in visti:
            visti.add(p); uniq.append(p)
    return {"esito": "superato" if not uniq else "non_superato", "problemi": uniq}
