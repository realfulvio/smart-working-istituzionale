"""Test del redattore AI-Light (M5): fatti, controllo anti-invenzione, tentativi, testo standard, JSON giornaliero/3.

Il modello vero non serve: un motore finto restituisce risposte preparate (le prove con Qwen3-1.7B richiedono
il modello e non fanno parte della suite)."""
import copy
import json
import os
import sys

import pytest

from aggregatore import sigillo
from aggregatore.aggrega import apply_review
from aggregatore.cli import validate
from aggregatore.modelli import Manuale
from redattore import controllo, fatti, motore, sintesi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
ESEMPI = ["01_giornata_ufficio", "02_pause_lunghe_pranzo", "03_vdi_disconnessioni"]


def rivisto(nome="01_giornata_ufficio"):
    with open(os.path.join(ROOT, "examples", nome, "rivisto.json"), encoding="utf-8") as f:
        d = json.load(f)
    d["sintesi_ai"] = None
    d["integrita"]["sigillo_finale"] = None
    return d


@pytest.fixture(scope="module")
def sintetiche(tmp_path_factory):
    import m5_giornate_sintetiche as g
    return g.genera(str(tmp_path_factory.mktemp("m5")))


class Finto:
    """Motore finto: restituisce in ordine le risposte preparate (stringhe JSON) o solleva ErroreMotore."""
    tipo = "llama.cpp"

    def __init__(self, *risposte):
        self.risposte, self.misure, self.richieste, self.aperto = list(risposte), {}, [], False
        self.nome_modello = "finto"

    def __enter__(self):
        self.aperto = True
        self.misure["secondi_caricamento"] = 0.1
        return self

    def __exit__(self, *a):
        self.aperto = False
        self.misure["picco_mb"] = 123
        return False

    def descrizione(self):
        return {"tipo": "llama.cpp", "modello": "finto", "runtime": "test"}

    def genera(self, sistema, utente, schema, esempio=None):
        assert self.aperto
        self.richieste.append((sistema, utente, schema))
        r = self.risposte.pop(0)
        if isinstance(r, Exception):
            raise r
        return r, {"secondi": 1.0, "token_prompt": 100, "token_generati": 50}


def J(*frasi):
    return json.dumps({"frasi": [{"testo": t, "fatti": f} for t, f in frasi]}, ensure_ascii=False)


BUONA = J(("Lunedì 5 ottobre 2026 l'attività informatica rilevata si colloca tra le 08:00 e le 13:30, in 17 fasce "
           "da 15 minuti.", [1, 2, 3]),
          ("Le categorie rilevate comprendono Gestionale Halley e Strumenti d'ufficio.", [4]),
          ("Il dipendente ha dichiarato una riunione dalle 11:00 alle 11:45 e una telefonata dalle 13:40 alle 14:00.", [5, 6]))


# ------------------------------------------------------------------------------------------------- fatti
def test_fatti_deterministici_e_ordinati():
    d = rivisto()
    a, b = fatti.estrai(d), fatti.estrai(copy.deepcopy(d))
    assert a == b and fatti.impronta(a) == fatti.impronta(b)
    assert [f["id"] for f in a] == list(range(1, len(a) + 1))
    tipi = [f["tipo"] for f in a]
    assert tipi[:4] == ["giorno", "totale_rilevato", "orari", "categorie"]
    assert a[0]["testo"] == "Giornata del resoconto: lunedì 5 ottobre 2026."


def test_fatti_senza_rete_ne_dati_personali():
    d = rivisto()
    testo = fatti.elenco(fatti.estrai(d))
    assert "rete" not in testo.lower().replace("interamente", "")
    for vietato in (d["dipendente"]["nome"], d["dipendente"]["account"], d["postazione"]["host"], "112"):
        assert vietato not in testo


def test_fatti_dichiarati_etichettati():
    fs = fatti.estrai(rivisto())
    man = [f for f in fs if f["tipo"] == "manuale"]
    assert len(man) == 2 and all(f["origine"] == "dichiarato" and "dichiarata" in f["testo"] for f in man)
    assert not any(f["tipo"] == "totale_complessivo" for f in fs)        # bonifica B4: niente tempo complessivo
    assert any(f["tipo"] == "segnalazione" for f in fs) and any(f["tipo"] == "osservazioni" for f in fs)


