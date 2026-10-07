"""Comandi della giornata: avvia, pausa, riprendi, chiudi (stessi passi dei pulsanti dell'interfaccia M1)."""
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import subprocess
import sys
import time

from . import __version__
from .percorsi import Percorsi
from .registro import Registro
from .stato import FUSO, NOME_FUSO, Stato, intervalli_attivi

from resoconto.ente import carica as _ente
VERSIONE_INFORMATIVA = _ente().get("versione_informativa", "2026-10-07")
RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Attesa per il flush della fascia parziale dall'estensione dopo Chiudi (collaudo ALFA B12).
ATTESA_FLUSH_ESTENSIONE_S = 5.5


class ErroreGiornata(RuntimeError):
    pass


def _adesso():
    return dt.datetime.now(FUSO())


def _comando_demone() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "_esegui"]
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return [pyw if os.path.exists(pyw) else exe, "-m", "collector", "_esegui"]


def _lancia_demone(p: Percorsi, st: Stato):
    env = dict(os.environ, RSW_BASE=p.base)
    if not getattr(sys, "frozen", False):
        env["PYTHONPATH"] = RADICE + os.pathsep + env.get("PYTHONPATH", "")
    flags = 0x00000008 | 0x00000200 | 0x08000000 if sys.platform == "win32" else 0   # DETACHED|NEW_GROUP|NO_WINDOW
    subprocess.Popen(_comando_demone(), cwd=RADICE if not getattr(sys, "frozen", False) else None, env=env,
                     creationflags=flags, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True)
    for _ in range(50):
        if st.demone_attivo():
            return
        time.sleep(0.2)
    raise ErroreGiornata("il processo di raccolta non è partito (vedi diagnostica/collector.log)")


def _attendi_fine(st: Stato, secondi: float = 30):
    fine = time.monotonic() + secondi
    while time.monotonic() < fine:
        if not st.demone_attivo():
            return True
        time.sleep(0.5)
    return False


def avvia(p: Percorsi, presa_visione: bool = False, lancia: bool = True) -> str:
    st, reg, t = Stato(p), Registro(p), _adesso()
    if st.demone_attivo():
        raise ErroreGiornata("la raccolta è già in corso")
    if st.presa_visione() is None:
        if not presa_visione:
            raise ErroreGiornata("serve la presa visione dell'informativa (--presa-visione)")
        st.registra_presa_visione(VERSIONE_INFORMATIVA, t)
    g = st.giornata()
    giorno = t.date().isoformat()
    if chiusura_da_completare(p, g):
        # collaudo ALFA3 N2: una giornata fermata senza JSON non va sovrascritta né riaperta
        raise ErroreGiornata(f"la chiusura della giornata del {g.get('giorno')} non è stata completata: usa «Riprova»")
    if g.get("giorno") != giorno:
        if g.get("fase") in ("in_corso", "in_pausa"):
            # senza questo controllo lo stato della giornata aperta andava perso e il suo JSON non veniva mai prodotto
            raise ErroreGiornata(f"la giornata del {g.get('giorno')} è rimasta aperta: chiudila prima di avviarne una nuova")
        g = {"giorno": giorno, "fasi": []}
    from .retention import marca_nuova
    marca_nuova(p, giorno)
    reg.scrivi("sessione", t, evento="avvio_raccolta")
    g["fase"] = "in_corso"
    g["fasi"].append({"avvio": t.replace(microsecond=0).isoformat()})
    st.salva_giornata(g)
    if lancia:
        _lancia_demone(p, st)
    return giorno


def pausa(p: Percorsi) -> None:
    st, t = Stato(p), _adesso()
    g = st.giornata()
    if g.get("fase") != "in_corso":
        raise ErroreGiornata("la raccolta non è in corso")
    _ferma(p, st, "pausa", t)
    g["fase"] = "in_pausa"
    g["fasi"][-1]["pausa"] = t.replace(microsecond=0).isoformat()
    st.salva_giornata(g)


