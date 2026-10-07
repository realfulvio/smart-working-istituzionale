"""Asset PNG della pagina 5.0: grafica originale neutra e catture sintetiche.
Uso: python tools/genera_presentazione.py
Pillow + Titillium Web del repo; offline, nessun dato del sistema o EXIF.
"""
from pathlib import Path
import json,textwrap
from PIL import Image, ImageDraw, ImageFont, ImageFilter
R=Path(__file__).resolve().parents[1];OUT=R/'docs/img'
FONT=R/'applicazione/assets/fonts'
BLUE='#0066CC';DARK='#001A4D';INK='#17324D';LIGHT='#E6EEFF';MUTED='#516579';TEAL='#006B5B';AMBER='#875000'
def font(n,bold=False):return ImageFont.truetype(str(FONT/('TitilliumWeb-Bold.ttf' if bold else 'TitilliumWeb-Regular.ttf')),n)
def base(w,h):
    im=Image.new('RGB',(w,h),'#F5F8FC');d=ImageDraw.Draw(im)
    d.rectangle((0,0,w,14),fill=BLUE)
    for x,y,r in [(w+40,-70,420),(w+90,h+180,410)]:d.ellipse((x-r,y-r,x+r,y+r),fill='#E9F0FB')
    return im,d
def text(d,xy,value,size=28,color=INK,bold=False):d.text(xy,value,font=font(size,bold),fill=color)
def wrap(d,xy,value,width,size=26,color=INK,bold=False):
    words=value.split();lines=[];line=''
    for word in words:
        attempt=(line+' '+word).strip()
        if d.textlength(attempt,font=font(size,bold))>width and line:lines.append(line);line=word
        else:line=attempt
    lines.append(line)
    for i,line in enumerate(lines):text(d,(xy[0],xy[1]+i*(size+9)),line,size,color,bold)
    return len(lines)*(size+9)
def title(d,kicker,heading,sub,w=1600):
    text(d,(72,50),kicker.upper(),23,BLUE,True);text(d,(72,94),heading,54,INK,True)
    wrap(d,(72,173),sub,w-144,29,MUTED)
def card(im,box,fill='white',radius=28):
    shadow=Image.new('RGBA',im.size);sd=ImageDraw.Draw(shadow);x,y,x2,y2=box
    sd.rounded_rectangle((x,y+8,x2,y2+8),radius,fill=(15,42,83,28));shadow=shadow.filter(ImageFilter.GaussianBlur(10))
    im.paste(shadow,(0,0),shadow);ImageDraw.Draw(im).rounded_rectangle(box,radius,fill=fill,outline='#DCE5F1',width=2)