def test_fatti_giornata_senza_dichiarate(sintetiche):
    d = json.load(open([p for p in sintetiche if "g05" in p][0], encoding="utf-8"))
    fs = fatti.estrai(d)
    assert any(f["tipo"] == "nessuna_dichiarata" for f in fs)
    assert any("Nessuna fascia con attività informatica rilevata" in f["testo"] for f in fs)


def test_durata():
    assert fatti.durata(45) == "45 minuti" and fatti.durata(60) == "60 minuti (1 ora)"
    assert fatti.durata(255) == "255 minuti (4 ore e 15 minuti)" and fatti.durata(1) == "1 minuto"


# ---------------------------------------------------------------------------------------------- controllo
def ctl(testo, ids, fs=None):
    fs = fs or fatti.estrai(rivisto())
    base = [{"testo": "Giornata del resoconto: lunedì 5 ottobre 2026.", "fatti": [1]}] * 2
    return controllo.controlla(base + [{"testo": testo, "fatti": ids}], fs)


def test_controllo_accetta_testo_fedele():
    fs = fatti.estrai(rivisto())
    r = controllo.controlla(sintesi._leggi(BUONA), fs)
    assert r == {"esito": "superato", "problemi": []}


@pytest.mark.parametrize("testo,ids,atteso", [
    ("L'attività informatica rilevata inizia alle 07:30.", [3], "orario 07:30"),
    ("L'attività informatica rilevata inizia alle 8.00.", [3], None),                 # 8.00 = 08:00: ammesso
    ("L'attività informatica rilevata ammonta a 300 minuti.", [2], "numero 300"),
    ("L'attività informatica rilevata copre il 53% della giornata.", [2], "numero 53"),
    ("L'attività informatica rilevata ammonta a 255 minuti.", [3], "numero 255"),      # numero vero, fatto sbagliato
    ("L'attività informatica rilevata dura quattro ore.", [2], "quattro"),
    ("Tra le 08:00 e le 13:30 risulta un'ora di sessione bloccata.", [10], "un'ora"),
    ("La giornata è stata produttiva, con 255 minuti di attività informatica rilevata.", [2], "produttiv"),
    ("Nessun periodo di inattività: 255 minuti di attività informatica rilevata.", [2], "inattiv"),
    ("L'attività informatica rilevata, ottima, ammonta a 255 minuti.", [2], "ottim"),
    ("Il dipendente ha dichiarato osservazioni sulle sue performance.", [8], "performance"),
    ("Il dipendente ha dichiarato una riunione dalle 11:00 alle 11:45.", [1], "riunion"),
    ("Risulta una riunione dalle 11:00 alle 11:45.", [5], "senza dire che è dichiarato"),
    ("La segnalazione riguarda la fascia 10:30–10:45.", [7], None),
    ("Il dipendente ha usato Microsoft Teams per 255 minuti di attività informatica rilevata.", [2], "teams"),
    ("Il dipendente ha registrato 255 minuti di attività informatica rilevata.", [2], "attribuisce"),
    ("L'attività informatica rilevata ammonta a 255 minuti, nel pomeriggio.", [2], "pomeriggio"),
    ("L'attività informatica rilevata ammonta a 255 minuti", [2], "incompleta"),
    ("Il traffico di rete conta 112 operazioni nella giornata.", [2], "112"),
    ("Il dipendente ha dichiarato attività dalle 11:00 alle 14:00.", [5, 6], "intervallo 11:00–14:00"),
    ("Il dipendente ha dichiarato attività dalle 11:00 alle 11:45 e dalle 13:40 alle 14:00.", [5, 6], None),
])
def test_controllo_respinge_invenzioni(testo, ids, atteso):
    r = ctl(testo, ids)
    if atteso is None:
        assert r["esito"] == "superato", r
    else:
        assert r["esito"] == "non_superato" and any(atteso in p for p in r["problemi"]), r