def riprendi(p: Percorsi, lancia: bool = True) -> None:
    st, reg, t = Stato(p), Registro(p), _adesso()
    g = st.giornata()
    if g.get("fase") != "in_pausa":
        raise ErroreGiornata("la raccolta non è in pausa")
    reg.scrivi("raccolta", t, evento="ripresa")
    reg.scrivi("sessione", t, evento="avvio_raccolta")
    g["fase"] = "in_corso"
    g["fasi"].append({"avvio": t.replace(microsecond=0).isoformat(), "ripresa": True})
    st.salva_giornata(g)
    if lancia:
        _lancia_demone(p, st)


def _ferma(p: Percorsi, st: Stato, comando: str, t: dt.datetime):
    if st.demone_attivo():
        st.invia_comando(comando, t)
        if _attendi_fine(st):
            return
        st.log(f"il processo di raccolta non ha risposto al comando {comando}")
    # processo non attivo (o bloccato): l'evento lo scrive la riga di comando
    st.cancella_comando()
    reg = Registro(p)
    if comando == "pausa":
        reg.scrivi("raccolta", t, evento="pausa")
    else:
        reg.scrivi("sessione", t, evento="fine_raccolta")


def meta(p: Percorsi, giorno: str, modalita: str = "collector", copertura: dict | None = None,
         stato_iniziale: str = "sconosciuta") -> dict:
    """Metadati della giornata. modalita «consuntivo» (M7): nessun processo di raccolta, nessun registro di Windows
    letto (bonifica B6b); copertura indicata dal lettore iniettato (test) o tutta «non_installato»."""
    st = Stato(p)
    d = st.demone()
    from aggregatore import __version__ as ver_agg
    dip = {}
    dip.update({k: v for k, v in (st.dipendente() or {}).items() if k in ("nome", "ufficio") and v})
    m = {"tipo": "meta", "giorno": giorno, "fuso": NOME_FUSO, "modalita": modalita,
         "dipendente": dip,
         "postazione": {}, "versioni": {"collector": __version__, "aggregatore": ver_agg},
         "copertura_fonti": {"sessione": "completa" if d.get("wts", True) else "non_disponibile",
                             "attivita": "completa", "app": "completa",
                             "rete": "parziale" if d.get("smb") else "non_disponibile",
                             "browser": "non_installato"},
         "stato_iniziale_sessione": stato_iniziale}
    if copertura:
        m["copertura_fonti"].update(copertura)
    m["copertura_fonti"] = dict(sorted(m["copertura_fonti"].items()))
    pv = st.presa_visione()
    if pv:
        m["presa_visione"] = pv
    from resoconto import ente
    if ente.carica()["dati_tecnici_postazione"]:
        from .postazione import rileva
        m["dati_tecnici_postazione"] = rileva()
    return m


def _righe(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(r) for r in f.read().splitlines() if r.strip() and not r.lstrip().startswith("#")]


def giorni_della_giornata(primo: str, ultimo: dt.date) -> list[str]:
    """Giorni di calendario toccati dalla raccolta (giornata a cavallo della mezzanotte: due o più giorni)."""
    d, out = dt.date.fromisoformat(primo), []
    while d <= max(ultimo, dt.date.fromisoformat(primo)):
        out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def _prepara_raw(p: Percorsi, giorno: str, riporto: list[dict], **meta_extra) -> tuple[str, list[dict]]:
    """Riscrive il raw del giorno: meta + eventi di sessione/raccolta dei giorni precedenti della stessa giornata
    (servono solo allo stato a mezzanotte, l'aggregatore non li conta) + eventi del giorno."""
    raw = p.raw_giorno(giorno)
    propri = [r for r in _righe(raw) if r.get("tipo") != "meta"]
    inizio = dt.datetime.combine(dt.date.fromisoformat(giorno), dt.time(0), FUSO())
    propri_pre = [r for r in propri if dt.datetime.fromisoformat(r["ts"]) < inizio]
    gia = {json.dumps(r, sort_keys=True) for r in propri_pre}
    riporto = [r for r in riporto if json.dumps(r, sort_keys=True) not in gia]
    righe = riporto + propri
    with open(raw + ".tmp", "w", encoding="utf-8") as f:
        f.write(json.dumps(meta(p, giorno, **meta_extra), ensure_ascii=False) + "\n")
        f.write("".join(json.dumps(r, ensure_ascii=False, separators=(", ", ": ")) + "\n" for r in righe))
    os.replace(raw + ".tmp", raw)
    return raw, [r for r in propri if r.get("tipo") in ("sessione", "raccolta")
                 and dt.datetime.fromisoformat(r["ts"]) >= inizio]


