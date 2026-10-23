"""PDF/A-3b del resoconto e metadati del documento informatico (Linee guida AgID, allegato 5).

Il PDF/A-3 tocca solo il catalogo e i metadati del documento: profilo colore sRGB (OutputIntent), metadati XMP e
dichiarazione dell'allegato resoconto.json come file associato. Le pagine non cambiano, quindi testo e impronte
grafiche confrontati dal Verificatore restano quelli dell'impaginatore.

I metadati AgID vanno in un file XML accanto al PDF («<nome>.metadati.xml»): contengono l'impronta SHA-256 del PDF,
che il PDF non può contenere. Registrazione, classificazione e tempo di conservazione restano al sistema di protocollo
e al manuale di gestione dell'Ente.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
from xml.sax.saxutils import escape

from . import VERSIONE_PROGRAMMA

DATA_PREDEFINITA = "D:20000101000000+00'00'"     # quella di ReportLab in modalità invariante


def profilo_srgb() -> bytes:
    """Profilo ICC sRGB di littlecms (tramite Pillow) con data di creazione azzerata: stessi byte a ogni esecuzione."""
    from PIL import ImageCms
    b = bytearray(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
    b[24:36] = bytes(12)
    if any(b[84:100]):   # ID del profilo (MD5 su intestazione con flag, intento e ID azzerati)
        t = bytearray(b); t[44:48] = t[64:68] = bytes(4); t[84:100] = bytes(16)
        b[84:100] = hashlib.md5(t).digest()
    return bytes(b)


def data_pdf(iso: str | None) -> str:
    """«2026-10-05T14:30:00+02:00» → «D:20261005143000+02'00'»; senza data, quella invariante di ReportLab."""
    if not iso:
        return DATA_PREDEFINITA
    d = dt.datetime.fromisoformat(iso)
    off = d.utcoffset() or dt.timedelta(0)
    m = int(off.total_seconds()) // 60
    segno = "-" if m < 0 else "+"
    return d.strftime("D:%Y%m%d%H%M%S") + f"{segno}{abs(m) // 60:02d}'{abs(m) % 60:02d}'"


def data_xmp(pdf: str) -> str:
    """«D:20261005143000+02'00'» → «2026-10-05T14:30:00+02:00»."""
    s = pdf[2:]
    tz = s[14:].replace("'", "")
    tz = "Z" if tz in ("", "Z") else f"{tz[:3]}:{tz[3:5]}"
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}T{s[8:10]}:{s[10:12]}:{s[12:14]}{tz}"


def xmp(info: dict) -> bytes:
    """Pacchetto XMP coerente con il dizionario Info (requisito PDF/A), con identificazione PDF/A-3B."""
    e = lambda k: escape(str(info.get(k) or ""))   # noqa: E731
    testo = f"""<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:pdf="http://ns.adobe.com/pdf/1.3/">
   <pdfaid:part>3</pdfaid:part>
   <pdfaid:conformance>B</pdfaid:conformance>
   <dc:format>application/pdf</dc:format>
   <dc:title><rdf:Alt><rdf:li xml:lang="x-default">{e('/Title')}</rdf:li></rdf:Alt></dc:title>
   <dc:creator><rdf:Seq><rdf:li>{e('/Author')}</rdf:li></rdf:Seq></dc:creator>
   <dc:description><rdf:Alt><rdf:li xml:lang="x-default">{e('/Subject')}</rdf:li></rdf:Alt></dc:description>
   <dc:language><rdf:Bag><rdf:li>it</rdf:li></rdf:Bag></dc:language>
   <xmp:CreatorTool>{e('/Creator')}</xmp:CreatorTool>
   <xmp:CreateDate>{data_xmp(str(info['/CreationDate']))}</xmp:CreateDate>
   <xmp:ModifyDate>{data_xmp(str(info['/ModDate']))}</xmp:ModifyDate>
   <pdf:Producer>{e('/Producer')}</pdf:Producer>
   <pdf:Keywords>{e('/Keywords')}</pdf:Keywords>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="r"?>"""
    return testo.encode("utf-8")


def rendi_pdfa(w, nome_allegato: str, data: str) -> None:
    """Completa un PdfWriter (pypdf) con allegato già aggiunto: OutputIntent, allegato associato, XMP.
    Il dizionario Info deve essere definitivo prima della chiamata."""
    from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject,
                               TextStringObject)
    root = w._root_object
    icc = DecodedStreamObject()
    icc.set_data(profilo_srgb())
    icc = icc.flate_encode()
    icc[NameObject("/N")] = NumberObject(3)
    intento = DictionaryObject({
        NameObject("/Type"): NameObject("/OutputIntent"), NameObject("/S"): NameObject("/GTS_PDFA1"),
        NameObject("/OutputConditionIdentifier"): TextStringObject("sRGB IEC61966-2.1"),
        NameObject("/Info"): TextStringObject("sRGB IEC61966-2.1"),
        NameObject("/DestOutputProfile"): w._add_object(icc)})
    root[NameObject("/OutputIntents")] = ArrayObject([w._add_object(intento)])

    nomi = root["/Names"]["/EmbeddedFiles"]["/Names"]
    associati = ArrayObject()
    for i in range(0, len(nomi), 2):
        rif = nomi[i + 1]
        fs = rif.get_object()
        nome = str(nomi[i])
        fs[NameObject("/F")] = TextStringObject(nome)
        fs[NameObject("/UF")] = TextStringObject(nome)
        fs[NameObject("/AFRelationship")] = NameObject("/Data" if nome == nome_allegato else "/Unspecified")
        if nome == nome_allegato:
            fs[NameObject("/Desc")] = TextStringObject("Dati sigillati del resoconto (JSON), verificabili con il Verificatore")
        ef = fs["/EF"]["/F"].get_object()
        ef[NameObject("/Subtype")] = NameObject("/application/json" if nome.endswith(".json") else "/application/octet-stream")
        ef[NameObject("/Params")] = DictionaryObject({
            NameObject("/ModDate"): TextStringObject(data),
            NameObject("/Size"): NumberObject(len(ef.get_data()))})
        associati.append(rif)
    root[NameObject("/AF")] = associati

    meta = DecodedStreamObject()      # i metadati XMP non vanno compressi (ISO 19005-3, 6.6.2.1)
    meta.set_data(xmp(w.metadata))
    meta[NameObject("/Type")] = NameObject("/Metadata")
    meta[NameObject("/Subtype")] = NameObject("/XML")
    root[NameObject("/Metadata")] = w._add_object(meta)


def metadati_agid(doc: dict, percorso_pdf: str, nome_ente: str, codice_ipa: str = "") -> dict:
    """Metadati del documento informatico (Linee guida AgID, allegato 5) noti al momento della creazione.
    I campi della registrazione e della classificazione li assegna il sistema di protocollo dell'Ente."""
    with open(percorso_pdf, "rb") as f:
        impronta = hashlib.sha256(f.read()).hexdigest()
    sf = (doc.get("integrita") or {}).get("sigillo_finale") or {}
    dip = doc.get("dipendente") or {}
    giorno = dt.date.fromisoformat(doc["giorno"]).strftime("%d/%m/%Y")
    return {
        "IdDoc": {"Impronta": impronta, "Algoritmo": "SHA-256", "Identificativo": sf.get("codice") or ""},
        "ModalitaDiFormazione": "a",   # creazione tramite software
        "TipologiaDocumentale": "Resoconto giornaliero del lavoro agile",
        "Soggetti": {"Ruolo": "Autore", "Nome": dip.get("nome") or "", "Ufficio": dip.get("ufficio") or "",
                     "Amministrazione": nome_ente, "CodiceIPA": codice_ipa},
        "ChiaveDescrittiva": {"Oggetto": f"Resoconto attività in lavoro agile del {giorno}",
                              "ParoleChiave": "lavoro agile; resoconto giornaliero"},
        "Allegati": {"NumeroAllegati": 1,
                     "IndiceAllegati": "resoconto.json (dati sigillati, file associato interno al PDF/A-3)"},
        "Riservato": "true",
        "IdentificativoDelFormato": {"Formato": "application/pdf (PDF/A-3b)",
                                     "ProdottoSoftware": f"Smart Working Istituzionale {VERSIONE_PROGRAMMA}"},
        "Verifica": {"FirmatoDigitalmente": "false", "SigillatoElettronicamente": "false",
                     "MarcaturaTemporale": "false", "ConformitaCopieImmagineSuSupportoInformatico": "false"},
        "NomeDelDocumento": os.path.basename(percorso_pdf),
        "VersioneDelDocumento": "1",
        "DataCreazione": sf.get("creato_il") or "",
        "Note": ("Il documento contiene sigilli Ed25519 dell'applicazione, verificabili con il Verificatore: non sono "
                 "firme o sigilli elettronici qualificati. Registrazione, classificazione e tempo di conservazione "
                 "sono assegnati dal sistema di protocollo e dal manuale di gestione dell'Ente."),
    }


def _xml(nome: str, v, rientro: str) -> str:
    if isinstance(v, dict):
        figli = "".join(_xml(k, x, rientro + "  ") for k, x in v.items())
        return f"{rientro}<{nome}>\n{figli}{rientro}</{nome}>\n"
    return f"{rientro}<{nome}>{escape(str(v))}</{nome}>\n"


def scrivi_metadati(doc: dict, percorso_pdf: str, nome_ente: str, codice_ipa: str = "") -> str:
    """Scrive «<nome del PDF senza .pdf>.metadati.xml» accanto al PDF e ne restituisce il percorso."""
    m = metadati_agid(doc, percorso_pdf, nome_ente, codice_ipa)
    corpo = "".join(_xml(k, v, "  ") for k, v in m.items())
    testo = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             "<!-- Metadati del documento informatico (Linee guida AgID, allegato 5), precompilati dal programma. -->\n"
             f"<MetadatiDocumentoInformatico>\n{corpo}</MetadatiDocumentoInformatico>\n")
    base = percorso_pdf[:-4] if percorso_pdf.lower().endswith(".pdf") else percorso_pdf
    out = base + ".metadati.xml"
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(testo)
    os.replace(tmp, out)
    return out
