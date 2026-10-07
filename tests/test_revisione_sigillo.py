"""Regressioni della revisione indipendente (revisione): sigilli, verifica, JSON ambiguo."""
import copy
import json
import os

import pytest

from aggregatore import sigillo
from aggregatore.cli import main
from resoconto.verifica import verifica_file

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINALE = os.path.join(RADICE, "examples", "01_giornata_ufficio", "finale.json")
REGISTRO = os.path.join(RADICE, "examples", "chiavi_registrate")


@pytest.fixture
def fin():
    with open(FINALE, encoding="utf-8") as f:
        return json.load(f)


def _scrivi(tmp_path, doc, nome="x.json"):
    p = tmp_path / nome
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return str(p)


def test_esempio_valido(fin):
    assert sigillo.verify(fin, [REGISTRO])["esito"] == "VALIDO"


def test_cli_senza_sigillo_finale_non_e_valido(fin, tmp_path):
    """Tolto il sigillo finale si possono cambiare dichiarazioni e osservazioni: il CLI non deve dire VALIDO (exit 0)."""
    d = copy.deepcopy(fin)
    d["integrita"]["sigillo_finale"] = None
    d["osservazioni_dipendente"] = "testo cambiato da terzi"
    d["manuali"][0]["descrizione"] = "descrizione falsa"
    p = _scrivi(tmp_path, d)
    assert main(["verifica", p, "--chiavi", REGISTRO]) == 2
    assert main(["verifica", p, "--chiavi", REGISTRO, "--solo-tecnico"]) == 0     # verifica volutamente tecnica


def test_cli_finale_integro_resta_valido(tmp_path):
    assert main(["verifica", FINALE, "--chiavi", REGISTRO]) == 0


@pytest.mark.parametrize("modifica", [
    lambda d: d["integrita"]["sigillo_tecnico"].__setitem__("sha256", 5),
    lambda d: d["integrita"]["sigillo_tecnico"].__setitem__("sha256", "zz"),
    lambda d: d["integrita"]["sigillo_finale"].__setitem__("firma", None),
    lambda d: d["integrita"].__setitem__("sigillo_finale", ["x"]),
    lambda d: d.__setitem__("integrita", [1]),
])
def test_sigillo_malformato_e_alterato_senza_eccezioni(fin, tmp_path, modifica):
    d = copy.deepcopy(fin)
    modifica(d)
    assert sigillo.verify(d, [REGISTRO])["esito"] == "ALTERATO"
    assert main(["verifica", _scrivi(tmp_path, d), "--chiavi", REGISTRO]) == 2      # mai 1 (= INTEGRO) per un'eccezione


def test_documento_non_oggetto_alterato():
    assert sigillo.verify([1, 2])["esito"] == "ALTERATO"


def test_account_e_pc_del_sigillo_finale_non_modificabili(fin):
    """account/pc non sono nella firma del sigillo finale: devono coincidere con quelli del sigillo tecnico (coperto)."""
    d = copy.deepcopy(fin)
    d["integrita"]["sigillo_finale"]["account"] = "DOMINIO\altro.utente"
    r = sigillo.verify(d, [REGISTRO])
    assert r["esito"] == "ALTERATO" and any("account" in m for m in r["motivi"])
    d = copy.deepcopy(fin)
    d["integrita"]["sigillo_finale"]["pc"] = "PC-FALSO"
    assert sigillo.verify(d, [REGISTRO])["esito"] == "ALTERATO"


def test_json_con_chiavi_duplicate_rifiutato(tmp_path):
    with open(FINALE, encoding="utf-8") as f:
        testo = f.read()
    dup = testo.replace('"giorno":', '"giorno": "1999-01-01", "giorno":', 1)
    assert dup != testo
    with pytest.raises(sigillo.JsonAmbiguo):
        sigillo.loads_stretto(dup)
    p = tmp_path / "dup.json"
    p.write_text(dup, encoding="utf-8")
    r = verifica_file(str(p), [REGISTRO])
    assert r["esito"] == "ALTERATO" and any("duplicate" in m for m in r["motivi"])
    assert main(["verifica", str(p), "--chiavi", REGISTRO]) == 2


def test_nan_rifiutato():
    with pytest.raises(ValueError):
        sigillo.loads_stretto('{"a": NaN}')


# ------------------------------------------------------------------------------- PDF: aspetto grafico oltre al testo
def _pdf_originale(tmp_path, fin):
    from resoconto.pdf import crea_pdf
    p = str(tmp_path / "orig.pdf")
    crea_pdf(fin, p)
    return p


def _modifica_pdf(origine, destinazione, fn):
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter(clone_from=PdfReader(origine))
    fn(w)
    with open(destinazione, "wb") as f:
        w.write(f)
    return destinazione


def test_pdf_originale_valido_anche_nella_grafica(tmp_path, fin):
    r = verifica_file(_pdf_originale(tmp_path, fin), [REGISTRO])
    assert r["esito"] == "VALIDO" and r["testo_pdf"] == "corrisponde ai dati" and r["grafica_pdf"] == "corrisponde ai dati"