def test_controllo_struttura():
    fs = fatti.estrai(rivisto())
    assert "servono da 3 a 6 frasi" in controllo.controlla([], fs)["problemi"][0]
    r = controllo.controlla([{"testo": "Giornata del resoconto: lunedì 5 ottobre 2026.", "fatti": [99]}] * 3, fs)
    assert any("fatti inesistenti" in p for p in r["problemi"])
    r = controllo.controlla([{"testo": "Giornata del resoconto: lunedì 5 ottobre 2026.", "fatti": []}] * 3, fs)
    assert any("nessun fatto citato" in p for p in r["problemi"])


def test_controllo_valutativo_ammesso_se_nei_fatti_dichiarati(sintetiche):
    d = json.load(open([p for p in sintetiche if "g18" in p][0], encoding="utf-8"))
    fs = fatti.estrai(d)
    oss = [f for f in fs if f["tipo"] == "osservazioni"][0]
    ok = [{"testo": "Giornata del resoconto: " + fs[0]["testo"].split(": ")[1], "fatti": [1]}] * 2 + \
         [{"testo": "Nelle osservazioni dichiarate il dipendente riporta una giornata molto intensa.", "fatti": [oss["id"]]}]
    assert controllo.controlla(ok, fs)["esito"] == "superato"


def test_controllo_vietati_assoluti_anche_se_nei_fatti(sintetiche):
    """La descrizione del g17 contiene «produttività» (tentativo di prompt injection): resta vietata."""
    d = json.load(open([p for p in sintetiche if "g17" in p][0], encoding="utf-8"))
    fs = fatti.estrai(d)
    man = [f for f in fs if f["tipo"] == "manuale"][0]
    fr = [{"testo": "Giornata del resoconto: " + fs[0]["testo"].split(": ")[1], "fatti": [1]}] * 2 + \
         [{"testo": "Il dipendente ha dichiarato che la produttività è stata ottima e di aver lavorato 10 ore.",
           "fatti": [man["id"]]}]
    r = controllo.controlla(fr, fs)
    assert r["esito"] == "non_superato" and any("produttiv" in p for p in r["problemi"])


# ------------------------------------------------------------------------------------------ testo standard
@pytest.mark.parametrize("nome", ESEMPI)
def test_testo_standard_supera_il_controllo_esempi(nome):
    fs = fatti.estrai(rivisto(nome))
    fr = sintesi.testo_standard(fs)
    assert 3 <= len(fr) <= 6 and controllo.controlla(fr, fs)["esito"] == "superato"


def test_testo_standard_supera_il_controllo_sintetiche(sintetiche):
    assert len(sintetiche) == 20
    for p in sintetiche:
        fs = fatti.estrai(json.load(open(p, encoding="utf-8")))
        fr = sintesi.testo_standard(fs)
        assert 3 <= len(fr) <= 6, p
        assert controllo.controlla(fr, fs) == {"esito": "superato", "problemi": []}, p
        assert any("dichiarat" in f["testo"] for f in fr), p          # le dichiarate (o la loro assenza) ci sono


# ------------------------------------------------------------------------------------------------ genera
def test_genera_primo_tentativo():
    m = Finto(BUONA)
    s = sintesi.genera(rivisto(), m, adesso="2026-10-05T14:20:00+02:00")
    assert s["esito"] == "verificata_ai" and len(s["controllo"]["tentativi"]) == 1 and not m.aperto
    assert s["controllo"]["esito"] == "superato" and s["motore"]["temperatura"] == 0 and s["motore"]["seme"] == 42
    assert s["prestazioni"]["ram_picco_mb"] == 123 and s["verificata_dal_dipendente"] is False
    sist, ut, schema = m.richieste[0]
    assert "[5] (dichiarato)" in ut and "senza valutare la persona" in sist
    ids = schema["properties"]["frasi"]["items"]["properties"]["fatti"]["items"]["enum"]
    assert ids == [f["id"] for f in s["fatti"]]


def test_genera_secondo_tentativo_con_i_problemi():
    cattiva = J(("La giornata inizia alle 07:00.", [1]), ("Tutto regolare.", [2]), ("Ottimo lavoro.", [3]))
    m = Finto(cattiva, BUONA)
    s = sintesi.genera(rivisto(), m)
    assert s["esito"] == "verificata_ai" and [t["esito"] for t in s["controllo"]["tentativi"]] == ["non_superato", "superato"]
    assert "respinta dal controllo" in m.richieste[1][1] and "07:00" in m.richieste[1][1]


