"""Logica dell'applicazione, indipendente dall'interfaccia (testabile senza Tk).

Flusso della giornata (modalità «collector», predefinita dal 06/10/2026: processo di raccolta solo tra Avvia e
Chiudi, escluse le pause; «a consuntivo» resta selezionabile e non legge nulla):
  informativa (primo avvio) → Avvia giornata → [Pausa/Riprendi] → Chiudi giornata (stop della raccolta +
  aggregazione + sigillo tecnico) → Revisione (dati automatici in sola lettura; attività dichiarate, segnalazioni,
  osservazioni) → Genera resoconto (AI locale o testo standard) → [Riscrivi ≤ 3 | Modifica con avvisi] →
  «Ho verificato la sintesi» → Conferma (sigillo finale + PDF).

Il JSON tecnico del giorno (giorni/<g>.json, con sigillo tecnico) non viene mai modificato: il documento rivisto si
ricostruisce sempre da lì applicando la revisione salvata in revisione/<g>.json (stessa funzione apply_review
dell'aggregatore). La sintesi resta valida solo se i fatti non cambiano (impronta dei fatti).
"""
from __future__ import annotations

import copy
import datetime as dt
import glob
import json
import os
import sys
import time

from aggregatore import aggrega, sigillo
from aggregatore.modelli import CATEGORIE_MANUALI, CAMPI_SEGNALABILI, MAX_OSSERVAZIONI, Manuale, Segnalazione
from collector import giornata as cg
from collector.percorsi import Percorsi
from collector.stato import FUSO, Stato
from redattore import fatti as mod_fatti
from redattore import sintesi as mod_sintesi

MAX_DESCRIZIONE = 200
MAX_NOTA = 200
MAX_RISCRITTURE = mod_sintesi.MAX_RISCRITTURE
VERSIONE_INFORMATIVA = cg.VERSIONE_INFORMATIVA
RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ErroreApp(ValueError):
    """Errore da mostrare al dipendente così com'è (testo in italiano)."""


def _ora_locale() -> dt.datetime:
    return dt.datetime.now(FUSO())


def _scrivi(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)


def _leggi(path: str, predefinito=None):
    try:
        with open(path, encoding="utf-8-sig") as f:     # tollera il BOM (Set-Content -Encoding UTF8 di PS 5.1, Blocco note)
            return json.load(f)
    except (OSError, ValueError):
        return copy.deepcopy(predefinito)


def _profilo_pubblico(info):
    """La diagnostica runtime può contenere RAM e path: non propagarli al resoconto."""
    allowed = ("AI-LIGHT", "AI-STANDARD")
    out = {k: info[k] for k in ("profilo_richiesto", "profilo") if info.get(k) in allowed}
    out["motivo"] = info.get("messaggio") or ("Testo standard richiesto" if info.get("motivo") == "Testo standard richiesto"
                     else "Profilo AI locale disponibile" if out.get("profilo")
                     else "Testo standard: modello locale non disponibile o memoria insufficiente")
    return out


# --------------------------------------------------------------------------------------------- impostazioni
def cartella_documenti() -> str:
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:     # CSIDL_PERSONAL
                return buf.value
        except Exception:   # noqa: BLE001
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")


_EXE_LLAMA = "llama-server.exe" if sys.platform == "win32" else "llama-server"
# Modalità predefinita (Luca, 06/10/2026: «il programma è nato per quello»). Vale anche per valori non validi.
# Un «consuntivo» scritto esplicitamente in config/app.json o in <base>/impostazioni.json resta rispettato: nessun
# codice scrive quei file, quindi è una scelta deliberata del CED (vedi README, «Le due modalità»).
MODALITA_PREDEFINITA = "collector"


def _ai_accanto() -> str | None:
    """Eseguibile installato: cartella «ai» accanto al programma, se contiene llama-server (anche fuori da
    %LOCALAPPDATA%\\Programs, es. installazione con -Destinazione; collaudo ALFA3 N6)."""
    if not getattr(sys, "frozen", False):
        return None
    accanto = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "ai")
    return accanto if os.path.exists(os.path.join(accanto, "llama", _EXE_LLAMA)) else None