def test_pdf_con_rettangolo_bianco_sopra_i_dati_e_alterato(tmp_path, fin):
    """Il testo estratto resta identico, ma il dato non si vede più: prima risultava VALIDO."""
    from pypdf.generic import ContentStream, NameObject

    def copri(w):
        pg = w.pages[0]
        c = ContentStream(None, w)
        c.set_data(pg.get_contents().get_data() + b"\nq 1 1 1 rg 30 250 540 300 re f Q")
        pg[NameObject("/Contents")] = w._add_object(c)
    p = _modifica_pdf(_pdf_originale(tmp_path, fin), str(tmp_path / "coperto.pdf"), copri)
    r = verifica_file(p, [REGISTRO])
    assert r["esito"] == "ALTERATO" and r["testo_pdf"] == "corrisponde ai dati" and r["grafica_pdf"] == "diversa dai dati"


def _dichiara_altra_versione(w):
    """I metadati del PDF li controlla chi lo modifica: dichiara un'altra versione di ReportLab."""
    from resoconto import VERSIONE_APP
    w.add_metadata({"/RendicontoSW": f"{VERSIONE_APP}|sigillato|rl0.0.0-dichiarata"})


def test_pdf_con_altra_versione_dichiarata_non_e_valido(tmp_path, fin):
    """Senza il confronto grafico non si può escludere un rettangolo sopra i dati: l'esito massimo è INTEGRO."""
    p = _modifica_pdf(_pdf_originale(tmp_path, fin), str(tmp_path / "altra.pdf"), _dichiara_altra_versione)
    r = verifica_file(p, [REGISTRO])
    assert r["esito"] == "INTEGRO" and r["grafica_pdf"].startswith("non confrontata")
    assert any("non verificato" in m for m in r["motivi"])


def test_rettangolo_bianco_con_versione_dichiarata_diversa_non_passa_per_valido(tmp_path, fin):
    """Regressione: cambiando i metadati si saltava il controllo grafico e il rettangolo bianco restava VALIDO."""
    from pypdf.generic import ContentStream, NameObject

    def copri_e_dichiara(w):
        pg = w.pages[0]
        c = ContentStream(None, w)
        c.set_data(pg.get_contents().get_data() + b"\nq 1 1 1 rg 30 250 540 300 re f Q")
        pg[NameObject("/Contents")] = w._add_object(c)
        _dichiara_altra_versione(w)
    p = _modifica_pdf(_pdf_originale(tmp_path, fin), str(tmp_path / "coperto2.pdf"), copri_e_dichiara)
    r = verifica_file(p, [REGISTRO])
    assert r["esito"] != "VALIDO", r


def test_annotazione_con_versione_dichiarata_diversa_e_alterata(tmp_path, fin):
    from pypdf.annotations import FreeText

    def annota_e_dichiara(w):
        w.add_annotation(page_number=0, annotation=FreeText(text="falso", rect=(50, 550, 300, 600)))
        _dichiara_altra_versione(w)
    p = _modifica_pdf(_pdf_originale(tmp_path, fin), str(tmp_path / "annotato2.pdf"), annota_e_dichiara)
    r = verifica_file(p, [REGISTRO])
    assert r["esito"] == "ALTERATO" and any("/Annots" in m for m in r["motivi"])


def test_pdf_con_annotazione_aggiunta_e_alterato(tmp_path, fin):
    from pypdf.annotations import FreeText

    def annota(w):
        w.add_annotation(0, FreeText(text="APPROVATO", rect=(50, 50, 300, 100)))
    p = _modifica_pdf(_pdf_originale(tmp_path, fin), str(tmp_path / "annotato.pdf"), annota)
    assert verifica_file(p, [REGISTRO])["esito"] == "ALTERATO"


def test_pdf_con_contenuto_attivo_e_alterato(tmp_path, fin):
    from pypdf.generic import DictionaryObject, NameObject, TextStringObject

    def js(w):
        w._root_object[NameObject("/OpenAction")] = DictionaryObject({NameObject("/S"): NameObject("/JavaScript"),
                                                                       NameObject("/JS"): TextStringObject("app.alert(1)")})
    p = _modifica_pdf(_pdf_originale(tmp_path, fin), str(tmp_path / "attivo.pdf"), js)
    r = verifica_file(p, [REGISTRO])
    assert r["esito"] == "ALTERATO" and any("attivo" in m for m in r["motivi"])