def _ultimo_avvio(g: dict) -> dt.datetime:
    """Inizio dell'ultimo periodo di raccolta (per una giornata in corso al momento della chiusura)."""
    f = (g.get("fasi") or [{}])[-1]
    if g.get("fase") == "in_corso" and "avvio" in f and not f.get("pausa"):
        return dt.datetime.fromisoformat(f["avvio"])
    return dt.datetime.max.replace(tzinfo=FUSO())


def carica_estensione():
    """Modulo lettore dell'estensione del browser, oppure None se il pacchetto non è installato.

    Il pacchetto ``estensione`` NON fa parte dell'eseguibile ALFA (escluso nella build): l'import è solo qui, solo
    quando l'estensione è attiva nelle impostazioni, e la sua assenza non fa fallire la chiusura (collaudo ALFA3 N1)."""
    try:
        from estensione import lettore
    except ImportError:
        return None
    return lettore


def chiusura_da_completare(p: Percorsi, g: dict | None = None) -> bool:
    """True se la giornata è stata fermata ma il suo JSON non è stato scritto: fase «in_chiusura» (errore durante la
    chiusura) oppure «chiusa» senza JSON (stato lasciato dall'ALFA3, collaudo N2). Si completa con completa_chiusura."""
    g = Stato(p).giornata() if g is None else g
    if g.get("fase") == "in_chiusura":
        return True
    if g.get("fase") == "chiusa" and g.get("giorno") and g.get("fasi") and g["fasi"][-1].get("chiusura"):
        return not g.get("json") and not os.path.exists(p.json_giorno(g["giorno"]))
    return False


def chiudi(p: Percorsi, sigillo: bool = True, profili=(), lettore=None,
           quando: dt.datetime | None = None, estensione: bool = False) -> dict:
    """Chiude la giornata. Se la raccolta ha attraversato la mezzanotte produce un JSON per ogni giorno di calendario:
    il giorno successivo riceve gli eventi di sessione/raccolta precedenti (stato a mezzanotte: attiva, bloccata,
    in pausa…), quindi le sue fasce iniziali non risultano «dato non disponibile».

    lettore (modalità «a consuntivo», M7): funzione giorno -> {"eventi": [(tipo, ts, campi)], "copertura": {...},
    "stato_iniziale": ...} (iniettato nei test; nel prodotto non legge nulla); gli eventi passano dal registro a campi chiusi.
    quando (M7): ora di chiusura scelta dal dipendente per una giornata rimasta aperta (mai nel futuro, mai prima
    dell'ultimo avvio/pausa); predefinita: adesso.
    estensione (M8): unisce le fasce scritte dall'host dell'estensione del browser (raw/estensione-<giorno>.jsonl),
    solo dentro i periodi di raccolta attiva; copertura «browser» parziale (solo siti dell'elenco + web generico).
    Se il pacchetto dell'estensione non è installato la chiusura prosegue senza (avviso nel risultato).
    La posta non si legge più (bonifica B2): Outlook resta solo la categoria «Posta elettronica» del campionatore.

    Transazione (collaudo ALFA3 N2): la fase diventa «chiusa» solo dopo che i JSON dei giorni sono scritti. Durante
    la lettura e l'aggregazione è «in_chiusura» (per l'estensione la raccolta è già finita: flush della fascia
    parziale, B12). Se qualcosa fallisce la giornata resta «in_chiusura» con l'errore, i file grezzi tornano come
    prima e i JSON parziali sono tolti: «Riprova» (completa_chiusura) rifà la stessa chiusura alla stessa ora."""
    st, t = Stato(p), _adesso()
    g = st.giornata()
    if g.get("fase") not in ("in_corso", "in_pausa"):
        raise ErroreGiornata("nessuna giornata da chiudere")
    if quando is not None:
        ultimo = max(dt.datetime.fromisoformat(x) for f in g["fasi"] for k, x in f.items() if k in ("avvio", "pausa"))
        if quando > t or quando < ultimo:
            raise ErroreGiornata("ora di chiusura non valida: deve essere dopo l'ultimo avvio o pausa e non nel futuro")
        t = quando
    if g["fase"] == "in_corso":
        _ferma(p, st, "chiudi", t)
    else:
        Registro(p).scrivi("sessione", t, evento="fine_raccolta")
    g["fase"] = "in_chiusura"
    g["fasi"][-1]["chiusura"] = t.replace(microsecond=0).isoformat()
    g.pop("errore_chiusura", None)
    st.salva_giornata(g)
    mod_est = carica_estensione() if estensione else None
    if mod_est is not None:
        # Attende il poll config (TTL 5 s) + invio della fascia parziale dall'estensione
        time.sleep(ATTESA_FLUSH_ESTENSIONE_S)
    return _completa(p, st, g, t, sigillo=sigillo, profili=profili, lettore=lettore,
                     estensione=estensione, mod_est=mod_est)


