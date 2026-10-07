"""Icone generiche a tratto, locali e decorative: etichetta sempre presente."""
from PIL import Image, ImageDraw, ImageTk

def icona(widget, categoria, colore, lato=20):
    root=widget.winfo_toplevel()
    cache=getattr(root,"_icone_categoria",{})
    root._icone_categoria=cache
    key=(categoria,colore,lato)
    if key not in cache:
        im=Image.new("RGBA",(48,48));d=ImageDraw.Draw(im)
        def line(points):d.line([(x*2,y*2) for x,y in points],fill=colore,width=3,joint="curve")
        def rect(b):d.rounded_rectangle(tuple(x*2 for x in b),radius=3,outline=colore,width=3)
        if categoria=="posta":
            rect((3,5,21,19));line([(3,6),(12,13),(21,6)])
        elif categoria=="riunione":
            d.ellipse((9,5,23,19),outline=colore,width=3);d.ellipse((27,10,37,20),outline=colore,width=3)
            line([(3,21),(3,16),(8,13),(13,13),(17,17),(17,21)]);line([(18,13),(22,17),(22,20)])
        elif categoria=="telefonata":line([(5,3),(9,7),(7,10),(14,17),(17,15),(21,19),(18,22),(11,18),(4,11),(2,6),(5,3)])
        elif categoria=="halley":
            rect((3,4,21,20));line([(3,9),(21,9)]);line([(9,9),(9,20)]);line([(13,13),(18,13)]);line([(13,16),(18,16)])
        elif categoria=="word":
            line([(6,3),(15,3),(19,7),(19,21),(6,21),(6,3)]);line([(8,11),(10,17),(12,13),(14,17),(16,11)])
        else:
            rect((3,3,21,16));line([(12,16),(12,21)]);line([(8,21),(16,21)])
        cache[key]=ImageTk.PhotoImage(im.resize((lato,lato),Image.Resampling.LANCZOS),master=root)
    return cache[key]

def categoria_da_testo(testo):
    s=testo.lower()
    for chiave,nome in (("word","word"),("posta","posta"),("outlook","posta"),("halley","halley"),("riunione","riunione"),("telefon","telefonata"),("session","sessione")):
        if chiave in s:return nome
    return "sessione"