def test_genera_due_fallimenti_testo_standard():
    cattiva = J(("La giornata inizia alle 07:00.", [1]), ("Tutto regolare.", [2]), ("Ottimo lavoro.", [3]))
    s = sintesi.genera(rivisto(), Finto(cattiva, "non è json"))
    assert s["esito"] == "testo_standard" and s["controllo"]["esito"] == "superato"
    assert s["controllo"]["tentativi"][1]["problemi"] == ["risposta non leggibile come JSON"]
    assert s["frasi"] == sintesi.testo_standard(s["fatti"])


def test_genera_motore_non_disponibile():
    s = sintesi.genera(rivisto(), Finto(motore.ErroreMotore("modello non trovato")))
    assert s["esito"] == "testo_standard" and s["controllo"]["tentativi"][0]["esito"] == "errore_motore"


def test_genera_senza_modello_riproducibile():
    a = sintesi.genera(rivisto(), None, adesso="2026-10-05T14:20:00+02:00")
    b = sintesi.genera(rivisto(), None, adesso="2026-10-05T14:20:00+02:00")
    assert a == b and a["motore"]["tipo"] == "testo_standard" and a["prestazioni"]["secondi_totali"] is None


def test_prompt_qwen3_senza_ragionamento():
    p = motore.prompt_chatml("S", "U", qwen3=True, esempio=("D", "R"))
    assert p.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n") and p.count("<think>") == 2
    assert "<think>" not in motore.prompt_chatml("S", "U", qwen3=False)


def test_motore_llamacpp_modello_mancante():
    s = sintesi.genera(rivisto(), motore.LlamaCpp("llama-server-inesistente", "/non/esiste.gguf"))
    assert s["esito"] == "testo_standard" and "modello non trovato" in s["controllo"]["tentativi"][0]["problemi"][0]


# ------------------------------------------------------------------------------ JSON giornaliero/3 e sigilli
def test_schema_3_con_sintesi_ai_e_testo_standard():
    d = rivisto()
    assert d["schema"] == "rendiconto-sw/giornaliero/3"
    for m in (Finto(BUONA), None):
        out = sintesi.conferma(sintesi.applica(d, sintesi.genera(d, m)))
        assert validate(out) == [], validate(out)


def test_sigillo_finale_richiede_conferma_e_fatti_invariati(tmp_path):
    key = sigillo.load_or_create_key(str(tmp_path / "k"))
    with open(os.path.join(ROOT, "examples", "01_giornata_ufficio", "giorno.json"), encoding="utf-8") as f:
        g = json.load(f)
    g = sigillo.seal_technical({**g, "integrita": {"sigillo_tecnico": None, "sigillo_finale": None}}, key)
    d = sintesi.applica(g, sintesi.genera(g, Finto(BUONA.replace("[5, 6]", "[1]").replace(
        "Il dipendente ha dichiarato una riunione dalle 11:00 alle 11:45 e una telefonata dalle 13:40 alle 14:00.",
        "Giornata del resoconto: lunedì 5 ottobre 2026."))))
    with pytest.raises(ValueError, match="non è stata confermata"):
        sigillo.seal_final(d, key)
    c = sintesi.conferma(d)
    fin = sigillo.seal_final(c, key)
    assert sigillo.verify(fin)["esito"] in ("VALIDO", "INTEGRO") and fin["sintesi_ai"]["verificata_dal_dipendente"]
    # la sintesi è coperta dal sigillo finale (non da quello tecnico)
    alt = copy.deepcopy(fin); alt["sintesi_ai"]["testo"] += " Aggiunta."
    r = sigillo.verify(alt)
    assert r["tecnico"]["valido"] and not r["finale"]["valido"]
    # fatti cambiati dopo la sintesi (es. osservazioni modificate a mano): sigillo finale rifiutato
    man = copy.deepcopy(c); man["osservazioni_dipendente"] = "Altro testo"
    with pytest.raises(ValueError, match="non corrisponde ai dati"):
        sigillo.seal_final(man, key)
    with pytest.raises(ValueError, match="dati sono cambiati"):
        sintesi.conferma(man)