def impostazioni_predefinite(base: str) -> dict:
    """Valori predefiniti. Il CED può sovrascriverli con config/app.json accanto al programma; il dipendente non li
    vede. Cartella AI: llama-server e modelli copiati dall'installazione (origine: cartella del pacchetto,
    copia manuale); cache del prefisso in %LOCALAPPDATA%\\RendicontoSW\\cache_ai."""
    loc = os.environ.get("LOCALAPPDATA") or os.path.dirname(base)
    ai = _ai_accanto() or os.path.join(loc, "Programs", "RendicontoSW", "ai")
    exe = _EXE_LLAMA
    return {"modalita": MODALITA_PREDEFINITA, "server_ai": os.path.join(ai, "llama", exe), "modelli_ai": os.path.join(ai, "modelli"),
            "cache_ai": os.path.join(base, "cache_ai"), "thread_ai": 4, "profilo_ai": None,
            "cartella_pdf": os.path.join(cartella_documenti(), "Rendiconti lavoro agile"),
            "profili_siti": [], "estensione_browser": False, "filigrana_pdf": None}


def carica_impostazioni(base: str, file_ced: str | None = None) -> dict:
    imp = impostazioni_predefinite(base)
    file_ced = file_ced or os.environ.get("RSW_CONFIG_APP") or os.path.join(RADICE, "config", "app.json")
    for src in (file_ced, os.path.join(base, "impostazioni.json")):
        d = _leggi(src, {})
        if isinstance(d, dict):
            imp.update({k: os.path.expandvars(v) if isinstance(v, str) else v
                        for k, v in d.items() if k in imp})
    if imp["modalita"] not in ("consuntivo", "collector"):
        imp["modalita"] = MODALITA_PREDEFINITA
    # N6: config/app.json del pacchetto indica %LOCALAPPDATA%\\Programs\\RendicontoSW\\ai; se lì non c'è ma
    # l'assistente è accanto all'eseguibile installato (altra -Destinazione), si usa quello
    acc = _ai_accanto()
    standard = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.dirname(base), "Programs", "RendicontoSW", "ai")
    usa_standard = os.path.normcase(imp["server_ai"]) == os.path.normcase(os.path.join(standard, "llama", _EXE_LLAMA))
    if acc and (usa_standard or not os.path.exists(imp["server_ai"])):
        imp["server_ai"] = os.path.join(acc, "llama", _EXE_LLAMA)
        if usa_standard or not os.path.isdir(imp["modelli_ai"]):
            imp["modelli_ai"] = os.path.join(acc, "modelli")
    imp["estensione_browser"] = False
    imp["profili_siti"] = []
    return imp