def completa_chiusura(p: Percorsi, sigillo: bool = True, profili=(), lettore=None,
                      estensione: bool = False) -> dict:
    """«Riprova»: completa una chiusura non riuscita (fase «in_chiusura») o una giornata «chiusa» senza JSON (ALFA3),
    all'ora di chiusura già registrata. Gli eventi di fine raccolta non vengono riscritti."""
    st = Stato(p)
    g = st.giornata()
    if not chiusura_da_completare(p, g):
        raise ErroreGiornata("non c'è una chiusura da completare")
    t = dt.datetime.fromisoformat(g["fasi"][-1]["chiusura"])
    g["fase"] = "in_chiusura"
    st.salva_giornata(g)
    mod_est = carica_estensione() if estensione else None
    return _completa(p, st, g, t, sigillo=sigillo, profili=profili, lettore=lettore,
                     estensione=estensione, mod_est=mod_est)


def _copia_raw(p: Percorsi, giorno: str) -> str:
    """Copia del grezzo del giorno com'era prima della chiusura (una sola volta: i tentativi successivi ripartono da
    lì, così gli eventi letti non si duplicano)."""
    raw = p.raw_giorno(giorno)
    copia = raw + ".prima_della_chiusura"
    if not os.path.exists(copia):
        if os.path.exists(raw):
            with open(raw, "rb") as a, open(copia + ".tmp", "wb") as b:
                b.write(a.read())
        else:
            open(copia + ".tmp", "wb").close()
        os.replace(copia + ".tmp", copia)
    else:
        with open(copia, "rb") as a, open(raw + ".tmp", "wb") as b:
            b.write(a.read())
        os.replace(raw + ".tmp", raw)
    return copia