def test_revisione_annulla_la_sintesi():
    import datetime as dt
    from zoneinfo import ZoneInfo
    d = sintesi.applica(rivisto(), sintesi.genera(rivisto(), None))
    tz = ZoneInfo("Europe/Rome")
    mm = Manuale(dt.datetime(2026, 10, 5, 15, 0, tzinfo=tz), dt.datetime(2026, 10, 5, 15, 30, tzinfo=tz), "telefonata", "Prova")
    out = apply_review(d, [mm])
    assert out["sintesi_ai"] is None and any("sintesi" in a for a in out["avvisi_revisione"])
    assert d["sintesi_ai"] is not None                      # l'originale non è modificato


def test_applica_rifiuta_sintesi_di_altri_dati():
    s = sintesi.genera(rivisto("01_giornata_ufficio"), None)
    with pytest.raises(ValueError, match="non corrisponde"):
        sintesi.applica(rivisto("02_pause_lunghe_pranzo"), s)


def test_cli_redattore(tmp_path, capsys):
    from redattore.__main__ import main
    src = os.path.join(ROOT, "examples", "02_pause_lunghe_pranzo", "rivisto.json")
    out = str(tmp_path / "s.json")
    assert main(["fatti", src]) == 0 and "[1] (automatico) Giornata del resoconto" in capsys.readouterr().out
    assert main(["sintetizza", src, "-o", out, "--motore", "standard"]) == 0
    assert main(["controlla", out]) == 0
    assert main(["conferma", out, "-o", out]) == 0
    assert json.load(open(out, encoding="utf-8"))["sintesi_ai"]["verificata_dal_dipendente"] is True
    assert main(["sintetizza", src, "-o", out, "--motore", "llamacpp", "--server", "", "--modello", ""]) == 2


def test_nessuna_rete_esterna_nel_motore():
    """Il motore parla solo con 127.0.0.1 e non scarica nulla."""
    src = open(os.path.join(ROOT, "redattore", "motore.py"), encoding="utf-8").read()
    import re
    assert set(re.findall(r"https?://([\w.\-]+)", src)) <= {"127.0.0.1"}


# ------------------------------------------------------------------------- M6: controllo rafforzato
def _giornata(sintetiche, nome):
    return json.load(open([p for p in sintetiche if nome in p][0], encoding="utf-8"))


def _ctl_frase(fs, testo, ids):
    base = [{"testo": "Giornata del resoconto.", "fatti": [1]}] * 2
    return controllo.controlla(base + [{"testo": testo, "fatti": ids}], fs)["problemi"]


def test_controllo_massimo_fatti_per_frase(sintetiche):
    fs = fatti.estrai(_giornata(sintetiche, "g09"))
    p = _ctl_frase(fs, "Nella giornata risultano 0 messaggi di posta ricevuti.", [6, 7, 8, 9, 10])
    assert any("cita 5 fatti (massimo 4)" in x for x in p)
    assert not any("massimo" in x for x in _ctl_frase(fs, "Nella giornata risultano 0 messaggi di posta ricevuti.", [6]))


def test_controllo_quantita_con_unita_sbagliata():
    fs = fatti.estrai(rivisto())
    p = _ctl_frase(fs, "L'attività informatica rilevata ammonta a 17 ore.", [2])
    assert any("«17 or…» non compare con questa unità" in x for x in p)
    assert _ctl_frase(fs, "L'attività informatica rilevata risulta in 17 fasce da 15 minuti.", [2]) == []


