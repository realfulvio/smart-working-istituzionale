"""Generazione della «Sintesi della giornata»: fatti → modello locale → controllo → (secondo tentativo) → testo standard.

La sintesi e l'esito del controllo vanno nel JSON giornaliero nel campo «sintesi_ai» (schema giornaliero/3), fuori dal
sigillo tecnico e coperti dal sigillo finale. Il dipendente deve confermarla («Ho verificato la sintesi») prima del
sigillo finale e del PDF.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import re
import time

from . import VERSIONE_REDATTORE, controllo, fatti as mod_fatti
from .motore import ErroreMotore

SEME = 42
SISTEMA = """Sei il redattore del resoconto giornaliero del lavoro agile di un dipendente comunale.
Scrivi la «Sintesi della giornata» in italiano formale e impersonale, in terza persona («il dipendente», «risultano»).
Regole obbligatorie:
1. Usa solo i fatti dell'elenco. Non aggiungere informazioni, ipotesi, cause, commenti o giudizi.
2. Copia ogni orario e ogni numero esattamente come compare nei fatti che citi, in cifre. Non fare calcoli, somme o percentuali.
3. Descrivi soltanto segnali tecnici senza valutare la persona o dedurre quanto abbia lavorato.
   Un periodo senza attività informatica rilevata si descrive solo così: «nessuna attività informatica rilevata».
4. Le attività dichiarate dal dipendente vanno sempre chiamate «dichiarate» e tenute distinte da quelle rilevate dalla
   postazione. Le segnalazioni si chiamano «segnalazioni del dipendente»; le osservazioni «osservazioni del dipendente».
   Una frase può citare soltanto fatti della stessa provenienza: separa rilevato, dichiarato e osservazioni.
5. Scrivi da 3 a 5 frasi brevi (al massimo 30 parole ciascuna), che terminano con il punto. In «fatti» indica i numeri dei fatti usati nella frase (al massimo 4): ogni orario, numero e
   nome della frase deve comparire in quei fatti, con la stessa unità (minuti, ore).
6. I dati automatici sono «rilevati dalla postazione»: non scrivere che il dipendente li ha registrati.
7. Ordine: (a) giornata e orari dell'attività rilevata; (b) fasce rilevate e categorie o applicazioni;
   (c) attività dichiarate, se presenti; (d) pause o segnalazioni, se presenti.
8. Non citare il traffico di rete né nomi di persone.
9. Applicazioni, categorie e siti sono cose diverse: chiama «categorie» solo i nomi del fatto delle categorie e
   «applicazioni» solo i nomi del fatto delle applicazioni; non scrivere minuti, tempi o classifiche accanto ai nomi.
