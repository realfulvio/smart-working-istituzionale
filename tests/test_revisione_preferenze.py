"""Contratti M6: scelta esplicita AI, PDF /4 completo e preferenze personali."""
import copy
import io
import json
from pathlib import Path
from pypdf import PdfReader
from resoconto.pdf import pdf_bytes, crea_pdf, NOME_ALLEGATO
from resoconto.verifica import verifica_file
from aggregatore import sigillo
from tests.test_servizio import srv, T
from redattore import sintesi

ROOT = Path(__file__).resolve().parents[1]

def test_testo_standard_non_avvia_motore(srv):
    srv.registra_informativa("Rossi Maria (ESEMPIO)", "Ufficio dimostrativo")
    g=srv.avvia(); srv.orologio.t=T("13:00"); srv.chiudi()
    def forbidden(doc): raise AssertionError("AI non richiesta")
    srv._motore_factory=forbidden
    assert srv.genera(g, usa_ai=False)["origine_testo"]=="testo_standard"
    assert srv.riscrivi(g, usa_ai=False)["origine_testo"]=="testo_standard"

def test_preferenze_non_esportano_policy(srv,tmp_path):
    srv.salva_preferenze("Rossi Maria (ESEMPIO)","Ufficio dimostrativo",str(tmp_path/"pdf2"))
    personal=json.loads(Path(srv.p.base,"impostazioni.json").read_text(encoding="utf-8"))
    assert personal=={"cartella_pdf":str(tmp_path/"pdf2")}
    assert srv.dipendente()["nome"]=="Rossi Maria (ESEMPIO)"

def test_pdf_schema5_sigilli_lingua_fasce_provenienza(tmp_path):
    doc=json.loads((ROOT/"examples/istituzionale/ordinaria/giorno.json").read_text(encoding="utf-8"))
    from resoconto.identita import snapshot
    doc["identita_documento"] = snapshot()
    doc["sintesi_ai"]=sintesi.genera(doc,None,adesso="2026-10-05T14:00:00+02:00")
    # Chiavi temporanee, nessuna chiave privata nel repository.
    key=sigillo.load_or_create_key(str(tmp_path/"chiave"))
    doc=sigillo.seal_technical(doc,key)
    doc["sintesi_ai"]["verificata_dal_dipendente"]=True
    doc["sintesi_ai"]["verificata_il"]="2026-10-05T14:05:00+02:00"
    doc=sigillo.seal_final(doc,key)
    path=crea_pdf(doc,str(tmp_path/"example.pdf"))
    reader=PdfReader(path)
    assert reader.trailer["/Root"]["/Lang"]=="it"
    assert json.loads(reader.attachments[NOME_ALLEGATO][0])==doc
    text="\n".join(p.extract_text() for p in reader.pages)
    for f in doc["fasce"]: assert f["ora"] in text
    for label in ("Dichiarato","Rilevato","Nota metodologica","Sigillo finale"): assert label in text
    assert verifica_file(path)["esito"]=="INTEGRO"
    assert verifica_file(path,[str(tmp_path/"chiave")])["esito"]=="VALIDO"
    assert pdf_bytes(doc)==pdf_bytes(doc)