def test_controllo_dichiarato_attribuito_al_rilevato(sintetiche):
    """Caso reale del banco v3 (g03 sulla postazione di prova): le 3 ore dichiarate presentate come attività rilevata."""
    fs = fatti.estrai(_giornata(sintetiche, "g03"))
    t = ("Il dipendente ha dichiarato un'attività formazione dalle 09:00 alle 12:00 (180 minuti), in aggiunta a "
         "un'attività rilevata (3 ore).")
    assert any("dichiarato ma è attribuito all'attività rilevata" in x for x in _ctl_frase(fs, t, [5, 6]))
    ok = "Il dipendente ha dichiarato un'attività formazione dalle 09:00 alle 12:00 (180 minuti (3 ore))."
    assert _ctl_frase(fs, ok, [5]) == []
    # orario dichiarato attribuito al rilevato
    t2 = "L'attività informatica rilevata inizia alle 09:00."
    assert any("orario 09:00 viene da un dato dichiarato" in x for x in _ctl_frase(fs, t2, [3, 5]))


def test_controllo_rilevato_attribuito_al_dipendente():
    fs = fatti.estrai(rivisto())
    t = "Il dipendente ha dichiarato 17 fasce di attività."
    assert any("rilevato ma è attribuito al dipendente" in x for x in _ctl_frase(fs, t, [2, 5]))


def test_controllo_conteggi(sintetiche):
    fs = fatti.estrai(_giornata(sintetiche, "g08"))          # 2 segnalazioni (fatti 6 e 7)
    assert _ctl_frase(fs, "Risultano 2 segnalazioni del dipendente su dati tecnici.", [6, 7]) == []
    assert _ctl_frase(fs, "Risultano due segnalazioni del dipendente su dati tecnici.", [6, 7]) == []
    fe = fatti.estrai(rivisto())                                  # 2 attività dichiarate (fatti 5 e 6)
    assert _ctl_frase(fe, "Il dipendente ha dichiarato due attività: una riunione e una telefonata.", [5, 6]) == []
    assert any("conteggio errato" in x for x in
               _ctl_frase(fe, "Il dipendente ha dichiarato tre attività: una riunione e una telefonata.", [5, 6]))
    assert any("conteggio errato" in x for x in _ctl_frase(fs, "Risultano 3 segnalazioni del dipendente.", [6, 7]))
    assert any("conteggio errato" in x for x in
               _ctl_frase(fs, "Il dipendente ha inviato una segnalazione su dati tecnici.", [6, 7]))
    # una sola segnalazione citata: «una segnalazione» è corretto
    assert not any("conteggio" in x for x in
                   _ctl_frase(fs, "Il dipendente ha inviato una segnalazione sulla posta senza fascia oraria.", [7]))


def test_testo_standard_rispetta_il_limite_di_fatti(sintetiche):
    for p in sintetiche:
        fs = fatti.estrai(json.load(open(p, encoding="utf-8")))
        assert all(len(f["fatti"]) <= controllo.MAX_FATTI_FRASE for f in sintesi.testo_standard(fs)), p


# ----------------------------------------------------------------------------- M6: profilo e modello
def test_profilo_sceglie_il_modello(tmp_path):
    from redattore import profilo
    for n in profilo.MODELLI.values():
        (tmp_path / n).write_bytes(b"x")
    std = {"postazione": {"profilo_ai": {"profilo": "AI-STANDARD", "criterio": "ram_rilevata"}}}
    r = profilo.scegli(std, str(tmp_path), memoria=(15.7, 9.0))
    assert r["profilo"] == "AI-STANDARD" and r["modello"].endswith("Qwen3-4B-Q4_K_M.gguf")
    r = profilo.scegli(std, str(tmp_path), memoria=(15.7, 3.0))          # poca memoria libera: ripiego sull'1.7B
    assert r["profilo"] == "AI-LIGHT" and "memoria libera" in r["motivo"]
    r = profilo.scegli(std, str(tmp_path), memoria=(15.7, 1.0))          # nemmeno per l'1.7B: testo standard
    assert r["modello"] is None and "testo standard" in r["motivo"]
    assert profilo.scegli({}, str(tmp_path), memoria=(15.7, 9.0))["profilo"] == "AI-STANDARD"   # ≥ 14 GB rilevati
    assert profilo.scegli({}, str(tmp_path), memoria=(11.9, 9.0))["profilo"] == "AI-LIGHT"
    assert profilo.scegli({}, str(tmp_path), memoria=(None, None))["profilo"] == "AI-LIGHT"
    os.remove(tmp_path / profilo.MODELLI["AI-STANDARD"])
    r = profilo.scegli(std, str(tmp_path), memoria=(15.7, 9.0))
    assert r["profilo"] == "AI-LIGHT" and "non installato" in r["motivo"]
    assert profilo.scegli(rivisto(), str(tmp_path), memoria=(8, 6), forza="AI-LIGHT")["criterio"] == "forzato"


