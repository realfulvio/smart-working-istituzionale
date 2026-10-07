"""PDF M5 approvato: riepilogo, fasce complete, metodo e sigilli. Paginazione variabile."""
from __future__ import annotations
import io
import json
import os
from html import escape
from pathlib import Path
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, PageBreak, Spacer, KeepTogether, Flowable
from . import VERSIONE_APP, ente
from .tokens import carica
from .formati import Giornata, ST_LAB, MANUALI, ORIGINE_SINTESI, data_breve, avviso_leggibile

NOME_ALLEGATO = "resoconto.json"
ASSETS = Path(__file__).resolve().parents[1] / "applicazione/assets"

def pdf_bytes(doc: dict, filigrana: str | None = None) -> bytes:
    """PDF senza allegato; nessuna modifica ai dati sigillati."""
    assets = Path(ASSETS) / "fonts"
    for name, fn in (("TW", "TitilliumWeb-Regular.ttf"), ("TW-B", "TitilliumWeb-Bold.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(assets / fn)))
    from reportlab.lib.fonts import addMapping
    addMapping("TW", 0, 0, "TW"); addMapping("TW", 1, 0, "TW-B")
    t = carica(); identity = ente.carica(); g = Giornata(doc)
    stamped=doc.get("identita_documento")
    if stamped:
        import hashlib
        actual=hashlib.sha256(Path(identity["logo"]).read_bytes()).hexdigest() if identity["logo"] else None
        if actual != stamped["logo_sha256"]:
            raise ValueError("Serve il logo dell’identità originale per confrontare la grafica del documento")
        t=stamped["token"];identity.update(nome=stamped["nome"],sottotitolo=stamped["sottotitolo"])
    body = ParagraphStyle("body", fontName="TW", fontSize=10, leading=13, spaceAfter=8, textColor=HexColor(t["text"]))
    title = ParagraphStyle("title", parent=body, fontName="TW-B", fontSize=23, leading=28, spaceAfter=14)
    head = ParagraphStyle("head", parent=body, fontName="TW-B", fontSize=14, leading=18, spaceBefore=10, spaceAfter=8, keepWithNext=True)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=10, spaceAfter=4)
    story = []
    def para(text, style=body):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)
    def p(text, style=body):
        story.append(para(text, style))
    class Riquadro(Flowable):
        def __init__(self,label,text,color):
            super().__init__(); self.label=para(label,head);self.text=para(text);self.color=color
        def wrap(self,aw,ah):
            self.width=aw
            _,a=self.label.wrap(aw-28,ah);_,b=self.text.wrap(aw-28,ah)
            self.h_label=a;self.height=a+b+30
            return aw,self.height
        def split(self,aw,ah):
            import copy
            _,lh=self.label.wrap(aw-28,ah)
            parts=self.text.split(aw-28,max(0,ah-lh-30))
            if len(parts)<2:return []
            result=[]
            for part in parts:
                item=copy.copy(self);item.text=part;result.append(item)
            return result
        def draw(self):
            c=self.canv;c.setFillColor(HexColor(t[self.color]));c.setStrokeColor(HexColor(t["border"]))
            c.roundRect(0,0,self.width,self.height,8,fill=1,stroke=1)
            self.label.drawOn(c,14,self.height-self.h_label-12)
            self.text.drawOn(c,14,12)
    def box(label,text,color):
        story.append(Riquadro(label,text,color));story.append(Spacer(1,10))
    def table(labels, rows, widths):
        data = [[para(x, small) for x in labels]] + [[para(x, small) for x in r] for r in rows]
        tab = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
        tab.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), HexColor(t["primary-tint-1"])),
                                ("ROWBACKGROUNDS", (0,1), (-1,-1), [HexColor(t["surface"]),HexColor(t["surface-alt"])]),
                                ("VALIGN", (0,0), (-1,-1), "TOP"), ("LINEBELOW", (0,0), (-1,-1), .3, HexColor(t["border"])),
                                ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5)]))
        story.append(tab)
    dip = doc.get("dipendente") or {}
    cats = sorted({g.cat(c) for f in doc["fasce"] for c in f.get("categorie", []) if c not in ("rete", "sessione", "postazione")})
    p("La giornata in un documento.", title)
    p(f"{dip.get('nome') or 'Nome non indicato'} · {dip.get('ufficio') or 'Ufficio non indicato'}")
    p(f"Giornata del {data_breve(doc['giorno'])}")
    box("A · Dati rilevati automaticamente", "Categorie rilevate: " + (", ".join(cats) or "nessuna") + ". I segnali descrivono il contesto tecnico, senza dedurre durata o qualità del lavoro.", "primary-tint-1")
    manuali = doc.get("manuali", [])
    box("B · Attività dichiarate dal dipendente", "\n".join(f"{m['inizio'][11:16]}–{m['fine'][11:16]} · {MANUALI.get(m['categoria'],m['categoria'])} · {m.get('descrizione') or 'Senza descrizione'}" for m in manuali[:6]) + ("\nAltre dichiarazioni nel dettaglio." if len(manuali)>6 else "") or "Nessuna attività dichiarata.", "surface-alt")
    box("C · Osservazioni del dipendente", (doc.get("osservazioni_dipendente") or "Nessuna osservazione.")[:250], "surface-alt")
    s = doc.get("sintesi_ai") or {}
    text_sintesi=s.get("testo") or "La sintesi non è stata generata."
    if s.get("frasi") and s.get("origine_testo") != "dichiarata":
        facts={f["id"]:f for f in s.get("fatti",[])}
        labels={"automatico":"Rilevato","dichiarato":"Dichiarato","osservazione":"Osservazione"}
        lines=[]
        for phrase in s["frasi"]:
            origins=sorted({facts[i]["origine"] for i in phrase.get("fatti",[]) if i in facts and facts[i].get("tipo")!="giorno"})
            lines.append((" / ".join(labels.get(o,o) for o in origins) or "Contesto")+": "+phrase["testo"])
        text_sintesi="\n".join(lines)
    box("D · Sintesi · "+ORIGINE_SINTESI.get(s.get("origine_testo"),"non presente"),text_sintesi,"primary-tint-1")
    p("Come leggere il documento",head)
    p("Nessuna attività informatica rilevata non significa assenza di lavoro. Dettaglio per fasce, nota metodologica, dati tecnici della postazione e sigilli nelle pagine successive.",small)
    story.append(PageBreak())
    p("Dettaglio della giornata", title)
    p(f"A · Fasce di {g.t['durata_fascia_min']} minuti · dati automatici in sola lettura", head)
    p("Tutte le fasce del JSON sono riportate, comprese quelle senza dati. Le applicazioni contemporanee non si sommano.")
    p(f"Nessuna attività informatica rilevata: {g.t['fasce_per_stato'].get('nessuna_attivita_informatica_rilevata',0)} fasce. È un dato tecnico, senza deduzioni sul lavoro.", small)
    rows = []
    for f in doc["fasce"]:
        end = f["fine"][11:16]
        if end == "00:00" and f is doc["fasce"][-1]: end = "24:00"
        context = ", ".join(sorted({g.cat(c) for c in f.get("categorie", [])})) or "—"
        rows.append((f"{f['ora']}–{end}", ST_LAB.get(f["stato"], f["stato"]), context))
    table(["Fascia", "Stato tecnico", "Categorie / contesto"], rows, [80,220,191])
    p("B · Dettaglio delle dichiarazioni", head)
    p("Gli orari sono indicativi, dichiarati dal dipendente. Una dichiarazione resta distinta dai segnali della stessa fascia.")
    table(["Orari dichiarati", "Categoria", "Descrizione"], [(f"{m['inizio'][11:16]}–{m['fine'][11:16]}", MANUALI.get(m['categoria'],m['categoria']), m.get('descrizione') or "—") for m in manuali] or [("—","—","Nessuna attività dichiarata")], [85,150,256])
    story.append(PageBreak())
    p("Osservazioni, metodo e conferma", title)
    p("C · Osservazioni e segnalazioni", head)
    p(doc.get("osservazioni_dipendente") or "Nessuna osservazione.")
    for obs in doc.get("segnalazioni_dipendente", []):
        p(f"Segnalazione del dipendente: {obs.get('nota') or obs.get('testo') or ''}")
    cm = s.get("controllo_modifica") or {}
    if cm.get("accettata_con_avvisi"):
        p("Avvisi del controllo confermati dal dipendente", head)
        for warning in cm.get("problemi", []): p(avviso_leggibile(warning))
    p("Nota metodologica", head)
    p("La rilevazione registra soltanto eventi tecnici consentiti durante la giornata avviata. L'aggregatore li ordina e li organizza in fasce. Rete e integrazione Halley sono disabilitate in questa edizione.")
    p("Nessuna attività informatica rilevata non significa assenza di lavoro. Telefonate, riunioni, letture su carta e attività offline possono non produrre segnali del computer.")
    p("L'AI locale, se richiesta, riformula soltanto fatti minimizzati. Rilevato, dichiarato e osservazioni mantengono provenienza distinta. Se il modello non è disponibile o il controllo non è superato si usa il testo standard.")
    post = doc.get("dati_tecnici_postazione")
    if post:
        p("Dati tecnici della postazione", head)
        p("Snapshot tecnico alla chiusura, escluso dai fatti e dalla sintesi AI. Il tipo VDI/PC fisso è una classificazione tecnica indicativa.", small)
        table(["Campo", "Valore tecnico"], [(label, post.get(key) if post.get(key) is not None else "Non disponibile")
              for key, label in (("nome_macchina", "Nome macchina"), ("tipo", "Tipo"),
                                 ("sistema_operativo", "Sistema operativo e versione"), ("processore", "Processore"), ("ram_gb", "RAM (GB)"))], [180,311])
    p("Conferma del dipendente", head)
    final = (doc.get("integrita") or {}).get("sigillo_finale") or {}
    p("Resoconto confermato dal dipendente prima della generazione del PDF." if final else "Documento di prova, non confermato.")
    p("Sigillo finale", head); p(final.get("codice") or "NON SIGILLATO")
    p("Il PDF contiene resoconto.json e sigilli Ed25519. VerificaRendiconto controlla l'integrità dei dati e la corrispondenza del PDF: VALIDO con chiave registrata, INTEGRO con chiave non registrata, ALTERATO se modificato. Il sigillo non dimostra contenuto o qualità del lavoro. La consegna è manuale.")
    def page(c, d):
        w,h = A4
        c.setFillColor(HexColor(t["primary"])); c.rect(0,h-106,w,106,fill=1,stroke=0)
        if identity.get("logo"): c.drawImage(identity["logo"],40,h-84,62,62,preserveAspectRatio=True,mask="auto")
        c.setFillColor(HexColor(t["surface"])); c.setFont("TW-B",19); c.drawString(120,h-43,identity["nome"])
        c.setFont("TW",10); c.drawString(120,h-67,"Resoconto del lavoro agile")
        c.setFillColor(HexColor(t["stemma-gold"])); c.rect(0,h-109,w,3,fill=1,stroke=0)
        c.setFillColor(HexColor(t["text-muted"])); c.setFont("TW",8)
        c.drawString(52,32,filigrana or "Documento con dati e sigilli verificabili"); c.drawRightString(w-52,32,f"Pagina {d.page}")
        c.setStrokeColor(HexColor(t["border"])); c.line(52,48,w-52,48)
    buf = io.BytesIO()
    SimpleDocTemplate(buf,pagesize=A4,leftMargin=52,rightMargin=52,topMargin=134,bottomMargin=66,
                      title=f"Resoconto attività in lavoro agile – {data_breve(doc['giorno'])}",author=dip.get("nome") or "",
                      subject=f"Smart Working Istituzionale – {identity['nome']}",creator=f"Rendiconto SW {VERSIONE_APP}").build(
        story,onFirstPage=page,onLaterPages=page,canvasmaker=lambda *a,**kw: Canvas(*a,**dict(kw,invariant=1)))
    return buf.getvalue()

def crea_pdf(doc: dict, percorso: str, filigrana: str | None = None) -> str:
    if not (doc.get("integrita") or {}).get("sigillo_finale") and not filigrana:
        raise ValueError("il resoconto non ha il sigillo finale: confermarlo prima di creare il PDF")
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, TextStringObject
    import reportlab
    w = PdfWriter(clone_from=PdfReader(io.BytesIO(pdf_bytes(doc,filigrana))))
    w._root_object[NameObject("/Lang")] = TextStringObject("it")
    w.add_attachment(NOME_ALLEGATO,json.dumps(doc,ensure_ascii=False,indent=1).encode("utf-8"))
    meta = {"/RendicontoSW": f"{VERSIONE_APP}|{'filigrana' if filigrana else 'sigillato'}|rl{reportlab.Version}"}
    if filigrana: meta["/RendicontoSWFiligrana"] = filigrana
    w.add_metadata(meta)
    tmp = percorso + ".tmp"
    with open(tmp,"wb") as f: w.write(f)
    os.replace(tmp,percorso)
    return percorso
