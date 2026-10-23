"""PDF/A-3b del resoconto e metadati AgID del documento informatico (file XML accanto al PDF)."""
import hashlib
import json
import os
import xml.etree.ElementTree as ET

from pypdf import PdfReader

from resoconto.pdf import NOME_ALLEGATO, crea_pdf
from resoconto.pdfa import data_pdf, data_xmp, profilo_srgb
from resoconto.verifica import verifica_file

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIN = os.path.join(RADICE, "examples", "01_giornata_ufficio", "finale.json")
CHIAVI = os.path.join(RADICE, "examples", "chiavi_registrate")


def carica():
    return json.load(open(FIN, encoding="utf-8"))


def test_struttura_pdfa3(tmp_path):
    r = PdfReader(crea_pdf(carica(), str(tmp_path / "r.pdf")))
    root = r.trailer["/Root"]
    oi = root["/OutputIntents"][0].get_object()
    assert oi["/S"] == "/GTS_PDFA1" and oi["/DestOutputProfile"].get_object()["/N"] == 3
    xmp = root["/Metadata"].get_object()
    assert "/Filter" not in xmp and xmp["/Subtype"] == "/XML"
    testo = xmp.get_data().decode("utf-8")
    assert "<pdfaid:part>3</pdfaid:part>" in testo and "<pdfaid:conformance>B</pdfaid:conformance>" in testo
    assert r.metadata["/Title"] in testo and r.metadata["/Producer"] in testo
    assert data_xmp(r.metadata["/CreationDate"]) == "2026-10-05T14:30:00+02:00"
    assert "/Trapped" not in r.metadata
    fs = root["/AF"][0].get_object()
    assert fs["/UF"] == NOME_ALLEGATO and fs["/AFRelationship"] == "/Data"
    ef = fs["/EF"]["/F"].get_object()
    assert ef["/Subtype"] == "/application/json" and ef["/Params"]["/Size"] == len(ef.get_data())
    assert json.loads(r.attachments[NOME_ALLEGATO][0]) == carica()


def test_pdfa_resta_valido_per_il_verificatore(tmp_path):
    out = crea_pdf(carica(), str(tmp_path / "r.pdf"))
    v = verifica_file(out, [CHIAVI])
    assert v["esito"] == "VALIDO" and v["grafica_pdf"] == "corrisponde ai dati"


def test_metadati_agid_accanto_al_pdf(tmp_path):
    pdf = crea_pdf(carica(), str(tmp_path / "Resoconto_2026-10-05_X.pdf"))
    xml = tmp_path / "Resoconto_2026-10-05_X.metadati.xml"
    m = ET.parse(xml).getroot()
    assert m.findtext("IdDoc/Impronta") == hashlib.sha256(open(pdf, "rb").read()).hexdigest()
    assert m.findtext("IdDoc/Algoritmo") == "SHA-256"
    assert m.findtext("IdDoc/Identificativo") == carica()["integrita"]["sigillo_finale"]["codice"]
    assert m.findtext("Soggetti/Nome") == carica()["dipendente"]["nome"]
    assert m.findtext("NomeDelDocumento") == "Resoconto_2026-10-05_X.pdf"
    assert m.findtext("Verifica/FirmatoDigitalmente") == "false"
    testo = xml.read_text(encoding="utf-8")
    assert "account" not in testo.lower() and carica()["dipendente"]["account"] not in testo


def test_pdf_di_prova_senza_metadati(tmp_path):
    crea_pdf(carica(), str(tmp_path / "p.pdf"), filigrana="DATI DI ESEMPIO")
    assert not (tmp_path / "p.metadati.xml").exists()


def test_profilo_e_date_deterministici():
    assert profilo_srgb() == profilo_srgb() and profilo_srgb()[36:40] == b"acsp"
    assert data_pdf("2026-10-05T14:30:00+02:00") == "D:20261005143000+02'00'"
    assert data_pdf(None) == "D:20000101000000+00'00'"
    assert data_xmp("D:20000101000000+00'00'") == "2000-01-01T00:00:00+00:00"