def test_cache_prefisso_nome_stabile_e_senza_dati(tmp_path):
    m = motore.LlamaCpp("srv", str(tmp_path / "Qwen3-4B-Q4_K_M.gguf"), cache_prefisso=str(tmp_path))
    m.versione_runtime = "b1"
    p = motore.prompt_chatml(sintesi.SISTEMA, "x", True, sintesi.ESEMPIO)
    pref = p[: p.rfind("<|im_start|>user\n")]
    assert m._nome_cache(pref) == m._nome_cache(pref) and m._nome_cache(pref) != m._nome_cache(pref + "y")
    # il prefisso salvato contiene solo istruzioni ed esempio inventato, nessun fatto della giornata
    assert "Fatti della giornata (numerati):\n[1]" not in pref.split(sintesi.ESEMPIO_FATTI)[-1]


# ------------------------------------------------------------------------ M6: Riscrivi e modifiche
def test_riscrivi_nuova_versione_e_limite():
    d = sintesi.applica(rivisto(), sintesi.genera(rivisto(), Finto(BUONA)))
    d = sintesi.conferma(d)
    m = Finto(BUONA.replace("comprendono", "includono"))
    r = sintesi.riscrivi(d, m)
    s = r["sintesi_ai"]
    assert s["riscritture"] == 1 and s["motore"]["seme"] == sintesi.SEME + 1 and "includono" in s["testo"]
    assert s["verificata_dal_dipendente"] is False                  # va riconfermata
    assert "Versione precedente" in m.richieste[0][1] and "comprendono" in m.richieste[0][1]
    assert validate(sintesi.conferma(r)) == []
    for _ in range(2):
        r = sintesi.riscrivi(r, Finto(BUONA))
    with pytest.raises(ValueError, match="numero massimo di riscritture"):
        sintesi.riscrivi(r, Finto(BUONA))


def test_modifica_del_dipendente(tmp_path):
    d = sintesi.applica(rivisto(), sintesi.genera(rivisto(), Finto(BUONA)))
    orig = d["sintesi_ai"]["testo"]
    t = ("L'attività informatica rilevata va dalle 08:00 alle 13:30, in 17 fasce. "
         "Ho dichiarato una riunione dalle 11:00 alle 11:45 con l'ufficio tributi.")
    m = sintesi.modifica(d, t)
    s = m["sintesi_ai"]
    assert s["origine_testo"] == "dichiarata" and s["esito"] == "modificata_dal_dipendente"
    assert s["testo_originale"] == orig and s["controllo_modifica"]["esito"] == "superato"
    assert len(s["frasi"]) == 2 and s["verificata_dal_dipendente"] is False
    assert validate(sintesi.conferma(m)) == [], validate(sintesi.conferma(m))
    # un numero o un orario che non esiste nei dati: servono avvisi espliciti
    falso = "L'attività informatica rilevata va dalle 07:00 alle 13:30, per 300 minuti."
    with pytest.raises(sintesi.AvvisiModifica) as e:
        sintesi.modifica(m, falso)
    assert any("07:00" in p for p in e.value.problemi) and any("300" in p for p in e.value.problemi)
    m2 = sintesi.modifica(m, falso, accetta_avvisi=True)
    s2 = m2["sintesi_ai"]
    assert s2["controllo_modifica"]["accettata_con_avvisi"] is True and s2["testo_originale"] == orig
    # il dato rilevato non si può attribuire al dipendente nemmeno nel testo modificato
    with pytest.raises(sintesi.AvvisiModifica):
        sintesi.modifica(m, "Il dipendente ha dichiarato 17 fasce di lavoro al PC oltre alla riunione.")
    # sigillo finale solo dopo la nuova conferma
    key = sigillo.load_or_create_key(str(tmp_path / "k"))
    with open(os.path.join(ROOT, "examples", "01_giornata_ufficio", "giorno.json"), encoding="utf-8") as f:
        g = json.load(f)
    g = sigillo.seal_technical({**g, "integrita": {"sigillo_tecnico": None, "sigillo_finale": None}}, key)
    g = sintesi.applica(g, sintesi.genera(g, None))
    g = sintesi.modifica(sintesi.conferma(g), "L'attività informatica rilevata va dalle 08:00 alle 13:30, in 17 fasce.")
    with pytest.raises(ValueError, match="non è stata confermata"):
        sigillo.seal_final(g, key)
    fin = sigillo.seal_final(sintesi.conferma(g), key)
    assert sigillo.verify(fin)["finale"]["valido"]