# ------------------------------------------------------------------------------------------------- servizio
class Servizio:
    def __init__(self, base: str | None = None, impostazioni: dict | None = None, adesso=None, lettore=None,
                 motore_factory=None, mappa=None):
        """adesso: funzione → datetime (test); lettore: funzione giorno → eventi a consuntivo (test);
        motore_factory: funzione (doc) → (motore|None, profilo|None, info) (test)."""
        self.p = Percorsi(os.path.abspath(base)) if base else Percorsi.predefiniti()
        self.imp = impostazioni or carica_impostazioni(self.p.base)
        self._adesso = adesso or _ora_locale
        self._lettore = lettore
        self._motore_factory = motore_factory
        self._mappa = mappa

    # ------------------------------------------------------------------------------ percorsi
    def _f_revisione(self, g: str) -> str:
        return os.path.join(self.p.base, "revisione", f"{g}.json")

    def _f_finale(self, g: str) -> str:
        return os.path.join(self.p.base, "finali", f"{g}.json")

    def adesso(self) -> dt.datetime:
        return self._adesso().replace(microsecond=0)

    # --------------------------------------------------------------------------- informativa
    def serve_informativa(self) -> bool:
        return Stato(self.p).presa_visione() is None

    def dipendente(self) -> dict:
        return Stato(self.p).dipendente() or {}

    def salva_preferenze(self, nome: str, ufficio: str, cartella: str) -> None:
        """Solo preferenze personali; non copia la policy CED nel file utente."""
        cartella = os.path.abspath(os.path.expandvars(cartella.strip())) if cartella.strip() else ""
        if not cartella or cartella.startswith("\\\\"):
            raise ErroreApp("Scegli una cartella locale per i PDF.")
        if os.name == "nt":
            import ctypes
            if ctypes.windll.kernel32.GetDriveTypeW(os.path.splitdrive(cartella)[0] + "\\") == 4:
                raise ErroreApp("Scegli una cartella locale, non un'unità di rete.")
        os.makedirs(cartella, exist_ok=True)
        self.registra_informativa(nome, ufficio)
        path = os.path.join(self.p.base, "impostazioni.json")
        personal = _leggi(path, {})
        personal["cartella_pdf"] = cartella
        _scrivi(path, personal)
        self.imp["cartella_pdf"] = cartella

    def segnali_correnti(self, giorno):
        """Anteprima dei raw già raccolti, su richiesta UI; nessun sensore o salvataggio."""
        if self.imp.get("modalita") != "collector":
            return []
        from aggregatore.modelli import parse_records
        path=self.p.raw_giorno(giorno)
        if not os.path.isfile(path):return []
        try:
            records=[]
            with open(path,encoding="utf-8") as f:
                for line in f:
                    try:records.append(json.loads(line))
                    except ValueError:continue  # eventuale ultima riga ancora in scrittura
            if not records:return []
            doc=aggrega.aggregate(parse_records(records),self.mappa())
            cutoff=self.adesso().isoformat()
            rows=[f for f in doc["fasce"] if f["inizio"] <= cutoff and f.get("categorie")]
            return [{"ora":f["ora"],"fine":f["fine"][11:16],"categorie":[c for c in f["categorie"] if c not in ("rete","halley","postazione")]} for f in rows[-6:]]
        except (OSError,ValueError,KeyError):return []

    def salva_movimento(self, preferenza):
        if preferenza not in ("sistema","ridotte","complete"):
            raise ErroreApp("Preferenza animazioni non valida")
        path=os.path.join(self.p.base,"impostazioni.json")
        personal=_leggi(path,{})
        personal["riduci_animazioni"]=preferenza
        _scrivi(path,personal)
        self.imp["riduci_animazioni"]=preferenza

    def registra_informativa(self, nome: str, ufficio: str) -> None:
        nome, ufficio = " ".join((nome or "").split())[:80], " ".join((ufficio or "").split())[:80]
        if not nome:
            raise ErroreApp("Indica il tuo nome e cognome: compare nel resoconto.")
        st = Stato(self.p)
        st.salva_dipendente(nome, ufficio)
        if st.presa_visione() is None:
            st.registra_presa_visione(VERSIONE_INFORMATIVA, self.adesso())

    # --------------------------------------------------------------------------------- stato
    def stato(self) -> dict:
        """{"fase": da_avviare|in_corso|in_pausa, "giorno", "avvio", "precedente_aperto": {...}|None,
        "da_confermare": [giorni chiusi ma non confermati], "oggi_concluso": bool}"""
        st, oggi = Stato(self.p), self.adesso().date().isoformat()
        g = st.giornata()
        fin_oggi = self._f_finale(oggi)
        pdf_oggi = None
        if os.path.exists(fin_oggi):
            try:
                d = _leggi(fin_oggi, {})
                cod = ((d.get("integrita") or {}).get("sigillo_finale") or {}).get("codice")
                if cod:
                    cand = os.path.join(self.imp["cartella_pdf"], f"Resoconto_{oggi}_{cod}.pdf")
                    if os.path.exists(cand):
                        pdf_oggi = cand
            except Exception:  # noqa: BLE001
                pdf_oggi = None
        out = {"fase": "da_avviare", "giorno": oggi, "avvio": None, "precedente_aperto": None,
               "da_confermare": self.giorni_da_confermare(),
               # «salvato» solo se esiste il PDF: un JSON finale senza PDF (errore in creazione) resta da confermare
               "oggi_concluso": pdf_oggi is not None, "modalita": self.imp["modalita"]}
        if cg.chiusura_da_completare(self.p, g):
            # collaudo ALFA3 N2: giornata fermata ma senza JSON (errore in chiusura): resta visibile con «Riprova»
            out.update(fase="chiusura_da_completare", giorno=g["giorno"], avvio=g["fasi"][0].get("avvio"),
                       chiusura=g["fasi"][-1].get("chiusura"),
                       errore=(g.get("errore_chiusura") or {}).get("errore")
                       or "la chiusura si è interrotta prima di salvare i dati della giornata")
            return out
        if g.get("fase") in ("in_corso", "in_pausa"):
            # Decisione consolidata: un JSON per giorno di calendario con stato riportato oltre mezzanotte.
            # La giornata aperta resta «in corso» (Pausa/Chiudi visibili) anche dopo la mezzanotte; non «da avviare».
            out.update(fase=g["fase"], giorno=g["giorno"], avvio=g["fasi"][0].get("avvio"))
            if g["fase"] == "in_pausa":
                out["pausa_dalle"] = g["fasi"][-1].get("pausa")
            if g.get("giorno") != oggi:
                # Informativo per chi vuole chiudere all'ora scelta (proposta_chiusura_precedente); l'UI non nasconde Pausa/Chiudi.
                out["precedente_aperto"] = {"giorno": g["giorno"], "avvio": g["fasi"][0].get("avvio"),
                                            "fase": g["fase"]}
        return out

    def giorni_da_confermare(self) -> list[str]:
        """Giorni con JSON tecnico ma senza PDF sigillato (finale assente, o finale senza PDF — collaudo ALFA B2)."""
        out = []
        for f in sorted(glob.glob(os.path.join(self.p.giorni, "*.json"))):
            g = os.path.basename(f)[:-5]
            fin = self._f_finale(g)
            if not os.path.exists(fin):
                out.append(g)
                continue
            d = _leggi(fin, {})
            cod = ((d.get("integrita") or {}).get("sigillo_finale") or {}).get("codice")
            pdf = os.path.join(self.imp["cartella_pdf"], f"Resoconto_{g}_{cod}.pdf") if cod else None
            if not pdf or not os.path.exists(pdf):
                out.append(g)
        return out

    # -------------------------------------------------------------------------- avvio/pausa
    def _collector(self) -> bool:
        return self.imp["modalita"] == "collector"

    def avvia(self) -> str:
        st = self.stato()
        if st["precedente_aperto"]:
            raise ErroreApp("Prima chiudi la giornata precedente, rimasta aperta.")
        if st["fase"] == "chiusura_da_completare":
            raise ErroreApp("La chiusura della giornata precedente non è stata completata: usa «Riprova la chiusura».")
        if st["fase"] != "da_avviare":
            raise ErroreApp("La giornata è già avviata.")
        try:
            return cg.avvia(self.p, presa_visione=not self.serve_informativa(), lancia=self._collector())
        except cg.ErroreGiornata as e:
            raise ErroreApp(str(e)) from e

    def pausa(self) -> None:
        try:
            cg.pausa(self.p)
        except cg.ErroreGiornata as e:
            raise ErroreApp(str(e)) from e

    def riprendi(self) -> None:
        try:
            cg.riprendi(self.p, lancia=self._collector())
        except cg.ErroreGiornata as e:
            raise ErroreApp(str(e)) from e

    # --------------------------------------------------------------------------------- chiusura
    def mappa(self):
        if self._mappa is None:
            from aggregatore.mappa import Mappa
            self._mappa = Mappa.predefinita(self.imp.get("profili_siti") or [])
        return self._mappa

    def _lettore_consuntivo(self):
        """Bonifica B6b: nessuna lettura retroattiva del registro eventi di Windows (pacchetto ``consuntivo`` eliminato).
        A consuntivo la giornata si compone dei pulsanti (Avvia, Pausa, Chiudi) e di ciò che dichiara il dipendente."""
        if self._lettore is not None:          # solo test e collaudo con dati sintetici
            return self._lettore
        return lambda giorno: {"eventi": [], "copertura": {"sessione": "non_installato", "attivita": "non_installato",
                                                           "app": "non_installato", "rete": "non_installato",
                                                           "browser": "non_installato"},
                               "stato_iniziale": "sconosciuta"}

    def proposta_chiusura_precedente(self) -> dict:
        """Giornata rimasta aperta (es. ieri): avvio, ultimo pulsante (o evento del collector), fine proposta.
        Nessuna chiusura automatica: decide il dipendente."""
        g = Stato(self.p).giornata()
        if g.get("fase") not in ("in_corso", "in_pausa") or g.get("giorno") == self.adesso().date().isoformat():
            raise ErroreApp("Non c'è una giornata precedente da chiudere.")
        avvio = dt.datetime.fromisoformat(g["fasi"][0]["avvio"])
        ultimi = [dt.datetime.fromisoformat(x) for f in g["fasi"] for k, x in f.items() if k in ("avvio", "pausa")]
        fine_giorno = dt.datetime.combine(avvio.date() + dt.timedelta(days=1), dt.time(0), FUSO())
        ultima = None
        try:
            letto = self._lettore_consuntivo()(avvio.date())
            ts = [t for _, t, _ in letto.get("eventi", []) if avvio <= t < fine_giorno]
            ultima = max(ts) if ts else None
        except Exception:   # noqa: BLE001 - la proposta resta quella dei soli eventi dei pulsanti
            ultima = None
        proposta = max([x for x in ultimi + ([ultima] if ultima else [])])
        return {"giorno": g["giorno"], "avvio": avvio.isoformat(), "ultima_attivita": ultima.isoformat() if ultima else None,
                "fine_proposta": proposta.isoformat()}

    def _argomenti_chiusura(self) -> dict:
        return {"sigillo": True,
                "profili": self.imp.get("profili_siti") or [],
                "lettore": None if self._collector() else self._lettore_consuntivo(),
                "estensione": self.imp.get("estensione_browser") is True}

    def chiudi(self, quando: dt.datetime | None = None) -> dict:
        """Chiude la giornata in corso (o quella rimasta aperta, all'ora «quando» scelta dal dipendente).
        Se la chiusura fallisce la giornata resta «da completare» (stato()["fase"] == "chiusura_da_completare")."""
        t0 = time.monotonic()
        try:
            r = cg.chiudi(self.p, quando=quando, **self._argomenti_chiusura())
        except cg.ErroreGiornata as e:
            raise ErroreApp(str(e)) from e
        r["secondi"] = round(time.monotonic() - t0, 2)
        return r

    def riprova_chiusura(self) -> dict:
        """«Riprova la chiusura»: completa una chiusura non riuscita alla stessa ora (collaudo ALFA3 N2)."""
        t0 = time.monotonic()
        try:
            r = cg.completa_chiusura(self.p, **self._argomenti_chiusura())
        except cg.ErroreGiornata as e:
            raise ErroreApp(str(e)) from e
        r["secondi"] = round(time.monotonic() - t0, 2)
        return r

    def chiudi_e_genera(self, quando: dt.datetime | None = None, genera: bool = True, riprova: bool = False,
                        avanzamento=None) -> dict:
        """Lavoro del pulsante «Chiudi giornata – Genera resoconto» (e di «Riprova la chiusura»): chiusura, poi
        sintesi. È la stessa funzione usata dall'interfaccia e dal collaudo senza finestra (--smoke-giornata).
        avanzamento(passo, info): notifica opzionale dei passi (2 = dati letti, 3 = sintesi in corso)."""
        r = self.riprova_chiusura() if riprova else self.chiudi(quando)
        if avanzamento:
            avanzamento(2, r)
        out = {"chiusura": r, "giorno": r["giorno"]}
        if genera:
            if avanzamento:
                avanzamento(3, None)
            out["sintesi"] = self.genera(r["giorno"])
        return out

    # --------------------------------------------------------------------------------- revisione
    def revisione(self, g: str) -> dict:
        r = _leggi(self._f_revisione(g), {})
        r.setdefault("giorno", g)
        for k, v in (("manuali", []), ("segnalazioni", []), ("osservazioni", ""), ("riscritture", 0), ("sintesi", None),
                     ("storico_sintesi", [])):
            r.setdefault(k, v)
        return r

    def _salva_revisione(self, g: str, r: dict) -> None:
        _scrivi(self._f_revisione(g), r)

    def tecnico(self, g: str) -> dict:
        doc = _leggi(self.p.json_giorno(g))
        if doc is None:
            raise ErroreApp(f"I dati della giornata {g} non ci sono ancora: chiudi prima la giornata.")
        return doc

    def documento(self, g: str) -> dict:
        """Documento rivisto (tecnico + revisione) con la sintesi, se ancora valida."""
        tec, r = self.tecnico(g), self.revisione(g)
        tz = FUSO()
        man = []
        for m in r["manuali"]:
            a = dt.datetime.combine(dt.date.fromisoformat(g), dt.time.fromisoformat(m["dalle"]), tz)
            b = dt.datetime.combine(dt.date.fromisoformat(g), dt.time.fromisoformat(m["alle"]), tz)
            man.append(Manuale(a, b, m["categoria"], m.get("descrizione", "")))
        seg = [Segnalazione(s["campo"], s["nota"], dalle=s.get("dalle") or "", alle=s.get("alle") or "")
               for s in r["segnalazioni"]]
        doc = aggrega.apply_review(tec, man, r["osservazioni"], seg)
        doc["avvisi_revisione"] = [a for a in doc.get("avvisi_revisione", []) if not a.startswith("sintesi della giornata annullata")]
        doc["integrita"] = dict(doc.get("integrita") or {}, sigillo_finale=None)
        s = r.get("sintesi")
        if s and s.get("impronta_fatti") == mod_fatti.impronta(mod_fatti.estrai(doc)):
            doc = mod_sintesi.applica(doc, s)
        return doc

    def sintesi_valida(self, g: str) -> dict | None:
        return self.documento(g).get("sintesi_ai")

    def _cambia(self, g: str, fn) -> dict:
        r = self.revisione(g)
        fn(r)
        self._salva_revisione(g, r)
        return r

    def aggiungi_manuale(self, g: str, categoria: str, dalle: str, alle: str, descrizione: str) -> dict:
        if categoria not in CATEGORIE_MANUALI:
            raise ErroreApp("Scegli il tipo di attività.")
        try:
            a, b = dt.time.fromisoformat(dalle), dt.time.fromisoformat(alle)
        except ValueError:
            raise ErroreApp("Orario non valido: usa il formato hh:mm (es. 09:30).") from None
        if b <= a:
            raise ErroreApp("L'ora di fine deve essere dopo l'ora di inizio.")
        descrizione = " ".join((descrizione or "").split())
        if len(descrizione) > MAX_DESCRIZIONE:
            raise ErroreApp(f"La descrizione può avere al massimo {MAX_DESCRIZIONE} caratteri.")
        voce = {"categoria": categoria, "dalle": a.strftime("%H:%M"), "alle": b.strftime("%H:%M"),
                "descrizione": descrizione}

        def fn(r):
            n = max([int(m["id"][1:]) for m in r["manuali"]] + [0]) + 1
            r["manuali"].append({"id": f"d{n}", **voce})
            r["manuali"].sort(key=lambda m: (m["dalle"], m["alle"], m["id"]))
        return self._cambia(g, fn)

    def rimuovi_manuale(self, g: str, voce_id: str) -> dict:
        return self._cambia(g, lambda r: r.__setitem__("manuali", [m for m in r["manuali"] if m["id"] != voce_id]))

    def segnala(self, g: str, campo: str, dalle: str | None, alle: str | None, nota: str) -> dict:
        """«Dato apparentemente errato»: il dato resta com'è; si aggiunge un riferimento con la nota del dipendente."""
        if campo not in CAMPI_SEGNALABILI:
            raise ErroreApp("Campo della segnalazione non valido.")
        nota = " ".join((nota or "").split())
        if not nota:
            raise ErroreApp("Scrivi in breve che cosa non torna.")
        if len(nota) > MAX_NOTA:
            raise ErroreApp(f"La nota può avere al massimo {MAX_NOTA} caratteri.")
        voce = {"campo": campo, "dalle": dalle, "alle": alle, "nota": nota}
        # verifica subito che il riferimento sia valido (fascia esistente)
        aggrega.apply_review(self.tecnico(g), [], "", [Segnalazione(campo, nota, dalle=dalle or "", alle=alle or "")])

        def fn(r):
            n = max([int(s["id"][1:]) for s in r["segnalazioni"]] + [0]) + 1
            r["segnalazioni"].append({"id": f"s{n}", **voce})
        return self._cambia(g, fn)

    def rimuovi_segnalazione(self, g: str, sid: str) -> dict:
        return self._cambia(g, lambda r: r.__setitem__("segnalazioni", [s for s in r["segnalazioni"] if s["id"] != sid]))

    def imposta_osservazioni(self, g: str, testo: str) -> dict:
        testo = (testo or "").strip()
        if len(testo) > MAX_OSSERVAZIONI:
            raise ErroreApp(f"Le osservazioni possono avere al massimo {MAX_OSSERVAZIONI} caratteri.")
        return self._cambia(g, lambda r: r.__setitem__("osservazioni", testo))

    # -------------------------------------------------------------------------------- sintesi
    def disponibilita_ai(self, doc: dict | None = None) -> dict:
        """Controllo locale senza avviare runtime, connessioni o letture di dati della giornata."""
        from redattore import profilo
        sc = profilo.scegli(doc or {}, self.imp["modelli_ai"], forza=self.imp.get("profilo_ai"))
        srv = self.imp["server_ai"]
        codice = "disponibile"
        messaggio = "AI locale disponibile. Seleziona «Usa AI locale» per richiederla; altrimenti si usa il testo standard."
        if not os.path.isfile(srv):
            codice, messaggio = "runtime_assente", "AI locale non disponibile: assistente non installato. Chiedi ai Sistemi Informativi di completare l'installazione. Puoi usare il testo standard."
        elif not os.access(srv, os.R_OK):
            codice, messaggio = "permesso_negato", "AI locale non disponibile: accesso all'assistente negato. Chiedi ai Sistemi Informativi di verificare i permessi. Puoi usare il testo standard."
        elif not sc["modello"]:
            codice = "memoria_insufficiente" if "memoria libera" in sc["motivo"] else "modello_assente"
            messaggio = ("AI locale non disponibile: memoria libera insufficiente. Chiudi le applicazioni non necessarie e riprova, oppure usa il testo standard." if codice == "memoria_insufficiente" else
                         "AI locale non disponibile: modello non installato. Chiedi ai Sistemi Informativi di completare l'installazione del modello. Puoi usare il testo standard.")
        elif not os.access(sc["modello"], os.R_OK):
            codice, messaggio = "permesso_negato", "AI locale non disponibile: accesso al modello negato. Chiedi ai Sistemi Informativi di verificare i permessi. Puoi usare il testo standard."
        return {**sc, "disponibile": codice == "disponibile", "causa": codice, "messaggio": messaggio,
                "server_ai": srv, "modelli_ai": self.imp["modelli_ai"], "profilo_forzato": self.imp.get("profilo_ai"),
                "runtime_presente": os.path.isfile(srv), "runtime_leggibile": os.access(srv, os.R_OK)}

    def _motore(self, doc: dict):
        """(motore|None, profilo|None, info). Senza runtime o modello: testo standard (motivo in info)."""
        if self._motore_factory is not None:
            return self._motore_factory(doc)
        from redattore import motore, profilo
        srv = self.imp["server_ai"]
        sc = self.disponibilita_ai(doc)
        if not sc["disponibile"]:
            return None, None, sc
        m = motore.LlamaCpp(srv, sc["modello"], thread=int(self.imp.get("thread_ai") or 4),
                            cache_prefisso=self.imp.get("cache_ai"))
        return m, sc["profilo"], sc

    def genera(self, g: str, usa_ai: bool = True) -> dict:
        """«Genera resoconto». Restituisce la sintesi (con prestazioni e motivo dell'eventuale testo standard)."""
        doc = self.documento(g)
        m, prof, info = self._motore(doc) if usa_ai else (None, None, {"motivo": "Testo standard richiesto"})
        s = mod_sintesi.genera(doc, m, profilo=prof, adesso=self.adesso().isoformat())
        s["scelta_profilo"] = _profilo_pubblico(info)
        self._cambia(g, lambda r: r.__setitem__("sintesi", s))
        return s

    def riscritture_rimaste(self, g: str) -> int:
        return max(0, MAX_RISCRITTURE - int(self.revisione(g)["riscritture"]))

    def riscrivi(self, g: str, usa_ai: bool = True) -> dict:
        r = self.revisione(g)
        doc = self.documento(g)
        s = doc.get("sintesi_ai")
        if not s:
            raise ErroreApp("Prima genera il resoconto.")
        n = int(r["riscritture"]) + 1
        if n > MAX_RISCRITTURE:
            raise ErroreApp(f"Hai già usato le {MAX_RISCRITTURE} riscritture di oggi: puoi modificare il testo a mano.")
        m, prof, info = self._motore(doc) if usa_ai else (None, None, {"motivo": "Testo standard richiesto"})
        nuova = mod_sintesi.genera(doc, m, variante=n, precedente=s.get("testo_originale") or s.get("testo"),
                                   profilo=prof, adesso=self.adesso().isoformat())
        nuova["scelta_profilo"] = _profilo_pubblico(info)

        def fn(rr):
            rr["storico_sintesi"].append({"testo": s.get("testo"), "origine_testo": s.get("origine_testo")})
            rr["riscritture"] = n
            rr["sintesi"] = nuova
        self._cambia(g, fn)
        return nuova

    def controlla_testo(self, g: str, testo: str) -> dict:
        doc = self.documento(g)
        return mod_sintesi.controlla_modifica(testo, mod_fatti.estrai(doc))

    def modifica(self, g: str, testo: str, accetta_avvisi: bool = False) -> dict:
        """Solleva redattore.sintesi.AvvisiModifica (con .problemi) se servono avvisi da confermare."""
        doc = self.documento(g)
        if not doc.get("sintesi_ai"):
            raise ErroreApp("Prima genera il resoconto.")
        try:
            out = mod_sintesi.modifica(doc, testo, adesso=self.adesso().isoformat(), accetta_avvisi=accetta_avvisi)
        except mod_sintesi.AvvisiModifica:
            raise
        except ValueError as e:
            raise ErroreApp(str(e).capitalize() + ".") from e
        self._cambia(g, lambda r: r.__setitem__("sintesi", out["sintesi_ai"]))
        return out["sintesi_ai"]

    # --------------------------------------------------------------------------------- conferma
    def conferma(self, g: str, ho_verificato: bool) -> dict:
        """«Conferma e crea il PDF»: richiede «Ho verificato la sintesi». Sigillo finale + PDF nella cartella scelta."""
        if not ho_verificato:
            raise ErroreApp("Spunta «Ho verificato la sintesi» prima di confermare.")
        doc = self.documento(g)
        if not doc.get("sintesi_ai"):
            raise ErroreApp("Prima genera il resoconto.")
        t0 = time.monotonic()
        adesso = self.adesso().isoformat()
        doc = mod_sintesi.conferma(doc, adesso)
        key = sigillo.load_or_create_key(self.p.chiave)
        fin = sigillo.seal_final(doc, key, adesso)
        from resoconto.pdf import crea_pdf
        cod = fin["integrita"]["sigillo_finale"]["codice"]
        cartella = self.imp["cartella_pdf"]
        os.makedirs(cartella, exist_ok=True)
        path = os.path.join(cartella, f"Resoconto_{g}_{cod}.pdf")
        # PDF prima del JSON finale: se la creazione fallisce la giornata resta «da confermare» (collaudo ALFA B2)
        crea_pdf(fin, path, filigrana=self.imp.get("filigrana_pdf"))
        _scrivi(self._f_finale(g), fin)
        st = Stato(self.p)
        gg = st.giornata()
        if gg.get("giorno") == g and gg.get("fase") == "chiusa":
            gg["fase"] = "conclusa"
            gg["pdf"] = path
            st.salva_giornata(gg)
        from collector.retention import applica
        try:
            applica(self.p, oggi=self.adesso().date(), confermati=os.path.dirname(self._f_finale(g)), esegui=True)
        except (OSError, ValueError) as e:
            st.log(f"Policy raw non applicata: {e}")
        return {"pdf": path, "codice": cod, "json": self._f_finale(g), "secondi": round(time.monotonic() - t0, 2)}

    def resoconti_salvati(self) -> list[dict]:
        out = []
        for f in sorted(glob.glob(os.path.join(self.p.base, "finali", "*.json")), reverse=True):
            d = _leggi(f, {})
            sf = (d.get("integrita") or {}).get("sigillo_finale") or {}
            cod = sf.get("codice")
            pdf = os.path.join(self.imp["cartella_pdf"], f"Resoconto_{d.get('giorno')}_{cod}.pdf")
            fps = ((d.get("totali") or {}).get("rilevati") or {}).get("fasce_per_stato") or {}
            out.append({"giorno": d.get("giorno"), "codice": cod, "json": f, "pdf": pdf if os.path.exists(pdf) else None,
                        "fasce": fps.get("attivita_rilevata") or 0,          # bonifica B4: niente tempi totali
                        "dichiarate": len(d.get("manuali") or [])})
        return out

    def finale(self, g: str) -> dict:
        fin = _leggi(self._f_finale(g))
        if not fin:
            raise ErroreApp("Resoconto non trovato.")
        return fin

    def fasce_finora(self):
        """Barra della home durante la giornata: solo ciò che è noto senza leggere nulla (avvio, pause, adesso).
        Stati usati solo per il disegno: giornata avviata, in pausa, fuori dalla giornata."""
        from resoconto.formati import Giornata
        g = Stato(self.p).giornata()
        oggi = self.adesso().date()
        if g.get("giorno") != oggi.isoformat() or not g.get("fasi"):
            return None
        tz = FUSO()
        periodi = []                                   # (inizio, fine, stato)
        adesso = self.adesso()
        fasi = g["fasi"]
        for i, f in enumerate(fasi):
            a = dt.datetime.fromisoformat(f["avvio"])
            b = dt.datetime.fromisoformat(f["pausa"]) if f.get("pausa") else adesso
            periodi.append((a, b, "nessuna_attivita_informatica_rilevata"))
            if f.get("pausa"):
                fine_p = dt.datetime.fromisoformat(fasi[i + 1]["avvio"]) if i + 1 < len(fasi) else adesso
                periodi.append((b, fine_p, "raccolta_sospesa"))
        fasce = []
        inizio = dt.datetime.combine(oggi, dt.time(0), tz)
        for n in range(1440 // aggrega.FASCIA_MIN):
            a = inizio + dt.timedelta(minutes=aggrega.FASCIA_MIN * n)
            b = a + dt.timedelta(minutes=aggrega.FASCIA_MIN)
            stato = "sessione_chiusa"
            best = 0
            for pa, pb, st in periodi:
                ov = (min(b, pb) - max(a, pa)).total_seconds()
                if ov > best:
                    best, stato = ov, st
            fasce.append({"n": n, "ora": a.strftime("%H:%M"), "inizio": a.isoformat(), "fine": b.isoformat(), "stato": stato,
                          "app": [], "siti": []})
        return Giornata({"fasce": fasce, "totali": {"rilevati": {"durata_fascia_min": aggrega.FASCIA_MIN}},
                         "manuali": [], "classificazione": {}})

    def rigenera_pdf(self, g: str) -> str:
        fin = _leggi(self._f_finale(g))
        if not fin:
            raise ErroreApp("Resoconto non trovato.")
        from resoconto.pdf import crea_pdf
        cod = fin["integrita"]["sigillo_finale"]["codice"]
        os.makedirs(self.imp["cartella_pdf"], exist_ok=True)
        return crea_pdf(fin, os.path.join(self.imp["cartella_pdf"], f"Resoconto_{g}_{cod}.pdf"),
                        filigrana=self.imp.get("filigrana_pdf"))