Non ricopiare i fatti uno per uno: riassumi i più importanti, unendo in una frase fatti collegati.
Per ogni attività dichiarata riporta solo la categoria, gli orari e i minuti scritti nel fatto, senza aggiungere scopi.
Le durate si scrivono come nei fatti («60 minuti (1 ora)»), mai «un'ora» o «mezz'ora».
Rispondi solo con il JSON richiesto: {"frasi": [{"testo": "...", "fatti": [1, 2]}]}"""


def schema_uscita(fatti: list[dict]) -> dict:
    ids = [f["id"] for f in fatti]
    return {"type": "object", "additionalProperties": False, "required": ["frasi"],
            "properties": {"frasi": {"type": "array", "minItems": 3, "maxItems": 5, "items": {
                "type": "object", "additionalProperties": False, "required": ["testo", "fatti"],
                "properties": {"testo": {"type": "string", "minLength": 20, "maxLength": 240},
                               "fatti": {"type": "array", "minItems": 1, "maxItems": controllo.MAX_FATTI_FRASE,
                                         "items": {"type": "integer", "enum": ids}}}}}}}


ESEMPIO_FATTI = """[1] (automatico) Giornata del resoconto: giovedì 1 gennaio 2026.
[2] (automatico) Attività informatica rilevata in 10 fasce da 15 minuti.
[3] (automatico) La prima fascia con attività informatica rilevata inizia alle 09:00; l'ultima termina alle 12:00.
[4] (automatico) Categorie di attività rilevate: Navigazione web, Strumenti d'ufficio.
[5] (dichiarato) Attività dichiarata dal dipendente (altra attività) dalle 14:00 alle 15:00, 60 minuti (1 ora): 'Esempio'."""
ESEMPIO_RISPOSTA = json.dumps({"frasi": [
    {"testo": "Nella giornata del 1 gennaio 2026 l'attività informatica rilevata dalla postazione si colloca tra le 09:00 e le 12:00, "
              "in 10 fasce da 15 minuti.", "fatti": [1, 2, 3]},
    {"testo": "Le categorie rilevate sono Navigazione web e Strumenti d'ufficio.", "fatti": [4]},
    {"testo": "Il dipendente ha inoltre dichiarato un'altra attività dalle 14:00 alle 15:00 (60 minuti).", "fatti": [5]}]}, ensure_ascii=False)


def messaggio_utente(fatti: list[dict], problemi: list[str] | None = None, precedente: str | None = None,
                     respinta: list[dict] | None = None) -> str:
    m = "Fatti della giornata (numerati):\n" + mod_fatti.elenco(fatti) + "\n\nScrivi la sintesi della giornata (3 o 4 frasi)."
    if precedente:      # «Riscrivi»: stessa richiesta, formulazione diversa (sempre temperatura 0, seme diverso)
        m += ("\n\nIl dipendente ha chiesto una nuova formulazione. Versione precedente, da non ripetere uguale:\n"
              + precedente + "\nScrivi una formulazione diversa con gli stessi fatti e le stesse regole.")
    if problemi and not respinta:          # come in M5 (risultati migliori nel banco M6)
        m += ("\n\nUna prima versione è stata respinta dal controllo automatico per questi motivi:\n"
              + "\n".join(f"- {p}" for p in problemi[:12])
              + "\nRiscrivi la sintesi evitando questi errori. In caso di dubbio usa le stesse parole dei fatti.")
    elif problemi:          # variante provata in M6: il modello vede la propria versione respinta, frase per frase
        m += ("\n\nVersione respinta dal controllo automatico:\n"
              + "\n".join(f"frase {i}: {f.get('testo', '')} (fatti {f.get('fatti', [])})"
                           for i, f in enumerate(respinta[:6], 1)))
        m += ("\n\nProblemi trovati dal controllo automatico:\n"
              + "\n".join(f"- {p}" for p in problemi[:12])
              + "\nRiscrivi tutta la sintesi: correggi le frasi con problemi usando le stesse parole e gli stessi numeri "
                "dei fatti, oppure togli la frase. Non fare somme né conteggi.")
    return m


def _leggi(testo: str) -> list[dict] | None:
    try:
        j = json.loads(testo)
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", testo or "", re.S)
        if not m:
            return None
        try:
            j = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    fr = j.get("frasi") if isinstance(j, dict) else None
    if not isinstance(fr, list):
        return None
    out = []
    for x in fr:
        if isinstance(x, dict):
            t = " ".join(str(x.get("testo", "")).split())
            ids = sorted({int(i) for i in x.get("fatti", []) if isinstance(i, int) or (isinstance(i, str) and i.isdigit())})
            out.append({"testo": t, "fatti": ids})
    return out


ESEMPIO = ("Fatti della giornata (numerati):\n" + ESEMPIO_FATTI + "\n\nScrivi la sintesi della giornata (3 o 4 frasi).",
           ESEMPIO_RISPOSTA)


# ------------------------------------------------------------------------------------------- testo standard
def testo_standard(fatti: list[dict]) -> list[dict]:
    """Sintesi a modello, deterministica, usata quando il modello non supera il controllo (o non è disponibile)."""
    per = {}
    for f in fatti:
        per.setdefault(f["tipo"], []).append(f)
    out = []
    g = per["giorno"][0]
    giorno = g["testo"].split(": ", 1)[1].rstrip(".")
    if "orari" in per:
        o = per["orari"][0]
        a, b = re.findall(r"\d{2}:\d{2}", o["testo"])[:2]
        out.append({"testo": f"Nella giornata di {giorno} la prima fascia con attività informatica rilevata inizia alle "
                             f"{a} e l'ultima termina alle {b}.", "fatti": [g["id"], o["id"]]})
        t = per["totale_rilevato"][0]
        out.append({"testo": "Risulta " + t["testo"][0].lower() + t["testo"][1:], "fatti": [t["id"]]})
    else:
        t = per["totale_rilevato"][0]
        out.append({"testo": f"Nella giornata di {giorno} non risultano fasce con attività informatica rilevata dalla "
                             "postazione.", "fatti": [g["id"], t["id"]]})
    if "categorie" in per:
        c = per["categorie"][0]
        out.append({"testo": "Le " + c["testo"][0].lower() + c["testo"][1:].replace(":", " sono:", 1),
                    "fatti": [c["id"]]})
    man = per.get("manuale", [])
    if man:
        voci = []
        for m in man:
            cat = re.search(r"\(([^)]+)\)", m["testo"]).group(1)
            a, b = re.findall(r"\d{2}:\d{2}", m["testo"])[:2]
            voci.append(f"{cat} dalle {a} alle {b}")
        for k in range(0, min(len(man), 8), 4):         # al massimo 4 fatti per frase
            out.append({"testo": ("Il dipendente ha dichiarato le seguenti attività non rilevabili dalla postazione: "
                                  if k == 0 else "Il dipendente ha inoltre dichiarato: ")
                        + "; ".join(voci[k:k + 4]) + ".", "fatti": [m["id"] for m in man][k:k + 4]})
    elif "nessuna_dichiarata" in per:
        out.append({"testo": "Non risultano attività dichiarate dal dipendente.", "fatti": [per["nessuna_dichiarata"][0]["id"]]})
    if "segnalazione" in per and len(out) < 6:
        out.append({"testo": "Sono presenti segnalazioni del dipendente su dati tecnici, riportate nel resoconto.",
                    "fatti": [s["id"] for s in per["segnalazione"]][:4]})
    for k in ("fonti", "sessione", "finestra", "pausa", "osservazioni"):   # B4: senza il fatto del tempo complessivo
        if len(out) < 3 and k in per:
            f = per[k][0]
            out.append({"testo": f["testo"], "fatti": [f["id"]]})
    return out[:6]


def _testo(frasi: list[dict]) -> str:
    return " ".join(f["testo"] if f["testo"].endswith(".") else f["testo"] + "." for f in frasi)


# ------------------------------------------------------------------------------------------------- genera
BUDGET_SECONDI = 60


def genera(doc: dict, motore=None, tentativi: int = 2, adesso: str | None = None, variante: int = 0,
           precedente: str | None = None, profilo: str | None = None,
           budget_secondi: float | None = BUDGET_SECONDI, mostra_respinta: bool = False) -> dict:
    """Restituisce il blocco «sintesi_ai». motore=None ⇒ solo testo standard (nessun modello).
    variante > 0: «Riscrivi» (seme SEME+variante e versione precedente da non ripetere).
    budget_secondi: il secondo tentativo si fa solo se, stimato con la durata del primo, resta nel budget; altrimenti
    testo standard subito (il dipendente non aspetta oltre ~1 minuto).
    mostra_respinta: nel secondo tentativo il modello rivede la propria versione respinta. Disattivato: nel banco M6
    peggiora i risultati (1.7B: 2 secondi tentativi riusciti su 8 contro 5 su 8 senza), il modello ripete gli errori."""
    fatti = mod_fatti.estrai(doc)
    schema = schema_uscita(fatti)
    prove, frasi, esito = [], None, "testo_standard"
    perf = {"secondi_totali": None, "secondi_caricamento": None, "secondi_generazione": None,
            "token_prompt": None, "token_generati": None, "ram_picco_mb": None}
    descr = {"tipo": "testo_standard", "modello": None, "runtime": None}
    t0 = time.monotonic()
    if motore is not None and variante:
        try:
            motore.seme = SEME + variante
        except AttributeError:
            pass
    if motore is not None:
        descr = {"tipo": motore.tipo, "modello": getattr(motore, "nome_modello", None) or getattr(motore, "modello", None),
                 "runtime": None}
        gen_s, tp, tg = 0.0, 0, 0
        try:
            with motore:
                descr = motore.descrizione()
                problemi, respinta = None, None
                for n in range(1, tentativi + 1):
                    trascorsi = max(time.monotonic() - t0, sum(p.get("secondi") or 0 for p in prove))
                    if n > 1 and budget_secondi and prove and prove[-1].get("secondi") and \
                            trascorsi + prove[-1]["secondi"] > budget_secondi:
                        perf["tentativo_saltato_per_tempo"] = True
                        break
                    raw, st = motore.genera(SISTEMA, messaggio_utente(fatti, problemi, precedente, respinta), schema,
                                            ESEMPIO)
                    gen_s += st["secondi"]; tp += st.get("token_prompt") or 0; tg += st.get("token_generati") or 0
                    cand = _leggi(raw)
                    ris = controllo.controlla(cand, fatti) if cand is not None else \
                        {"esito": "non_superato", "problemi": ["risposta non leggibile come JSON"]}
                    prove.append({"n": n, "esito": ris["esito"], "problemi": ris["problemi"],
                                  "frasi": cand if cand is not None else [], "secondi": st["secondi"],
                                  "token_generati": st.get("token_generati"), "secondi_prompt": st.get("secondi_prompt")})
                    if ris["esito"] == "superato":
                        frasi, esito = cand, "verificata_ai"
                        break
                    problemi, respinta = ris["problemi"], (cand if mostra_respinta else None)
        except ErroreMotore as e:
            prove.append({"n": len(prove) + 1, "esito": "errore_motore", "problemi": [str(e)], "frasi": [], "secondi": None})
        m = getattr(motore, "misure", {})
        perf.update({"secondi_caricamento": m.get("secondi_caricamento"), "secondi_generazione": round(gen_s, 2),
                     "token_prompt": tp or None, "token_generati": tg or None, "ram_picco_mb": m.get("picco_mb")})
        if m.get("picco_privato_mb") is not None:
            perf["ram_picco_privato_mb"] = m["picco_privato_mb"]
    if frasi is None:
        frasi = testo_standard(fatti)
    finale = controllo.controlla(frasi, fatti)
    if motore is not None:            # senza modello niente misure (il testo standard resta riproducibile byte per byte)
        perf["secondi_totali"] = round(time.monotonic() - t0, 2)
    descr.update({"temperatura": 0, "seme": SEME + variante, "profilo": profilo})
    return {"versione_redattore": VERSIONE_REDATTORE,
            "generata_il": adesso or dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "motore": descr, "fatti": fatti, "impronta_fatti": mod_fatti.impronta(fatti),
            "frasi": frasi, "testo": _testo(frasi), "esito": esito,
            "controllo": {"esito": finale["esito"], "problemi": finale["problemi"], "tentativi": prove},
            "prestazioni": perf, "riscritture": variante, "origine_testo": "ai" if esito == "verificata_ai" else "testo_standard",
            "verificata_dal_dipendente": False, "verificata_il": None}


def applica(doc: dict, sintesi: dict) -> dict:
    """Inserisce la sintesi nel JSON (annulla un eventuale sigillo finale precedente)."""
    if mod_fatti.impronta(mod_fatti.estrai(doc)) != sintesi["impronta_fatti"]:
        raise ValueError("la sintesi non corrisponde ai dati di questo JSON (fatti diversi)")
    out = copy.deepcopy(doc)
    out["sintesi_ai"] = sintesi      # origine: redatta dal modello (o testo standard) da fatti automatici e dichiarati
    out["integrita"] = dict(out.get("integrita") or {}, sigillo_finale=None)
    return out


def conferma(doc: dict, adesso: str | None = None) -> dict:
    """«Ho verificato la sintesi»: obbligatoria prima del sigillo finale."""
    s = doc.get("sintesi_ai")
    if not s:
        raise ValueError("nessuna sintesi da confermare")
    if mod_fatti.impronta(mod_fatti.estrai(doc)) != s["impronta_fatti"]:
        raise ValueError("i dati sono cambiati dopo la generazione della sintesi: rigenerarla")
    out = copy.deepcopy(doc)
    out["sintesi_ai"]["verificata_dal_dipendente"] = True
    out["sintesi_ai"]["verificata_il"] = adesso or dt.datetime.now().astimezone().isoformat(timespec="seconds")
    out["integrita"] = dict(out.get("integrita") or {}, sigillo_finale=None)
    return out


# ------------------------------------------------------------------------------------- Riscrivi / modifica
MAX_RISCRITTURE = 3


def riscrivi(doc: dict, motore=None, adesso: str | None = None, profilo: str | None = None) -> dict:
    """«Riscrivi»: nuova sintesi dagli stessi fatti, con lo stesso controllo; annulla la verifica e il sigillo finale.
    Restituisce il JSON aggiornato. Al massimo MAX_RISCRITTURE volte per giornata."""
    s = doc.get("sintesi_ai")
    if not s:
        raise ValueError("nessuna sintesi da riscrivere: usare prima «Genera resoconto»")
    n = int(s.get("riscritture") or 0) + 1
    if n > MAX_RISCRITTURE:
        raise ValueError(f"raggiunto il numero massimo di riscritture ({MAX_RISCRITTURE}): modificare il testo a mano")
    prec = s.get("testo_originale") or s.get("testo")
    nuova = genera(doc, motore, adesso=adesso, variante=n, precedente=prec, profilo=profilo)
    return applica(doc, nuova)


_RE_FRASE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ú«\"'])")


def dividi_frasi(testo: str) -> list[str]:
    t = " ".join((testo or "").split())
    return [x for x in _RE_FRASE.split(t) if x]


def controlla_modifica(testo: str, fatti: list[dict]) -> dict:
    """Controllo del testo modificato dal dipendente contro tutti i fatti della giornata (stesse regole su numeri,
    orari, abbinamenti, conteggi e lessico; nessun limite di fatti per frase)."""
    ids = [f["id"] for f in fatti]
    frasi = [{"testo": t, "fatti": ids} for t in dividi_frasi(testo)]
    r = controllo.controlla(frasi, fatti, min_frasi=1, max_frasi=8, max_fatti=None, testo_dipendente=True)
    return {"esito": r["esito"], "problemi": r["problemi"]}


def modifica(doc: dict, testo: str, adesso: str | None = None, accetta_avvisi: bool = False) -> dict:
    """Il dipendente modifica il testo della sintesi: il testo diventa «dichiarato» (origine_testo = dichiarata), viene
    ricontrollato; se il controllo trova problemi serve accetta_avvisi=True (conferma esplicita, gli avvisi restano nel
    JSON e nel PDF). Annulla la verifica («Ho verificato la sintesi» va ridata) e il sigillo finale."""
    s = doc.get("sintesi_ai")
    if not s:
        raise ValueError("nessuna sintesi da modificare")
    fatti = mod_fatti.estrai(doc)
    if mod_fatti.impronta(fatti) != s["impronta_fatti"]:
        raise ValueError("i dati sono cambiati dopo la generazione della sintesi: rigenerarla")
    testo = " ".join((testo or "").split())
    if not 20 <= len(testo) <= 3000:
        raise ValueError("il testo della sintesi deve avere tra 20 e 3000 caratteri")
    frasi_t = dividi_frasi(testo)
    if len(frasi_t) > 8:
        raise ValueError("il testo della sintesi può avere al massimo 8 frasi")
    r = controlla_modifica(testo, fatti)
    if r["esito"] != "superato" and not accetta_avvisi:
        raise AvvisiModifica(r["problemi"])
    out = copy.deepcopy(doc)
    so = out["sintesi_ai"]
    if so.get("origine_testo") != "dichiarata":          # conserva il testo generato (AI o standard) una volta sola
        so["testo_originale"] = so["testo"]
        so["frasi_originali"] = so["frasi"]
    so.update({"frasi": [{"testo": t, "fatti": []} for t in frasi_t], "testo": testo, "origine_testo": "dichiarata",
               "esito": "modificata_dal_dipendente",
               "controllo_modifica": {"esito": r["esito"], "problemi": r["problemi"],
                                      "accettata_con_avvisi": r["esito"] != "superato"},
               "modificata_il": adesso or dt.datetime.now().astimezone().isoformat(timespec="seconds"),
               "verificata_dal_dipendente": False, "verificata_il": None})
    out["integrita"] = dict(out.get("integrita") or {}, sigillo_finale=None)
    return out


class AvvisiModifica(ValueError):
    """Il testo modificato non supera il controllo: mostrare gli avvisi e chiedere conferma esplicita."""
    def __init__(self, problemi: list[str]):
        super().__init__("il testo modificato contiene dati non presenti nei fatti della giornata: "
                         + "; ".join(problemi[:6]))
        self.problemi = problemi
