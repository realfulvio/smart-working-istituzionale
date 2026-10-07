"""M7 – servizio dell'applicazione: flusso completo a consuntivo senza interfaccia."""
import datetime as dt
import json
import os

import pytest
from pypdf import PdfReader

from applicazione.servizio import ErroreApp, Servizio
from collector import giornata as cg
from collector.stato import FUSO, Stato
from redattore.sintesi import AvvisiModifica
from resoconto.verifica import verifica_file

TZ = FUSO()
G = dt.date(2026, 10, 5)


def T(hm, giorno=G):
    h, m = map(int, hm.split(":"))
    return dt.datetime.combine(giorno, dt.time(h, m), TZ)


class Orologio:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def lettore(g):
    ev = [("sessione", T("08:01", g), {"evento": "sblocco"})]
    ev += [("web", T(f"{h:02d}:{m:02d}", g), {"sito": "halley"}) for h in range(8, 12) for m in (5, 20, 35, 50)]
    ev += [("sessione", T("12:31", g), {"evento": "blocco"})]
    return {"eventi": ev, "copertura": {"sessione": "parziale", "browser": "parziale", "attivita": "non_installato",
                                        "app": "non_installato", "rete": "non_installato"}, "stato_iniziale": "bloccata"}


class MotoreFinto:
    """Restituisce sempre il testo standard come se fosse del modello (nessun modello reale nei test)."""
    tipo = "finto"
    nome_modello = "finto"
    misure = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def descrizione(self):
        return {"tipo": "finto", "modello": "finto", "runtime": None}

    def genera(self, sistema, utente, schema, esempio=None):
        return json.dumps({"frasi": []}), {"secondi": 0.01}


@pytest.fixture
def srv(tmp_path, monkeypatch):
    oro = Orologio(T("07:58"))
    monkeypatch.setattr(cg, "_adesso", oro)
    imp = {"modalita": "consuntivo", "server_ai": str(tmp_path / "nessuno"), "modelli_ai": str(tmp_path / "m"),
           "cache_ai": str(tmp_path / "cache"), "thread_ai": 2, "profilo_ai": None, "cartella_pdf": str(tmp_path / "pdf"),
           "profili_siti": []}
    s = Servizio(str(tmp_path / "base"), imp, adesso=oro, lettore=lettore)
    s.orologio = oro
    return s


def test_diagnostica_memoria_e_path_non_propagano_al_resoconto(srv):
    g = _giornata_chiusa(srv)["giorno"]
    srv._motore_factory = lambda doc: (None, None, {
        "profilo_richiesto": "AI-STANDARD", "profilo": None,
        "motivo": "PC-ESEMPIO: RAM 1.7 GB; C:/privato/esempio/cache", "memoria_gb": {"totale": 8}})
    srv.genera(g)
    doc = srv.documento(g)
    serialized = json.dumps({k: v for k, v in doc.items() if k != "dati_tecnici_postazione"})
    assert "PC-ESEMPIO" not in serialized and "1.7 GB" not in serialized and "C:/privato" not in serialized
    assert doc["sintesi_ai"]["scelta_profilo"]["profilo_richiesto"] == "AI-STANDARD"


def _giornata_chiusa(s):
    s.registra_informativa("Rossi Maria (ESEMPIO)", "Ufficio Tributi")
    s.avvia()
    s.orologio.t = T("10:00"); s.pausa()
    s.orologio.t = T("10:15"); s.riprendi()
    s.orologio.t = T("12:40")
    return s.chiudi()


def test_informativa_obbligatoria(srv):
    assert srv.serve_informativa()
    with pytest.raises(ErroreApp):
        srv.avvia()
    with pytest.raises(ErroreApp):
        srv.registra_informativa("  ", "x")
    srv.registra_informativa("Rossi Maria", "Tributi")
    assert not srv.serve_informativa() and srv.dipendente()["nome"] == "Rossi Maria"