def test_modifica_limiti():
    d = sintesi.applica(rivisto(), sintesi.genera(rivisto(), None))
    with pytest.raises(ValueError, match="tra 20 e 3000"):
        sintesi.modifica(d, "Corto.")
    with pytest.raises(ValueError, match="nessuna sintesi"):
        sintesi.modifica(rivisto(), "Un testo qualsiasi abbastanza lungo.")


def test_cli_riscrivi_e_modifica(tmp_path, capsys):
    from redattore.__main__ import main
    src = os.path.join(ROOT, "examples", "02_pause_lunghe_pranzo", "rivisto.json")
    out = str(tmp_path / "s.json")
    assert main(["sintetizza", src, "-o", out, "--motore", "standard"]) == 0
    assert main(["riscrivi", out, "-o", out, "--motore", "standard"]) == 0
    assert json.load(open(out, encoding="utf-8"))["sintesi_ai"]["riscritture"] == 1
    capsys.readouterr()
    assert main(["modifica", out, "-o", out, "--testo", "L'attività rilevata dura 999 minuti in tutto."]) == 3
    assert "999" in capsys.readouterr().out
    assert main(["modifica", out, "-o", out, "--testo", "L'attività rilevata dura 999 minuti in tutto.",
                 "--accetta-avvisi"]) == 0
    assert main(["controlla", out]) == 2                          # gli avvisi restano visibili
    s = json.load(open(out, encoding="utf-8"))["sintesi_ai"]
    assert s["origine_testo"] == "dichiarata" and s["controllo_modifica"]["accettata_con_avvisi"]


def test_secondo_tentativo_vede_la_versione_respinta():
    cattiva = BUONA.replace("17 fasce", "30 fasce")
    m = Finto(cattiva, BUONA)
    s = sintesi.genera(rivisto(), m, mostra_respinta=True)
    assert s["esito"] == "verificata_ai" and len(s["controllo"]["tentativi"]) == 2
    msg = m.richieste[1][1]
    assert "Versione respinta" in msg and "30 fasce" in msg and "numero 30" in msg
    m2 = Finto(cattiva, BUONA)                       # predefinito: solo l'elenco dei problemi
    sintesi.genera(rivisto(), m2)
    assert "Versione respinta" not in m2.richieste[1][1] and "numero 30" in m2.richieste[1][1]


def test_budget_di_tempo_salta_il_secondo_tentativo():
    class Lento(Finto):
        def genera(self, *a, **k):
            r, st = super().genera(*a, **k)
            st["secondi"] = 50.0
            return r, st
    cattiva = BUONA.replace("17 fasce", "30 fasce")
    s = sintesi.genera(rivisto(), Lento(cattiva, BUONA), budget_secondi=60)
    assert s["esito"] == "testo_standard" and len(s["controllo"]["tentativi"]) == 1
    assert s["prestazioni"]["tentativo_saltato_per_tempo"] is True
    assert validate(sintesi.conferma(sintesi.applica(rivisto(), s))) == []
    s2 = sintesi.genera(rivisto(), Lento(cattiva, BUONA), budget_secondi=None)
    assert s2["esito"] == "verificata_ai"


def test_controllo_chiuso_chiusa(sintetiche):
    fs = fatti.estrai(_giornata(sintetiche, "g15"))
    f = next(x for x in fs if x["tipo"] == "finestra")
    assert not any("chiuso" in p for p in _ctl_frase(fs, "Risulta il PC chiuso o spento per 90 minuti (1 ora e 30 minuti).", [f["id"]]))