def placed(im,file,box):
    src=Image.open(R/file).convert('RGB');src.thumbnail((box[2]-box[0],box[3]-box[1]),Image.Resampling.LANCZOS)
    im.paste(src,(box[0]+(box[2]-box[0]-src.width)//2,box[1]))
def footer(d,h):text(d,(72,h-50),'SOFTWARE PUBBLICO  /  DATI LOCALI  /  EDIZIONE NEUTRA 5.0.0',19,MUTED,True)
def save(im,name):
    # Palette adattiva senza dithering; nessun metadato personale o dipendente dal PC.
    p=OUT/name
    for n in (256,192,128):
        im.quantize(colors=n,method=Image.Quantize.MEDIANCUT,dither=Image.Dither.NONE).save(p,optimize=True)
        if p.stat().st_size<500000:break
    if p.stat().st_size>=500000:raise RuntimeError(f'{name} oltre 500 KB')
    return {'file':'docs/img/'+name,'dimensioni':list(im.size),'byte':p.stat().st_size}
def hero(w,h,social=False):
    im,d=base(w,h);scale=w/1600
    if social:
        text(d,(55,45),'SMART WORKING ISTITUZIONALE',38,INK,True)
        text(d,(55,102),'La giornata, rivista da chi l’ha vissuta.',28,BLUE)
        card(im,(45,170,995,575));placed(im,'docs/screenshots/04d_revisione_verificata.png',(59,184,980,561))
        card(im,(945,138,1230,599));placed(im,'docs/screenshots/pdf_pagina-1.png',(958,153,1217,581))
        text(ImageDraw.Draw(im),(55,601),'5.0.0  ·  Windows  ·  AI locale opzionale  ·  PDF sigillato',19,MUTED,True)
    else:
        title(d,'5.0.0 · il resoconto del lavoro agile','La giornata, rivista da chi l’ha vissuta.','Osserva poco. Organizza senza giudicare. Scrive senza inventare.')
        card(im,(62,263,1210,739));placed(im,'docs/screenshots/04d_revisione_verificata.png',(80,281,1192,720))
        card(im,(1190,225,1538,760));placed(im,'docs/screenshots/pdf_pagina-1.png',(1206,242,1522,744))
        text(ImageDraw.Draw(im),(77,750),'INTERFACCIA REALE E PDF · DATI INVENTATI · NESSUN INVIO AUTOMATICO',18,MUTED,True)
    return im
def main():
    OUT.mkdir(parents=True,exist_ok=True);manifest=[]
    manifest.append(save(hero(1600,800),'hero.png'))
    im,d=base(1600,360);title(d,'Edizione neutra · 5.0.0','Smart Working Istituzionale','Poca raccolta. Revisione del dipendente. Un PDF verificabile.');footer(d,360);manifest.append(save(im,'banner.png'))
    im,d=base(1600,670);title(d,'Dal segnale al documento','Ogni passaggio ha uno scopo.','L’AI riceve solo fatti minimizzati; la consegna del PDF resta manuale.')
    steps=[('Collector','Sessione e segnali\nnel periodo avviato'),('Aggregatore','Fasce, categorie\nnessuna classifica'),('JSON /5','Dati minimizzati\nsigillo tecnico'),('AI locale','Opzionale\n127.0.0.1'),('Revisione','Segnala, dichiara\nverifica il testo'),('PDF sigillato','Conferma finale\nVerificatore')]
    for i,(label,desc) in enumerate(steps):
        x=65+i*248;card(im,(x,282,x+222,502));dd=ImageDraw.Draw(im);text(dd,(x+18,308),label,29,BLUE,True)
        for j,line in enumerate(desc.split('\n')):text(dd,(x+18,367+j*34),line,22,MUTED)
        if i<5:
            dd.line((x+225,388,x+243,388),fill=BLUE,width=3)
            dd.polygon([(x+243,388),(x+236,381),(x+236,395)],fill=BLUE)
    text(ImageDraw.Draw(im),(75,550),'Senza AI: testo standard, poi revisione. Snapshot tecnico separato, mai nel prompt.',28,INK);footer(ImageDraw.Draw(im),670);manifest.append(save(im,'pipeline.png'))
    im,d=base(1600,840);title(d,'Un confine chiaro','Cosa registra. Cosa lascia fuori.','Solo durante una giornata avviata, fuori dalle pause e secondo la policy dell’Ente.')
    for x,color,label,rows in [(65,TEAL,'REGISTRA',['Eventi della sessione, con ora','Attività informatica: sì/no per fascia','Programmi ammessi dall’elenco CED','Attività e note dichiarate dal dipendente','Snapshot tecnico opzionale e sigillato']), (820,BLUE,'NON REGISTRA',['Tasti, testo o movimenti del mouse','Schermate e titoli delle finestre','Nomi, percorsi o contenuti dei file','Mail, destinatari, conteggi e URL','IP, MAC, SID, seriali o metriche della persona'])]:
        card(im,(x,272,x+715,725));dd=ImageDraw.Draw(im);text(dd,(x+30,300),label,35,color,True)
        for i,row in enumerate(rows):text(dd,(x+30,373+i*60),'• '+row,27,INK)
    footer(ImageDraw.Draw(im),840);manifest.append(save(im,'privacy.png'))
    im,d=base(1600,720);title(d,'I tre principi','Un resoconto, senza giudizi sulla persona.','La tecnologia rende leggibili i fatti; la revisione resta al dipendente.')
    for i,(h,t) in enumerate([('Il Collector osserva poco','Sessione e segnali ammessi. Nessun contenuto dei documenti.'),('L’Aggregator organizza, non giudica','Fasce e categorie. Nessuna durata di lavoro dedotta o classifica.'),('L’AI scrive, non inventa','Fatti minimizzati e controllo anti-invenzione. Testo standard sempre disponibile.')]):
        x=65+i*500;card(im,(x,285,x+465,596));dd=ImageDraw.Draw(im);wrap(dd,(x+28,314),h,409,35,BLUE,True);wrap(dd,(x+28,439),t,409,28,MUTED)
    footer(ImageDraw.Draw(im),720);manifest.append(save(im,'principi.png'))
    im,d=base(1600,720);title(d,'Provenienza leggibile','Tre voci, sempre riconoscibili.','Etichetta e simbolo accompagnano il colore: nessuna informazione affidata al solo movimento.')
    for i,(color,h,t,eg) in enumerate([(BLUE,'RILEVATO','Segnali automatici, in sola lettura.','Segnale: uso di Word nella fascia.'),(AMBER,'DICHIARATO','Attività e note inserite dal dipendente.','Dichiarazione: riunione di servizio.'),(TEAL,'TESTO AI','Riformulazione locale dei fatti disponibili.','Da verificare prima della conferma.')]):
        x=65+i*500;card(im,(x,284,x+465,594));dd=ImageDraw.Draw(im);dd.rounded_rectangle((x+26,312,x+437,372),16,fill=color);text(dd,(x+45,321),h,30,'white',True);wrap(dd,(x+28,401),t,409,29,INK);wrap(dd,(x+28,510),eg,409,24,MUTED)
    footer(ImageDraw.Draw(im),720);manifest.append(save(im,'provenienza.png'))
    im,d=base(1600,880);title(d,'Il flusso quotidiano','Pochi gesti. Un documento completo.','Controlli espliciti, dati locali e testo comprensibile.')
    features=[('Avvia e sospendi','La raccolta segue i comandi della giornata.'),('Dichiara le attività','Riunioni, telefonate e lavoro fuori dal PC.'),('Rivedi la sintesi','AI facoltativa oppure testo standard.'),('Personalizza l’Ente','Identità e configurazione in un overlay locale.'),('Conferma il PDF','JSON minimizzato e sigilli Ed25519.'),('Verifica il documento','VALIDO, INTEGRO, ALTERATO, NON SIGILLATO.')]
    for i,(h,t) in enumerate(features):
        x=65+(i%3)*500;y=270+(i//3)*260;card(im,(x,y,x+465,y+228));dd=ImageDraw.Draw(im);wrap(dd,(x+28,y+27),h,409,35,BLUE,True);wrap(dd,(x+28,y+105),t,409,29,MUTED)
    footer(ImageDraw.Draw(im),880);manifest.append(save(im,'funzioni.png'))
    manifest.append(save(hero(1280,640,True),'social-preview.png'))
    print(json.dumps(manifest,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