def test_flusso_completo_consuntivo(srv):
    assert srv.stato()["fase"] == "da_avviare"
    r = _giornata_chiusa(srv)
    g = G.isoformat()
    assert srv.stato()["da_confermare"] == [g]
    doc = srv.documento(g)
    assert doc["modalita"] == "consuntivo" and doc["dipendente"]["nome"] == "Rossi Maria (ESEMPIO)"
    st = {f["ora"]: f["stato"] for f in doc["fasce"]}
    assert st["08:00"] == "attivita_rilevata" and st["10:00"] == "raccolta_sospesa"
    # revisione
    srv.aggiungi_manuale(g, "telefonata", "12:45", "13:00", "Chiamata con un contribuente per una pratica")
    with pytest.raises(ErroreApp):
        srv.aggiungi_manuale(g, "riunione", "11:00", "10:00", "x")
    with pytest.raises(ErroreApp):
        srv.aggiungi_manuale(g, "riunione", "11:00", "12:00", "x" * 201)
    srv.segnala(g, "stato", "10:00", "10:15", "Ero al telefono con l'ufficio")
    with pytest.raises(ErroreApp):
        srv.segnala(g, "stato", "10:00", None, "x" * 201)
    srv.imposta_osservazioni(g, "Giornata regolare.")
    with pytest.raises(ErroreApp):
        srv.imposta_osservazioni(g, "x" * 501)
    doc = srv.documento(g)
    assert doc["manuali"][0]["origine"] == "dichiarata" and doc["segnalazioni_dipendente"][0]["nota"]
    tec = json.load(open(r["json"], encoding="utf-8"))
    assert [f["stato"] for f in doc["fasce"]] == [f["stato"] for f in tec["fasce"]]     # i dati automatici non cambiano
    # sintesi: nessun modello installato → testo standard
    s = srv.genera(g)
    assert s["origine_testo"] == "testo_standard" and "non disponibile" in s["scelta_profilo"]["motivo"]
    with pytest.raises(ErroreApp):
        srv.conferma(g, ho_verificato=False)
    srv.orologio.t = T("13:05")
    out = srv.conferma(g, ho_verificato=True)
    assert os.path.exists(out["pdf"]) and len(PdfReader(out["pdf"]).pages) >= 3
    v = verifica_file(out["pdf"], [os.path.join(srv.p.base, "chiave")])
    assert v["esito"] == "VALIDO", v
    assert srv.stato()["da_confermare"] == [] and srv.resoconti_salvati()[0]["codice"] == out["codice"]


def test_la_revisione_invalida_la_sintesi(srv):
    _giornata_chiusa(srv)
    g = G.isoformat()
    srv.genera(g)
    assert srv.sintesi_valida(g)
    srv.imposta_osservazioni(g, "Note.")            # anche le osservazioni entrano nei fatti (dichiarati)
    assert srv.sintesi_valida(g) is None
    srv.genera(g)
    srv.rimuovi_segnalazione(g, "nessuna")          # nessun cambiamento: la sintesi resta valida
    assert srv.sintesi_valida(g)
    srv.aggiungi_manuale(g, "riunione", "12:45", "13:30", "Riunione di settore")
    assert srv.sintesi_valida(g) is None            # fatti cambiati: va rigenerata
    with pytest.raises(ErroreApp):
        srv.conferma(g, True)


def test_riscrivi_al_massimo_tre_volte(srv):
    _giornata_chiusa(srv)
    g = G.isoformat()
    with pytest.raises(ErroreApp):
        srv.riscrivi(g)
    srv.genera(g)
    for i in range(3):
        srv.riscrivi(g)
        assert srv.riscritture_rimaste(g) == 2 - i
    with pytest.raises(ErroreApp):
        srv.riscrivi(g)
    assert len(srv.revisione(g)["storico_sintesi"]) == 3


def test_modifica_con_avvisi_da_confermare(srv):
    _giornata_chiusa(srv)
    g = G.isoformat()
    srv.genera(g)
    with pytest.raises(AvvisiModifica) as e:
        srv.modifica(g, "Nella giornata ho lavorato 9 ore su Microsoft Word e ho inviato 40 messaggi di posta.")
    assert e.value.problemi
    s = srv.modifica(g, "Nella giornata ho lavorato 9 ore su Microsoft Word e ho inviato 40 messaggi di posta.",
                     accetta_avvisi=True)
    assert s["origine_testo"] == "dichiarata" and s["controllo_modifica"]["accettata_con_avvisi"]
    out = srv.conferma(g, True)
    t = "\n".join(p.extract_text() for p in PdfReader(out["pdf"]).pages)
    assert "modificata dal dipendente" in t and "Avvisi del controllo confermati dal dipendente" in t


def test_giorno_precedente_non_chiuso(srv):
    srv.registra_informativa("Rossi Maria", "Tributi")
    srv.avvia()
    srv.orologio.t = T("08:30", G + dt.timedelta(days=1))
    cg._adesso.t = srv.orologio.t
    st = srv.stato()
    # Oltre mezzanotte: la giornata aperta resta in corso (Pausa/Chiudi), non «da avviare»
    assert st["fase"] == "in_corso" and st["giorno"] == G.isoformat()
    assert st["precedente_aperto"]["giorno"] == G.isoformat()
    with pytest.raises(ErroreApp):
        srv.avvia()
    pr = srv.proposta_chiusura_precedente()
    assert pr["ultima_attivita"].startswith(G.isoformat() + "T12:31") and pr["fine_proposta"] == pr["ultima_attivita"]
    with pytest.raises(ErroreApp):                         # non prima dell'avvio
        srv.chiudi(T("07:00"))
    r = srv.chiudi(dt.datetime.fromisoformat(pr["fine_proposta"]))
    doc = json.load(open(r["json"], encoding="utf-8"))
    assert doc["giorno"] == G.isoformat()
    assert {f["ora"]: f["stato"] for f in doc["fasce"]}["12:45"] != "attivita_rilevata"
    assert srv.stato()["precedente_aperto"] is None
    srv.avvia()                                            # oggi si avvia normalmente
    assert srv.stato()["fase"] == "in_corso"