# ---------------------------------------------------------------------- identificativi: «$» accetta un a-capo finale
def test_identificativi_con_a_capo_finale_rifiutati():
    from aggregatore import aggrega, mappa
    from collector import registro
    assert aggrega.RE_ID.match("halley") and not aggrega.RE_ID.match("halley\n")
    assert mappa.RE_ID.match("halley") and not mappa.RE_ID.match("halley\n")
    assert mappa.RE_DOMINIO.match("ente.it") and not mappa.RE_DOMINIO.match("ente.it\n")
    assert mappa.RE_IPV4.match("203.0.113.1") and not mappa.RE_IPV4.match("203.0.113.1\n")
    registro.controlla("web", {"sito": "halley"})
    registro.controlla("app", {"exe": "WORD.EXE"})
    with pytest.raises(registro.ErroreRegistro):
        registro.controlla("web", {"sito": "halley\n"})
    with pytest.raises(registro.ErroreRegistro):
        registro.controlla("app", {"exe": "WORD.EXE\n"})


def test_schema_rifiuta_identificativo_con_a_capo_finale(fin):
    from aggregatore.cli import validate
    assert validate(fin) == []
    d = copy.deepcopy(fin)
    d["classificazione"]["siti"]["halley\n"] = {"etichetta": "x", "categoria": "halley"}
    assert validate(d), "il pattern ^...$ lasciava passare «halley\n»"


# ------------------------------------------------------------------- collector: giornata precedente rimasta aperta
def test_avvia_non_cancella_la_giornata_precedente_aperta(tmp_path, monkeypatch):
    import datetime as dt
    from collector import giornata
    from collector.percorsi import Percorsi
    from collector.stato import FUSO, Stato
    monkeypatch.setenv("RSW_BASE", str(tmp_path))
    base = Percorsi.predefiniti()
    orari = iter([dt.datetime(2026, 10, 5, 8, 0, tzinfo=FUSO()), dt.datetime(2026, 10, 6, 8, 0, tzinfo=FUSO())])
    monkeypatch.setattr(giornata, "_adesso", lambda: next(orari))
    giornata.avvia(base, presa_visione=True, lancia=False)
    with pytest.raises(giornata.ErroreGiornata, match="rimasta aperta"):
        giornata.avvia(base, presa_visione=True, lancia=False)         # il 6/10 senza aver chiuso il 5/10
    g = Stato(base).giornata()
    assert g["giorno"] == "2026-10-05" and g["fase"] == "in_corso" and len(g["fasi"]) == 1


# ---------------------------------------------------------------------- applicazione: giornata oltre la mezzanotte
def test_giornata_in_corso_oltre_la_mezzanotte_resta_in_corso(tmp_path, monkeypatch):
    import datetime as dt
    from applicazione.servizio import Servizio
    from collector import giornata as cg
    from collector.stato import FUSO
    T = lambda g, h, m: dt.datetime(2026, 10, g, h, m, tzinfo=FUSO())

    class Orologio:
        t = T(5, 23, 40)
        def __call__(self):
            return self.t
    oro = Orologio()
    monkeypatch.setattr(cg, "_adesso", oro)
    imp = {"modalita": "consuntivo", "server_ai": str(tmp_path / "x"), "modelli_ai": str(tmp_path / "m"), "cache_ai": str(tmp_path / "c"),
           "thread_ai": 2, "profilo_ai": None, "cartella_pdf": str(tmp_path / "pdf"), "profili_siti": [], "browser": False,
           "posta": False}
    s = Servizio(str(tmp_path / "base"), imp, adesso=oro)
    s.registra_informativa("Rossi Maria (ESEMPIO)", "Ufficio Tributi")
    s.avvia()
    assert s.stato()["fase"] == "in_corso"
    oro.t = T(6, 0, 30)                         # il dipendente sta ancora lavorando, dopo la mezzanotte
    st = s.stato()
    assert st["fase"] == "in_corso"
    assert st["giorno"] == "2026-10-05"          # un JSON per giorno di calendario: resta la giornata aperta
    assert st["precedente_aperto"] is not None   # informativo; Pausa/Chiudi restano (fase != da_avviare)


# ------------------------------------------------- PDF: il confronto grafico non dipende dalla cartella di installazione
def test_pdf_verificato_con_un_percorso_degli_asset_diverso_resta_valido(tmp_path, fin, monkeypatch):
    """Collaudo ALFA: ReportLab chiama il logo «/FormXob.<hash del percorso del file>». Il PDF creato in una cartella e
    verificato su un altro PC/profilo (percorso diverso) risultava ALTERATO (aspetto grafico) pur essendo identico."""
    import shutil
    from resoconto import pdf_istituzionale as modulo_pdf
    from resoconto.pdf import crea_pdf
    a, b = tmp_path / "installazione_A" / "assets", tmp_path / "installazione_B_altro_utente" / "assets"
    shutil.copytree(modulo_pdf.ASSETS, a)
    shutil.copytree(modulo_pdf.ASSETS, b)
    monkeypatch.setattr(modulo_pdf, "ASSETS", str(a))
    p = str(tmp_path / "creato_in_A.pdf")
    crea_pdf(fin, p)
    monkeypatch.setattr(modulo_pdf, "ASSETS", str(b))          # il verificatore rigenera il PDF con un altro percorso
    r = verifica_file(p, [REGISTRO])
    assert r["esito"] == "VALIDO" and r["grafica_pdf"] == "corrisponde ai dati", r
