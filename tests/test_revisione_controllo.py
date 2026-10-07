"""Regressioni della revisione indipendente: casi in cui un'invenzione passava il controllo anti-invenzione."""
import json
import os

import pytest

from redattore import controllo, fatti

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="module")
def fs():
    with open(os.path.join(RADICE, "examples", "01_giornata_ufficio", "rivisto.json"), encoding="utf-8") as f:
        return fatti.estrai(json.load(f))


def _id(fs, tipo):
    return next(f["id"] for f in fs if f["tipo"] == tipo)


def esito(fs, testo, tipo_fatto):
    """Controlla una frase in più, preceduta da due frasi corrette (servono almeno 3 frasi)."""
    frasi = [{"testo": "La giornata del resoconto è lunedì 5 ottobre 2026.", "fatti": [_id(fs, "giorno")]},
             {"testo": "L'attività informatica rilevata copre 17 fasce da 15 minuti.", "fatti": [_id(fs, "totale_rilevato")]},
             {"testo": testo, "fatti": [_id(fs, tipo_fatto)]}]
    return controllo.controlla(frasi, fs)


def test_frase_corretta_passa(fs):
    r = esito(fs, "Le prime attività rilevate iniziano alle 08:00 e l'ultima termina alle 13:30.", "orari")
    assert r["esito"] == "superato", r


@pytest.mark.parametrize("testo,tipo,parola", [
    ("Tra le applicazioni rilevate figura anche Photoshop per 45 minuti.", "applicazioni", "Photoshop"),
    ("Tra i siti di lavoro riconosciuti figura Wikipedia per 30 minuti.", "siti", "Wikipedia"),
    ("Tra le categorie rilevate figura Sviluppo software per 60 minuti.", "categorie", "Sviluppo"),
])
def test_nome_inventato_non_passa(fs, testo, tipo, parola):
    """Applicazioni, siti e categorie fuori dalle liste fisse (ATTIVITA/PAROLE_MAPPA) passavano il controllo."""
    r = esito(fs, testo, tipo)
    assert r["esito"] == "non_superato" and any(parola in p for p in r["problemi"]), r


@pytest.mark.parametrize("testo", [
    "L'attività rilevata è durata circa trentacinque minuti.",
    "L'attività è stata rilevata in diciotto fasce.",
    "Verso mezzogiorno è stata rilevata attività informatica.",
    "L'attività rilevata è terminata all'una.",
])
def test_numero_o_orario_in_lettere_non_passa(fs, testo):
    assert esito(fs, testo, "totale_rilevato")["esito"] == "non_superato"


@pytest.mark.parametrize("testo", ["L'attività rilevata è terminata alle 17.", "L'attività rilevata è iniziata alle ore 15."])
def test_ora_senza_minuti_non_in_fatti_non_passa(fs, testo):
    """«17» e «15» compaiono nei fatti come numeri di fasce/minuti, ma non come ore: l'ora inventata passava."""
    assert esito(fs, testo, "totale_rilevato")["esito"] == "non_superato"


def test_numero_presente_ma_con_altro_nome_non_passa(fs):
    r = esito(fs, "Sono stati aperti 17 documenti.", "totale_rilevato")
    assert r["esito"] == "non_superato" and any("documenti" in p for p in r["problemi"]), r


@pytest.mark.parametrize("testo", ["La giornata risulta poco produt­tiva.", "Il dipendente risulta inat​tivo."])
def test_caratteri_invisibili_non_aggirano_i_termini_vietati(fs, testo):
    r = esito(fs, testo, "totale_rilevato")
    assert r["esito"] == "non_superato" and any("vietato" in p for p in r["problemi"]), r


def test_omografo_cirillico_non_passa(fs):
    r = esito(fs, "Il dipendente risulta inаttivo.", "totale_rilevato")        # «а» cirillica
    assert r["esito"] == "non_superato" and any("non latini" in p for p in r["problemi"]), r


def test_funzioni_di_supporto():
    assert controllo.numeri_in_lettere("circa duecentodieci e ventitré e trentacinque") == ["duecentodieci", "ventitré", "trentacinque"]
    assert controllo.numeri_in_lettere("un uomo, uno studio, una riga") == []
    assert controllo.nomi_propri("Oggi l'app Excel e la Posta") == ["Excel", "Posta"]       # «Oggi» è a inizio frase
    assert controllo.nomi_propri("Ha detto: «Parola Citata» e Word") == ["Word"]


@pytest.mark.parametrize("testo", [
    "Sono stati rilevati 165 minuti con Microsoft Excel e 45 minuti con il Browser.",
    "Tra le applicazioni rilevate: per 165 minuti Microsoft Excel e per 45 minuti il Browser.",
])
def test_minuti_scambiati_tra_applicazioni_prima_del_nome_non_passano(fs, testo):
    """E2 guardava solo il numero DOPO il nome: con i numeri scritti prima («165 minuti con Excel») lo scambio passava."""
    r = esito(fs, testo, "applicazioni")
    assert r["esito"] == "non_superato" and any("scritti prima" in p for p in r["problemi"]), r


def test_nomi_senza_minuti_passano(fs):
    """Bonifica B4: i fatti portano solo i nomi; una frase con i soli nomi passa."""
    r = esito(fs, "Sono rilevati il Browser e Microsoft Excel.", "applicazioni")
    assert r["esito"] == "superato", r
