"""M7 – PDF del resoconto dal JSON sigillato e verifica del PDF."""
import copy
import io
import json
import os

import pytest
from pypdf import PdfReader, PdfWriter

from aggregatore import sigillo
from redattore import sintesi
from resoconto.formati import Giornata, hm
from resoconto.pdf import NOME_ALLEGATO, crea_pdf, pdf_bytes
from resoconto.verifica import verifica_file

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIN = os.path.join(RADICE, "examples", "01_giornata_ufficio", "finale.json")
CHIAVI = os.path.join(RADICE, "examples", "chiavi_registrate")


def carica():
    return json.load(open(FIN, encoding="utf-8"))


def _testo(dati):
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(dati)).pages)


def test_paginazione_allegato_e_verifica_valido(tmp_path):
    out = crea_pdf(carica(), str(tmp_path / "r.pdf"))
    r = PdfReader(out)
    assert len(r.pages) >= 3
    assert r.trailer["/Root"]["/Lang"] == "it"
    assert json.loads(r.attachments[NOME_ALLEGATO][0]) == carica()
    v = verifica_file(out, [CHIAVI])
    assert v["esito"] == "VALIDO" and v["testo_pdf"] == "corrisponde ai dati"
    assert verifica_file(out)["esito"] == "INTEGRO"


def test_deterministico_e_contenuti():
    a, b = pdf_bytes(carica()), pdf_bytes(carica())
    assert a == b
    t = _testo(a)
    from resoconto import ente
    for atteso in ("La giornata in un documento.", "Sintesi", ente.carica()["nome"],
                   "Pagina 1", "Nota metodologica", "Sigillo finale", carica()["integrita"]["sigillo_finale"]["codice"],
                   "testo standard", "Riunione di servizio sulle scadenze IMU"):
        assert atteso in t, atteso
    # pagina 1 senza dati di rete
    p1 = PdfReader(io.BytesIO(a)).pages[0].extract_text()
    assert "richieste di rete" not in p1.lower()


def test_archivio_storico_incompleto_non_diventa_valido(tmp_path, monkeypatch):
    from resoconto import edizione
    path = crea_pdf(carica(), str(tmp_path / "r.pdf"))
    from resoconto import VERSIONE_APP
    monkeypatch.setattr(edizione, "identita", lambda: {"renderer_storici": {VERSIONE_APP: "pdf_999999"}})
    r = verifica_file(path, [CHIAVI])
    assert r["esito"] == "INTEGRO"
    assert "renderer storico" in r["testo_pdf"]


def test_senza_sigillo_finale_rifiutato(tmp_path):
    d = carica(); d["integrita"]["sigillo_finale"] = None
    with pytest.raises(ValueError):
        crea_pdf(d, str(tmp_path / "x.pdf"))
    crea_pdf(d, str(tmp_path / "prova.pdf"), filigrana="DATI DI ESEMPIO")      # prova: ammesso con filigrana
    assert verifica_file(str(tmp_path / "prova.pdf"))["esito"] == "NON SIGILLATO"


def test_allegato_manomesso_alterato(tmp_path):
    out = crea_pdf(carica(), str(tmp_path / "r.pdf"))
    d = carica(); d["totali"]["rilevati"]["minuti_attivita_rilevata"] = 400
    w = PdfWriter(clone_from=PdfReader(out))
    w2 = PdfWriter()
    for p in w.pages:
        w2.add_page(p)
    w2.add_attachment(NOME_ALLEGATO, json.dumps(d).encode())
    w2.write(str(tmp_path / "m.pdf"))
    assert verifica_file(str(tmp_path / "m.pdf"), [CHIAVI])["esito"] == "ALTERATO"


def test_testo_visibile_manomesso_alterato(tmp_path):
    """PDF impaginato da dati diversi ma con il JSON originale allegato: il testo non corrisponde."""
    orig = carica()
    falso = copy.deepcopy(orig); falso["osservazioni_dipendente"] = "Testo cambiato dopo la firma."
    w = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf_bytes(falso))))
    w.add_attachment(NOME_ALLEGATO, json.dumps(orig, ensure_ascii=False).encode("utf-8"))
    w.write(str(tmp_path / "f.pdf"))
    v = verifica_file(str(tmp_path / "f.pdf"), [CHIAVI])
    assert v["esito"] == "ALTERATO" and "testo del PDF non corrisponde" in " ".join(v["motivi"])


def test_pdf_senza_allegato_non_sigillato(tmp_path):
    p = tmp_path / "n.pdf"; p.write_bytes(pdf_bytes(carica()))
    assert verifica_file(str(p))["esito"] == "NON SIGILLATO"


def test_verifica_del_solo_json():
    assert verifica_file(FIN, [CHIAVI])["esito"] == "VALIDO"


@pytest.mark.parametrize("origine,attesa", [("ai", "scritta dall'assistente locale"),
                                            ("dichiarata", "modificata dal dipendente")])
def test_origine_della_sintesi_nel_pdf(origine, attesa):
    d = carica()
    s = d["sintesi_ai"]
    s["origine_testo"] = origine
    if origine == "dichiarata":
        s["controllo_modifica"] = {"esito": "non_superato", "problemi": ["frase 1: numero 9 non presente"],
                                   "accettata_con_avvisi": True}
    t = _testo(pdf_bytes(d, filigrana="PROVA"))
    assert attesa in t
    if origine == "dichiarata":
        assert "Avvisi del controllo confermati dal dipendente" in t and "numero 9 non presente" in t


def test_privacy_nessun_campo_vietato_nel_testo():
    t = _testo(pdf_bytes(carica())).lower()
    for x in ("gestionale.esempio", ".exe", "http", "@"):
        assert x not in t, x


def test_formati():
    assert hm(255) == "4 h 15" and hm(60) == "1 h" and hm(45) == "45 min" and hm(65, True) == "1 h 05 min"
    g = Giornata(carica())
    assert g.ore_estremi()[0] <= 8 and g.righe_revisione()
