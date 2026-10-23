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


def _firmato(tmp_path, base, coerente=True, campo_extra=False, modifica=None):
    """PDF con una revisione incrementale che aggiunge un campo firma (/Sig) con /ByteRange coerente, come fa un
    firmatario PAdES. La crittografia non c'è: il Verificatore non la controlla. `modifica(writer)` aggiunge altre
    modifiche nella stessa revisione (es. testo cambiato)."""
    from pypdf import PdfWriter
    from pypdf.generic import (ArrayObject, ByteStringObject, DictionaryObject, NameObject, NumberObject,
                               TextStringObject)
    w = PdfWriter(base, incremental=True)
    segnaposto = 1_000_000_000
    firma = DictionaryObject({
        NameObject("/Type"): NameObject("/Sig"), NameObject("/Filter"): NameObject("/Adobe.PPKLite"),
        NameObject("/SubFilter"): NameObject("/ETSI.CAdES.detached"),
        NameObject("/ByteRange"): ArrayObject([NumberObject(0), NumberObject(segnaposto), NumberObject(segnaposto + 1),
                                               NumberObject(segnaposto + 2)]),
        NameObject("/Contents"): ByteStringObject(b"\x00" * 16)})
    campi = [w._add_object(DictionaryObject({
        NameObject("/FT"): NameObject("/Sig"), NameObject("/T"): TextStringObject("Firma1"),
        NameObject("/V"): w._add_object(firma)}))]
    if campo_extra:
        campi.append(w._add_object(DictionaryObject({NameObject("/FT"): NameObject("/Tx"), NameObject("/T"): TextStringObject("x")})))
    w._root_object[NameObject("/AcroForm")] = DictionaryObject({
        NameObject("/Fields"): ArrayObject(campi), NameObject("/SigFlags"): NumberObject(3)})
    if modifica:
        modifica(w)
    out = tmp_path / "firmato.pdf"
    w.write(str(out))
    dati = bytearray(out.read_bytes())
    pos = dati.index(b"/ByteRange [") + len(b"/ByteRange ")
    fine_range = dati.index(b"]", pos) + 1
    larghezza = len(f"[0 {0:010d} {0:010d} {0:010d}]")
    dati[pos:fine_range] = b" " * larghezza                  # larghezza fissa: gli offset del file non si spostano
    ini = dati.index(b"/Contents <") + len(b"/Contents ")
    fine = dati.index(b">", ini) + 1
    resto = len(dati) - fine if coerente else len(dati)          # incoerente: oltre la fine del file
    dati[pos:pos + larghezza] = f"[0 {ini:010d} {fine:010d} {resto:010d}]".encode()
    out.write_bytes(bytes(dati))
    return str(out)


def test_pdf_firmato_pades_resta_valido_e_la_firma_e_segnalata(tmp_path):
    base = crea_pdf(carica(), str(tmp_path / "r.pdf"))
    v = verifica_file(_firmato(tmp_path, base), [CHIAVI])
    assert v["esito"] == "VALIDO", v["motivi"]
    assert v["firme_pades"] == [{"campo": "Firma1", "formato": "/ETSI.CAdES.detached"}]
    assert any("non verificata dal Verificatore" in m for m in v["motivi"])
    assert v["grafica_pdf"] == "corrisponde ai dati" and v["testo_pdf"] == "corrisponde ai dati"


def test_firma_con_intervallo_incoerente_e_alterato(tmp_path):
    base = crea_pdf(carica(), str(tmp_path / "r.pdf"))
    v = verifica_file(_firmato(tmp_path, base, coerente=False), [CHIAVI])
    assert v["esito"] == "ALTERATO" and any("non coerente" in m for m in v["motivi"])


def test_firma_non_nasconde_un_campo_modulo(tmp_path):
    base = crea_pdf(carica(), str(tmp_path / "r.pdf"))
    v = verifica_file(_firmato(tmp_path, base, campo_extra=True), [CHIAVI])
    assert v["esito"] == "ALTERATO" and any("/AcroForm" in m for m in v["motivi"])


def test_firma_non_copre_un_contenuto_cambiato_nella_stessa_revisione(tmp_path):
    from pypdf.generic import DecodedStreamObject, NameObject
    base = crea_pdf(carica(), str(tmp_path / "r.pdf"))

    def cambia(w):
        c = w.pages[0]["/Contents"]
        c = c[0].get_object() if isinstance(c, list) else c.get_object()
        d = DecodedStreamObject()
        d.set_data(c.get_data() + b"\n1 1 1 rg 0 0 600 800 re f\n")      # rettangolo bianco sopra la pagina
        w.pages[0][NameObject("/Contents")] = w._add_object(d)
    v = verifica_file(_firmato(tmp_path, base, modifica=cambia), [CHIAVI])
    assert v["esito"] == "ALTERATO", v["motivi"]
    assert v["grafica_pdf"] == "diversa dai dati"
