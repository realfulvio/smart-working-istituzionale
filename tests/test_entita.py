"""M7 – controllo «tipo di entità» e abbinamento numero/orari ↔ entità (redattore/entita.py)."""
import json
import os

from redattore import controllo, entita, fatti as F, sintesi

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FATTI = [
    {"id": 1, "testo": "Giornata del resoconto: lunedì 5 ottobre 2026.", "origine": "automatico", "tipo": "giorno"},
    {"id": 2, "testo": "Categorie di attività rilevate (minuti delle fasce in cui compaiono): Strumenti d'ufficio 270 "
                       "minuti, Posta elettronica 105 minuti.", "origine": "automatico", "tipo": "categorie"},
    {"id": 3, "testo": "Applicazioni rilevate (minuti delle fasce in cui compaiono): Microsoft Word 270 minuti, "
                       "Microsoft Outlook 105 minuti.", "origine": "automatico", "tipo": "applicazioni"},
    {"id": 4, "testo": "Attività dichiarata dal dipendente (riunione) dalle 11:00 alle 11:45, 45 minuti: 'IMU'.",
     "origine": "dichiarato", "tipo": "manuale"},
    {"id": 5, "testo": "Attività dichiarata dal dipendente (telefonata) dalle 13:40 alle 14:00, 20 minuti: 'TARI'.",
     "origine": "dichiarato", "tipo": "manuale"},
]


def P(testo, ids):
    return entita.controlla_frase(testo, [f for f in FATTI if f["id"] in ids], FATTI, "frase 1")


def test_app_presentata_come_categoria():
    p = P("Le categorie prevalenti sono Strumenti d'ufficio (270 minuti) e Microsoft Word (270 minuti).", [2, 3])
    assert len(p) == 1 and "applicazione, non una categoria" in p[0]


def test_categoria_presentata_come_applicazione():
    p = P("Le applicazioni più usate sono Microsoft Outlook (105 minuti) e Posta elettronica (105 minuti).", [2, 3])
    assert len(p) == 1 and "categoria, non un'applicazione" in p[0]


def test_frase_corretta_e_parti_separate():
    assert P("Le categorie prevalenti sono Strumenti d'ufficio (270 minuti) e Posta elettronica (105 minuti).", [2]) == []
    assert P("Le categorie sono Strumenti d'ufficio (270 minuti); tra le applicazioni Microsoft Word (270 minuti).",
             [2, 3]) == []


def test_minuti_di_unaltra_entita():
    p = P("Tra le applicazioni, Microsoft Outlook è stata usata per 270 minuti.", [3])
    assert len(p) == 1 and "abbinamento numero" in p[0]
    assert P("Tra le applicazioni, Microsoft Outlook (105 minuti) e Word (270 minuti).", [3]) == []


def test_orari_di_unaltra_attivita_dichiarata():
    p = P("Il dipendente ha dichiarato una riunione dalle 13:40 alle 14:00 e una telefonata dalle 11:00 alle 11:45.", [4, 5])
    assert len(p) == 2 and all("abbinamento orari" in x for x in p)
    assert P("Il dipendente ha dichiarato una riunione dalle 11:00 alle 11:45 e una telefonata dalle 13:40 alle "
             "14:00.", [4, 5]) == []


def test_integrato_nel_controllo_e_ambiguita():
    frasi = [{"testo": "Nella giornata di lunedì 5 ottobre 2026 le categorie prevalenti sono Microsoft Word (270 minuti).",
              "fatti": [1, 3]},
             {"testo": "Il dipendente ha dichiarato una riunione dalle 11:00 alle 11:45.", "fatti": [4]},
             {"testo": "Il dipendente ha dichiarato una telefonata dalle 13:40 alle 14:00.", "fatti": [5]}]
    r = controllo.controlla(frasi, FATTI)
    assert r["esito"] == "non_superato" and any("tipo di entità" in x for x in r["problemi"])
    # «Halley» è sia sito sia parte della categoria «Gestionale Halley»: ambiguo, non giudicato
    f = [{"id": 1, "testo": "Categorie di attività rilevate (minuti delle fasce in cui compaiono): Gestionale Halley 60 "
                            "minuti.", "origine": "automatico", "tipo": "categorie"},
         {"id": 2, "testo": "Siti di lavoro riconosciuti: Halley 60 minuti.", "origine": "automatico", "tipo": "siti"}]
    assert entita.controlla_frase("Le categorie sono: Halley (60 minuti).", f, f, "x") == []


def test_testi_standard_degli_esempi_superano_il_controllo():
    for es in ("01_giornata_ufficio", "02_pause_lunghe_pranzo", "03_vdi_disconnessioni"):
        doc = json.load(open(os.path.join(RADICE, "examples", es, "rivisto.json"), encoding="utf-8"))
        fa = F.estrai(doc)
        assert controllo.controlla(sintesi.testo_standard(fa), fa)["esito"] == "superato"


def test_entita_dai_fatti():
    e = entita.entita_dai_fatti(FATTI)
    assert ("microsoft word", 270, 3) in e["app"] and ("strumenti d'ufficio", 270, 2) in e["cat"]


def test_nome_di_categoria_con_segnalazioni_non_e_dichiarato():
    """Pilota postazione di prova: «Assistenza e segnalazioni» è il nome di una categoria, non una segnalazione del dipendente."""
    fatti = [
        {"id": 1, "testo": "Giornata del resoconto: venerdì 2 ottobre 2026.", "origine": "automatico", "tipo": "giorno"},
        {"id": 2, "testo": "Categorie di attività rilevate (minuti delle fasce in cui compaiono): Assistenza e "
                           "segnalazioni 60 minuti, Servizi online del Comune 45 minuti, Gestionale Halley 30 minuti.",
         "origine": "automatico", "tipo": "categorie"},
    ]
    frasi = [{"testo": "La giornata del resoconto è venerdì 2 ottobre 2026.", "fatti": [1]},
             {"testo": "Le categorie prevalenti sono Assistenza e segnalazioni (60 minuti), Servizi online del Comune "
                       "(45 minuti) e Gestionale Halley (30 minuti).", "fatti": [2]},
             {"testo": "Non risultano altre attività rilevate dalla postazione.", "fatti": [2]}]
    p = [x for x in controllo.controlla(frasi, fatti)["problemi"] if "attribuito al dipendente" in x]
    assert p == []
    # una vera attribuzione al dipendente resta segnalata
    frasi[1] = {"testo": "Il dipendente ha dichiarato 60 minuti di assistenza.", "fatti": [2]}
    p = [x for x in controllo.controlla(frasi, fatti)["problemi"] if "attribuito al dipendente" in x]
    assert p