def _completa(p: Percorsi, st: Stato, g: dict, t: dt.datetime, sigillo, profili, lettore,
              estensione, mod_est) -> dict:
    from aggregatore.cli import main as agg
    reg, riporto, esiti, avvisi = Registro(p), [], [], []
    if estensione and mod_est is None:
        avvisi.append("estensione del browser attiva ma non installata: siti dall'estensione non letti")
        st.log(avvisi[-1])
    giorni = giorni_della_giornata(g["giorno"], t.date())
    copie, scritti = {}, []
    try:
        for giorno in giorni:
            copie[giorno] = _copia_raw(p, giorno)
        for giorno in giorni:
            extra = {}
            if lettore is not None:
                letto = lettore(dt.date.fromisoformat(giorno))
                # Solo l'orario della giornata (Avvia→Chiudi, escluse le pause): la schermata promette
                # «solo per l'orario della giornata» (collaudo ALFA B3). Eventi di sessione precedenti
                # all'avvio restano utili solo per ricostruire lo stato all'inizio del periodo attivo.
                intervalli = intervalli_attivi({**g, "fase": "chiusa"}, t)
                if not intervalli and g.get("fasi"):
                    intervalli = [(_ultimo_avvio(g), t)]
                for tipo, ts, campi in letto.get("eventi", []):
                    if any(a <= ts < b for a, b in intervalli):
                        reg.scrivi(tipo, ts, **campi)
                # stato all'inizio del primo periodo attivo (non a mezzanotte): dagli eventi di sessione precedenti
                primo = intervalli[0][0] if intervalli else None
                stato_ini = letto.get("stato_iniziale") or "sconosciuta"
                if primo is not None:
                    prec = sorted(
                        (ts, campi.get("evento")) for tipo, ts, campi in letto.get("eventi", [])
                        if tipo == "sessione" and ts < primo and campi.get("evento"))
                    # mappa eventi → stato (allineata a sessione.EVENTI_V4 / aggregatore)
                    mappa_st = {"accesso": "attiva", "sblocco": "attiva", "blocco": "bloccata",
                                "disconnessione": "disconnessa", "uscita": "chiusa",
                                "sospensione": "sospesa", "ripresa": "attiva",
                                "avvio_raccolta": "attiva", "fine_raccolta": "chiusa"}
                    for _, ev in prec:
                        if ev in mappa_st:
                            stato_ini = mappa_st[ev]
                extra = {"modalita": "consuntivo", "copertura": letto.get("copertura") or {},
                         "stato_iniziale": stato_ini}
            if mod_est is not None:
                from aggregatore.mappa import Mappa
                ev_est = mod_est.eventi(p.raw, dt.date.fromisoformat(giorno), Mappa.predefinita(profili),
                                        intervalli_attivi({**g, "fase": "chiusa"}, t) + [(_ultimo_avvio(g), t)])
                for tipo, ts, campi in ev_est:
                    reg.scrivi(tipo, ts, **campi)
                cop = dict(extra.get("copertura") or {})
                if ev_est and cop.get("browser") != "completa":
                    cop["browser"] = "parziale"
                if cop:
                    extra["copertura"] = cop
            raw, nuovi = _prepara_raw(p, giorno, riporto, **extra)
            riporto += nuovi
            out = p.json_giorno(giorno)
            args = ["aggrega", raw, "-o", out] + (["--chiave", p.chiave] if sigillo else ["--senza-sigillo"])
            for x in profili:
                args += ["--profilo", x]
            scritti.append(out)
            rc = agg(args)
            if rc != 0:
                raise ErroreGiornata(f"aggregazione del {giorno} non riuscita (codice {rc})")
            esiti.append({"giorno": giorno, "json": out, "raw": raw})
    except Exception as e:
        # nessuna giornata «chiusa» a metà: grezzi come prima, JSON parziali tolti, errore nello stato
        for out in scritti:
            try:
                os.remove(out)
            except OSError:
                pass
        for giorno, copia in copie.items():
            try:
                with open(copia, "rb") as a, open(p.raw_giorno(giorno) + ".tmp", "wb") as b:
                    b.write(a.read())
                os.replace(p.raw_giorno(giorno) + ".tmp", p.raw_giorno(giorno))
            except OSError:
                pass
        msg = str(e) if isinstance(e, ErroreGiornata) else f"{type(e).__name__}: {e}"
        g["fase"] = "in_chiusura"
        g["errore_chiusura"] = {"quando": _adesso().replace(microsecond=0).isoformat(), "errore": msg[:500]}
        st.salva_giornata(g)
        st.log(f"chiusura non completata: {msg}")
        raise ErroreGiornata(f"chiusura non completata ({msg}). La giornata resta da chiudere: usa «Riprova».") from e
    g["fase"] = "chiusa"
    g.pop("errore_chiusura", None)
    g["json"] = esiti[0]["json"]
    if len(esiti) > 1:
        g["json_successivi"] = [e["json"] for e in esiti[1:]]
    st.salva_giornata(g)
    for copia in copie.values():
        try:
            os.remove(copia)
        except OSError:
            pass
    return {**esiti[0], "giorni": esiti, "avvisi": avvisi}
