"""PDF del resoconto giornaliero dal JSON con sigillo finale (impaginazione delle bozze M2 approvate, 7 pagine A4).

  from resoconto.pdf import crea_pdf
  crea_pdf(doc_finale, "resoconto.pdf")

Solo ReportLab (puro Python) e pypdf per allegare il JSON: nessun browser, nessun programma esterno. Uscita
deterministica (stesso JSON -> stesso testo): il verificatore rigenera il PDF e confronta il testo pagina per pagina.
Il JSON con i sigilli viene allegato al PDF come «resoconto.json».
"""
from __future__ import annotations

import io
import json
import os

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from . import ente_neutro as _ente
VERSIONE_APP = "4.1.0"
from .formati_410 import (avviso_leggibile, CAMPI_SEGNALAZIONE, COLORI_STATO, COPERTURA, EVENTI, FONTI, MANUALI, ORIGINE_SINTESI, STATI,
                      ST_BREVE, ST_LAB, TESTO_SU_STATO, Giornata, data_breve, data_lunga, hm, minuti_da, ora, ts_breve)

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "applicazione", "assets")
W, H = A4
M = 16 * mm                       # margine
CW = W - 2 * M                    # larghezza utile
C = {k: HexColor(v) for k, v in {
    "primary": "#005e8e", "dark": "#001a4d", "tint": "#e6eeff", "tint2": "#f0f6fb", "azure": "#0095da",
    "gold": "#c2912c", "text": "#191919", "muted": "#455a64", "line": "#dfe5ea", "bg": "#f4f7fa",
    "decl": "#b9861f", "decl_bg": "#fcf5e6", "decl_txt": "#6e4b0c", "decl_bd": "#ecd6a8", "ok": "#00744a",
    "ok_bg": "#e5f3ec", "warn": "#8a4b00", "warn_bg": "#fff4e0", "ai": "#3b3f9e", "ai_bg": "#eef0ff",
    "bar_bg": "#e6ebf0", "s_nes": "#c9dbe8"}.items()}
_LOGO = _ente.carica()["logo"]
_COL = _ente.carica()["colori"]
C.update({k: HexColor(v) for k, v in {"primary": _COL["primario"], "dark": _COL["scuro"], "tint": _COL["tenue"],
                                      "gold": _COL["accento"]}.items()})
TOT_PAGINE = 7
_FONT_OK = False


def _font():
    global _FONT_OK
    if _FONT_OK:
        return
    f = os.path.join(ASSETS, "fonts")
    for nome, file in (("TW", "TitilliumWeb-Regular.ttf"), ("TW-B", "TitilliumWeb-Bold.ttf"),
                       ("TW-SB", "TitilliumWeb-SemiBold.ttf"), ("TW-I", "TitilliumWeb-Italic.ttf"),
                       ("TW-L", "TitilliumWeb-Light.ttf"), ("Mono", "RobotoMono-Regular.ttf")):
        if nome not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(nome, os.path.join(f, file)))
    from reportlab.lib.fonts import addMapping
    addMapping("TW", 0, 0, "TW"); addMapping("TW", 1, 0, "TW-B"); addMapping("TW", 0, 1, "TW-I"); addMapping("TW", 1, 1, "TW-B")
    _FONT_OK = True


def _ts_completo(ts) -> str:
    if not ts:
        return "—"
    import datetime as _dt
    t = _dt.datetime.fromisoformat(ts)
    off = ts[19:] if len(ts) > 19 else ""
    return f"{t:%d/%m/%Y %H:%M:%S}" + (f" ({off})" if off else "")


def _fasce(n) -> str:
    return f"{n} fascia" if n == 1 else f"{n} fasce"


def esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Pdf:
    def __init__(self, doc: dict, out, filigrana: str | None = None):
        _font()
        self.d, self.g = doc, Giornata(doc)
        self.c = canvas.Canvas(out, pagesize=A4, invariant=1, pageCompression=1)
        self.c.setTitle(f"Resoconto attività in lavoro agile – {data_breve(doc['giorno'])}")
        self.c.setAuthor((doc.get("dipendente") or {}).get("nome") or "")
        self.c.setSubject(f"Smart Working Istituzionale – {_ente.carica()['nome']}")
        self.c.setCreator(f"Rendiconto SW {VERSIONE_APP} – powered by Accorsi Luca")
        self.fil = filigrana
        self.n = 0
        sf = (doc.get("integrita") or {}).get("sigillo_finale") or {}
        self.codice = sf.get("codice") or "NON SIGILLATO"
        self.dip = (doc.get("dipendente") or {}).get("nome") or (doc.get("dipendente") or {}).get("account", "")
        self.uff = (doc.get("dipendente") or {}).get("ufficio") or ""

    # ------------------------------------------------------------------------------------------- primitive
    def Y(self, y):                 # y dall'alto (pt) -> coordinate ReportLab
        return H - y

    def rect(self, x, y, w, h, fill=None, stroke=None, r=0, lw=0.6):
        c = self.c
        if fill is not None:
            c.setFillColor(fill)
        if stroke is not None:
            c.setStrokeColor(stroke); c.setLineWidth(lw)
        if r:
            c.roundRect(x, self.Y(y + h), w, h, r, fill=fill is not None, stroke=stroke is not None)
        else:
            c.rect(x, self.Y(y + h), w, h, fill=fill is not None, stroke=stroke is not None)

    def tratteggio(self, x, y, w, h, base, riga):
        c = self.c
        c.saveState()
        p = c.beginPath(); p.rect(x, self.Y(y + h), w, h); c.clipPath(p, stroke=0, fill=0)
        c.setFillColor(base); c.rect(x, self.Y(y + h), w, h, fill=1, stroke=0)
        c.setStrokeColor(riga); c.setLineWidth(1.2)
        k = -h
        while k < w:
            c.line(x + k, self.Y(y + h), x + k + h, self.Y(y)); k += 4
        c.restoreState()

    def stato(self, x, y, w, h, st):
        if st == "raccolta_sospesa":
            self.tratteggio(x, y, w, h, HexColor("#f3eee0"), HexColor("#c9b48a"))
        elif st == "dato_non_disponibile":
            self.tratteggio(x, y, w, h, white, HexColor("#dfe5ea"))
        else:
            self.rect(x, y, w, h, fill=HexColor(COLORI_STATO[st]))

    def t(self, x, y, s, font="TW", size=9, color=None, align="l"):
        c = self.c
        c.setFont(font, size); c.setFillColor(color or C["text"])
        s = str(s)
        if align == "r":
            c.drawRightString(x, self.Y(y), s)
        elif align == "c":
            c.drawCentredString(x, self.Y(y), s)
        else:
            c.drawString(x, self.Y(y), s)

    def tw(self, s, font="TW", size=9):
        return pdfmetrics.stringWidth(str(s), font, size)

    def taglia(self, s, w, font="TW", size=9):
        s = str(s)
        if self.tw(s, font, size) <= w:
            return s
        while s and self.tw(s + "…", font, size) > w:
            s = s[:-1]
        return s + "…"

    def par(self, x, y, w, testo, size=9, color=None, font="TW", leading=None, align=0) -> float:
        """Paragrafo con a capo (markup ReportLab); restituisce l'altezza."""
        st = ParagraphStyle("p", fontName=font, fontSize=size, leading=leading or size * 1.42,
                            textColor=color or C["text"], alignment=align)
        p = Paragraph(testo, st)
        _, h = p.wrap(w, 2000)
        p.drawOn(self.c, x, self.Y(y + h))
        return h

    def spunta(self, x, y, lato, colore=white, lw=1.3):
        """Segno di spunta disegnato (il carattere ✓ non è nel font Titillium)."""
        c = self.c
        c.setStrokeColor(colore); c.setLineWidth(lw); c.setLineCap(1); c.setLineJoin(1)
        p = c.beginPath()
        p.moveTo(x + lato * 0.18, self.Y(y + lato * 0.52)); p.lineTo(x + lato * 0.42, self.Y(y + lato * 0.76))
        p.lineTo(x + lato * 0.84, self.Y(y + lato * 0.26))
        c.drawPath(p, stroke=1, fill=0)

    def tag(self, x, y, testo, tipo="auto", size=7, spunta=False) -> float:
        fg, bg, bd = {"auto": (C["primary"], C["tint2"], None), "decl": (C["decl_txt"], C["decl_bg"], C["decl_bd"]),
                      "ai": (C["ai"], C["ai_bg"], None), "flag": (C["warn"], C["warn_bg"], None),
                      "ok": (C["ok"], C["ok_bg"], None), "std": (C["muted"], HexColor("#eef1f4"), None)}[tipo]
        extra = size + 2 if spunta else 0
        w = self.tw(testo, "TW-B", size) + 8 + extra
        self.rect(x, y - size - 1.5, w, size + 5, fill=bg, stroke=bd, r=2, lw=0.5)
        if spunta:
            self.spunta(x + 3, y - size, size, fg, 1.1)
        self.t(x + 4 + extra, y + 1.2, testo, "TW-B", size, fg)
        return w

    def sezione(self, y, testo, extra=None) -> float:
        self.rect(M, y - 9, 2.6, 12, fill=C["gold"], r=1)
        w = self.tw(testo, "TW-B", 11.5)
        self.t(M + 8, y, testo, "TW-B", 11.5, C["dark"])
        if extra:
            self.tag(M + 14 + w, y - 1, *extra)
        return y + 14

    def titolo(self, n, testo, destra):
        y = 92
        self.t(M, y, str(n), "TW-B", 17, C["gold"])
        self.t(M + 14, y, testo, "TW-B", 17, C["dark"])
        self.t(W - M, y - 2, destra, "TW", 8.5, C["muted"], "r")
        self.c.setStrokeColor(C["primary"]); self.c.setLineWidth(0.8)
        self.c.line(M, self.Y(y + 8), W - M, self.Y(y + 8))
        return y + 24

    def info(self, x, y, w, testo, size=7.6) -> float:
        self.c.setStrokeColor(C["muted"]); self.c.setLineWidth(0.6)
        self.c.circle(x + 4.5, self.Y(y + 4.5), 4.2, stroke=1, fill=0)
        self.t(x + 4.5, y + 7.2, "i", "TW-B", 7, C["muted"], "c")
        return self.par(x + 13, y, w - 13, testo, size, C["muted"])

    def tabella(self, y, colonne, righe, zebra=None, alt=17, size=8.6, testa=True) -> float:
        """colonne: [(titolo, larghezza, allineamento)]; righe: liste di valori (str o callable(x, y, w))."""
        x0 = M
        if testa:
            x = x0
            for tit, w, al in colonne:
                xx = x + (w - 4 if al == "r" else 4)
                self.t(xx, y + 9, tit.upper(), "TW-B", 6.6, C["primary"], al)
                x += w
            self.c.setStrokeColor(C["primary"]); self.c.setLineWidth(0.7)
            self.c.line(x0, self.Y(y + 14), x0 + sum(c[1] for c in colonne), self.Y(y + 14))
            y += 14
        for i, r in enumerate(righe):
            h = alt
            if zebra and zebra(i):
                self.rect(x0, y, sum(c[1] for c in colonne), h, fill=zebra(i))
            x = x0
            for (tit, w, al), v in zip(colonne, r):
                if callable(v):
                    v(x, y, w)
                else:
                    font = "TW-B" if isinstance(v, tuple) else "TW"
                    v = v[0] if isinstance(v, tuple) else v
                    xx = x + (w - 4 if al == "r" else 4)
                    self.t(xx, y + h / 2 + 3.2, self.taglia(v, w - 8, font, size), font, size, C["text"], al)
                x += w
            self.c.setStrokeColor(C["line"]); self.c.setLineWidth(0.5)
            self.c.line(x0, self.Y(y + h), x0 + sum(c[1] for c in colonne), self.Y(y + h))
            y += h
        return y

    def qr(self, x, y, lato):
        dato = f"RENDICONTO-SW|1|{self.d['giorno']}|{self.codice}|" + \
               (((self.d.get("integrita") or {}).get("sigillo_finale") or {}).get("sha256") or "")
        w = QrCodeWidget(dato, barLevel="M")
        b = w.getBounds()
        bw, bh = b[2] - b[0], b[3] - b[1]
        w.barFillColor = C["dark"]
        dr = Drawing(lato, lato, transform=[lato / bw, 0, 0, lato / bh, 0, 0])
        dr.add(w)
        renderPDF.draw(dr, self.c, x, self.Y(y + lato))

    # ------------------------------------------------------------------------------------------- cornice
    def nuova_pagina(self, titolo_breve=None):
        if self.n:
            self.c.showPage()
        self.n += 1
        c = self.c
        if self.n == 1:
            self.rect(0, 0, W, 104, fill=C["primary"])
            self.rect(0, 104, W, 3, fill=C["gold"])
            x0 = M
            if _LOGO:
                c.setFillColor(white); c.circle(M + 26, self.Y(52), 28, fill=1, stroke=0)
                c.drawImage(_LOGO, M + 4, self.Y(74), 44, 44, mask="auto")
                x0 = M + 70
            self.t(x0, 54, _ente.carica()["nome"].upper(), "TW-B", 19, white)
            if _ente.carica()["sottotitolo"]:
                self.t(x0, 72, _ente.carica()["sottotitolo"], "TW", 9.5, C["tint"])
            self.t(W - M, 42, self.uff, "TW", 8.5, C["tint"], "r")
            self.t(W - M, 56, "Resoconto giornaliero · lavoro agile", "TW-B", 9.5, white, "r")
            self.t(W - M, 70, data_lunga(self.d["giorno"]), "TW", 8.5, C["tint"], "r")
        else:
            self.rect(0, 0, W, 3, fill=C["primary"])
            x1 = M
            if _LOGO:
                c.drawImage(_LOGO, M, self.Y(52), 26, 26, mask="auto")
                x1 = M + 34
            self.t(x1, 36, _ente.carica()["nome"].upper(), "TW-B", 10, C["dark"])
            self.t(x1, 47, "Resoconto attività in lavoro agile", "TW", 8, C["muted"])
            c.setFont("TW-B", 8)
            nm = esc(self.dip)
            self.par(W / 2, 28, W / 2 - M, f"<b>{nm}</b> · {esc(self.uff)}", 8, C["text"], align=2)
            self.t(W - M, 47, f"{data_lunga(self.d['giorno'])} · {titolo_breve}", "TW", 8, C["muted"], "r")
            c.setStrokeColor(C["line"]); c.setLineWidth(0.6); c.line(0, self.Y(60), W, self.Y(60))
        if self.fil:
            c.saveState(); c.setFillColor(HexColor("#c2912c")); c.setFillAlpha(0.10)
            c.translate(W / 2, H / 2); c.rotate(38); c.setFont("TW-B", 54)
            c.drawCentredString(0, -18, self.fil); c.restoreState()
        # piè di pagina
        c.setStrokeColor(C["line"]); c.setLineWidth(0.6); c.line(M, 30, W - M, 30)
        self.t(M, H - 18, f"Rendiconto SW {VERSIONE_APP} · resoconto del {data_breve(self.d['giorno'])} · codice {self.codice}",
               "TW", 6.8, C["muted"])
        self.t(W / 2 + 20, H - 18, f"Pagina {self.n} di {TOT_PAGINE}", "TW-B", 7.2, C["dark"], "c")
        self.t(W - M, H - 18, "powered by Accorsi Luca", "TW", 6.8, HexColor("#6b7c88"), "r")

    def timeline(self, y, h=26, h0=None, h1=None) -> float:
        g = self.g
        a0, a1 = (h0, h1) if h0 is not None else g.ore_estremi()
        span = (a1 - a0) * 60
        x0, w = M, CW
        self.rect(x0, y, w, h, fill=HexColor("#f7f9fb"), stroke=C["line"], r=2)
        for f in g.fasce:
            a = minuti_da(f["inizio"]) - a0 * 60
            if 0 <= a < span:
                self.stato(x0 + a / span * w, y + 1, 15 / span * w + 0.3, h - 9, f["stato"])
        for m in self.d.get("manuali", []):
            a = max(0, minuti_da(m["inizio"]) - a0 * 60)
            b = min(span, (minuti_da(m["fine"]) or 1440) - a0 * 60)
            if b > a:
                self.rect(x0 + a / span * w, y + h - 6.5, (b - a) / span * w, 5, fill=C["decl"], r=1.5)
        for n in sorted(g.segnalate()):
            a = minuti_da(g.fasce[n]["inizio"]) - a0 * 60
            if 0 <= a < span:
                self.c.setFillColor(HexColor("#e08a00"))
                self.c.circle(x0 + (a + 7.5) / span * w, self.Y(y + 5), 2.2, fill=1, stroke=0)
        self.c.setStrokeColor(HexColor("#ffffff")); self.c.setLineWidth(0.8)
        for k in range(1, a1 - a0):
            self.c.line(x0 + k * 60 / span * w, self.Y(y + 1), x0 + k * 60 / span * w, self.Y(y + h - 8))
        passo = 1 if a1 - a0 <= 10 else 2
        for k in range(0, a1 - a0 + 1, passo):
            self.t(x0 + k * 60 / span * w, y + h + 9, f"{a0 + k:02d}:00", "TW", 7, C["muted"],
                   "l" if k == 0 else "r" if k == a1 - a0 else "c")
        return y + h + 12

    def legenda(self, y, chiavi=None, decl=True) -> float:
        chiavi = chiavi or [k for k, _, _ in STATI]
        x = M
        voci = [(k, ST_LAB[k]) for k in chiavi] + ([("decl", "Attività dichiarate dal dipendente")] if decl else [])
        for k, lab in voci:
            w = 12 + self.tw(lab, "TW", 7.4) + 12
            if x + w > W - M:
                x, y = M, y + 12
            if k == "decl":
                self.rect(x, y - 6.5, 8, 8, fill=C["decl"], r=1.5)
            else:
                self.stato(x, y - 6.5, 8, 8, k)
                if k in ("sessione_chiusa", "dato_non_disponibile"):
                    self.rect(x, y - 6.5, 8, 8, stroke=C["line"], lw=0.4)
            self.t(x + 11, y + 0.5, lab, "TW", 7.4, C["muted"])
            x += w
        return y + 12

    # ------------------------------------------------------------------------------------------- pagine
    def p1(self):
        d, g = self.d, self.g
        self.nuova_pagina()
        y = 132
        self.t(M, y, "RESOCONTO GIORNALIERO", "TW-B", 7.5, C["primary"]); y += 22
        self.t(M, y, "Resoconto attività in lavoro agile", "TW-B", 21, C["dark"]); y += 14
        self.t(M, y, f"{data_lunga(d['giorno'])} · documento generato dalla postazione e verificato dal dipendente",
               "TW", 8.6, C["muted"]); y += 12
        # dati della giornata
        self.c.setStrokeColor(C["primary"]); self.c.setLineWidth(1); self.c.line(M, self.Y(y), W - M, self.Y(y))
        a, b = g.orario_sessione()
        cols = [("Dipendente", self.dip, 0.34), ("Ufficio", self.uff or "—", 0.26), ("Data", data_breve(d["giorno"]), 0.2),
                ("Orario della sessione", f"{a} – {b}", 0.2)]
        x = M
        for k, v, fr in cols:
            self.t(x + 4, y + 11, k.upper(), "TW-B", 6.6, C["primary"])
            self.t(x + 4, y + 26, self.taglia(v, CW * fr - 8, "TW-SB", 10.5), "TW-SB", 10.5, C["text"])
            x += CW * fr
        y += 36
        self.c.setStrokeColor(C["line"]); self.c.line(M, self.Y(y), W - M, self.Y(y)); y += 10
        # indicatori
        t = g.t
        # Bonifica B4: niente tempi totali né «tempo complessivo»: fasce e numero di attività dichiarate
        kpi = [("Attività al computer", ("rilevato", "auto"), _fasce(t["fasce_per_stato"]["attivita_rilevata"]),
                "da 15 minuti" + (f" · {t['prima_attivita']}–{t['ultima_attivita']}" if t.get("prima_attivita") else ""),
                "auto"),
               ("Fuori dal computer", ("dichiarato", "decl"), str(len(d.get("manuali", []))),
                "attività dichiarate dal dipendente", "decl")]
        gap = 8
        kw = (CW - (len(kpi) - 1) * gap) / len(kpi)
        for i, (tit, tg, val, sub, tipo) in enumerate(kpi):
            x = M + i * (kw + gap)
            bg = {"auto": C["tint2"], "decl": C["decl_bg"], "tot": white}[tipo]
            bar = {"auto": C["primary"], "decl": C["decl"], "tot": C["dark"]}[tipo]
            self.rect(x, y, kw, 74, fill=bg, stroke=C["line"] if tipo == "tot" else None, r=4)
            self.rect(x, y, kw, 2.5, fill=bar)
            self.par(x + 7, y + 8, kw - (60 if tg else 14), f"<b>{tit}</b>", 7.6, C["text"])
            if tg:
                self.tag(x + kw - self.tw(tg[0], "TW-B", 7) - 15, y + 15, tg[0], tg[1])
            self.t(x + 7, y + 44, val, "TW-B", 17, C["decl_txt"] if tipo == "decl" else C["dark"])
            self.par(x + 7, y + 50, kw - 14, esc(sub), 6.8, C["muted"])
        y += 82
        fps = t["fasce_per_stato"]
        sec = [(_fasce(fps.get("nessuna_attivita_informatica_rilevata", 0)), "senza attività al computer rilevata"),
               (_fasce(fps.get("sessione_bloccata", 0)), "computer bloccato"),
               (_fasce(fps.get("raccolta_sospesa", 0)), "raccolta sospesa dal dipendente"),
               (str(len(d.get("segnalazioni_dipendente", []))), "segnalazioni sui dati")]
        self.rect(M, y, CW, 34, fill=white, stroke=C["line"], r=4)
        for i, (v, lab) in enumerate(sec):
            x = M + i * CW / 4
            if i:
                self.c.setStrokeColor(C["line"]); self.c.line(x, self.Y(y + 6), x, self.Y(y + 28))
            self.t(x + 8, y + 14, v, "TW-B", 9.5, C["dark"]); self.t(x + 8, y + 26, lab, "TW", 7.2, C["muted"])
        y += 50
        self.sezione(y, "La giornata in sintesi")
        self.t(W - M, y, "fasce di 15 minuti", "TW", 7.4, C["muted"], "r"); y += 10
        y = self.timeline(y, 28)
        y = self.legenda(y + 10, ["attivita_rilevata", "nessuna_attivita_informatica_rilevata", "sessione_bloccata",
                                 "raccolta_sospesa", "sessione_chiusa"]) + 6
        y = self.box_sintesi(y)
        # categorie rilevate (solo nomi, in ordine alfabetico: bonifica B4) + codice di verifica
        y += 12
        self.sezione(y, "Categorie rilevate")
        cats = sorted({g.cat(c["categoria"]) for c in t["per_categoria"]
                       if c["categoria"] not in ("rete", "interazione_postazione")})
        yy, lw = y + 10, CW * 0.58
        for nome in cats[:3]:
            self.t(M + 4, yy + 11, self.taglia(nome, lw - 8, "TW", 8.4), "TW", 8.4)
            self.c.setStrokeColor(C["line"]); self.c.line(M, self.Y(yy + 17), M + lw, self.Y(yy + 17))
            yy += 17
        if not cats:
            self.t(M + 4, yy + 11, "Nessuna categoria rilevata.", "TW", 8.4, C["muted"]); yy += 17
        self.info(M, yy + 6, lw, ("Solo i nomi, in ordine alfabetico" + (f" (altre {len(cats) - 3})" if len(cats) > 3 else "")
                                  + ": nessun tempo o classifica. Il dettaglio è alle pagine 3 e 4."), 7)
        bx, bw = M + lw + 16, CW - lw - 16
        self.rect(bx, y - 8, bw, 104, fill=C["tint2"], stroke=C["line"], r=4)
        self.qr(bx + 8, y + 2, 78)
        self.t(bx + 94, y + 10, "CODICE DI VERIFICA", "TW-B", 6.8, C["primary"])
        self.t(bx + 94, y + 27, self.codice, "Mono", 11.5, C["dark"])
        sf = (d.get("integrita") or {}).get("sigillo_finale") or {}
        self.par(bx + 94, y + 33, bw - 100, f"Sigillo finale del {esc(ts_breve(sf.get('creato_il')))} · Ed25519<br/>"
                 f"Impronta chiave {esc(sf.get('impronta_chiave', '—'))}<br/>Come verificarlo: allegato tecnico, pagina 7",
                 7, C["muted"])

    def box_sintesi(self, y) -> float:
        d = self.d
        s = d.get("sintesi_ai") or {}
        orig = s.get("origine_testo") or "testo_standard"
        x, w = M, CW
        testo = esc(s.get("testo") or "Sintesi non disponibile.")
        tipo = {"ai": "ai", "testo_standard": "std", "dichiarata": "decl"}[orig]
        avvisi = (s.get("controllo_modifica") or {}).get("problemi") if orig == "dichiarata" else []
        # misura
        st = ParagraphStyle("s", fontName="TW", fontSize=9.4, leading=14, textColor=C["text"])
        p = Paragraph(testo, st); _, ph = p.wrap(w - 28, 1000)
        ah = 0
        if avvisi:
            pa = Paragraph("<b>Avvisi del controllo confermati dal dipendente:</b> " + esc("; ".join(avviso_leggibile(a) for a in avvisi[:4])),
                           ParagraphStyle("a", fontName="TW", fontSize=7.4, leading=10, textColor=C["warn"]))
            _, ah = pa.wrap(w - 28, 400); ah += 6
        h = 34 + ph + ah + 22
        self.rect(x, y, w, h, fill=white, stroke=C["line"], r=4)
        self.rect(x, y, 3, h, fill={"ai": C["ai"], "std": C["muted"], "decl": C["decl"]}[tipo])
        self.t(x + 14, y + 17, "Sintesi della giornata", "TW-B", 11, C["dark"])
        self.tag(x + 20 + self.tw("Sintesi della giornata", "TW-B", 11), y + 16, ORIGINE_SINTESI[orig], tipo)
        if s.get("verificata_dal_dipendente"):
            lab = "verificata dal dipendente"
            self.tag(x + w - self.tw(lab, "TW-B", 7) - 29, y + 16, lab, "ok", spunta=True)
        p.drawOn(self.c, x + 14, self.Y(y + 28 + ph))
        yy = y + 28 + ph
        if avvisi:
            pa.drawOn(self.c, x + 14, self.Y(yy + ah)); yy += ah
        nota = {"ai": "redatta dall'assistente locale a partire solo dai dati del resoconto, controllata automaticamente",
                "testo_standard": "testo standard generato senza assistente dai dati del resoconto",
                "dichiarata": "testo modificato dal dipendente: è una dichiarazione del dipendente"}[orig]
        ver = f"«Ho verificato la sintesi» · {esc(self.dip)}, {esc(ts_breve(s.get('verificata_il')))}" \
            if s.get("verificata_dal_dipendente") else "sintesi NON verificata dal dipendente"
        self.par(x + 14, yy + 6, w - 28, f"{ver} · <i>{nota}</i>", 7.2, C["muted"])
        return y + h

    def p2(self):
        d, g = self.d, self.g
        self.nuova_pagina("Distribuzione del tempo")
        y = self.titolo(2, "Distribuzione del tempo", "fasce di 15 minuti · dati automatici")
        h0, h1 = g.ore_estremi()
        y += self.par(M, y - 8, CW, "Ogni casella è un quarto d'ora. Il colore indica lo stato del computer; la striscia oro "
                      "indica un'attività dichiarata dal dipendente, il punto arancio una sua segnalazione. "
                      f"Fuori dall'intervallo {h0:02d}:00–{h1:02d}:00 non ci sono dati diversi da «sessione chiusa» o "
                      "«dato non disponibile».", 8.4, C["muted"]) + 4
        righe = h1 - h0
        cella_h = min(36, (500 - y) / max(righe, 1) - 3) if righe else 30
        cella_h = max(cella_h, 16)
        x0, cw = M + 40, (CW - 40 - 9) / 4
        for q, lab in enumerate((":00", ":15", ":30", ":45")):
            self.t(x0 + q * (cw + 3) + cw / 2, y + 6, lab, "TW-B", 7.4, C["primary"], "c")
        y += 12
        segn = g.segnalate()
        man = {}
        for m in d.get("manuali", []):
            for n in g.fasce_manuale(m):
                man.setdefault(n, MANUALI.get(m["categoria"], m["categoria"]))
        for r in range(righe):
            hh = h0 + r
            self.t(M, y + cella_h / 2 + 4, f"{hh:02d}:00", "TW-B", 10, C["dark"])
            for q in range(4):
                n = next((f["n"] for f in g.fasce if minuti_da(f["inizio"]) == hh * 60 + q * 15), None)
                x = x0 + q * (cw + 3)
                if n is None:
                    continue
                f = g.fasce[n]
                self.stato(x, y, cw, cella_h, f["stato"])
                if f["stato"] in ("sessione_chiusa", "dato_non_disponibile", "raccolta_sospesa"):
                    self.rect(x, y, cw, cella_h, stroke=C["line"], r=0, lw=0.4)
                fg = HexColor(TESTO_SU_STATO.get(f["stato"], "#455a64"))
                self.t(x + 3, y + 8, ST_BREVE[f["stato"]].upper(), "TW-B", 5.8, fg)
                if cella_h >= 22:
                    sub = " · ".join([g.app(a) for a in f["app"] if a != "browser"] + [g.sito(s) for s in f["siti"]]) \
                        or (" · ".join(g.app(a) for a in f["app"]))
                    if sub:
                        self.t(x + 3, y + 16, self.taglia(sub, cw - 6, "TW", 6), "TW", 6, fg)
                if n in man:
                    self.rect(x, y + cella_h - 7, cw, 7, fill=C["decl"])
                    self.t(x + 3, y + cella_h - 1.6, self.taglia(man[n] + " · dichiarata", cw - 6, "TW-B", 5.4), "TW-B", 5.4, white)
                if n in segn:
                    self.c.setFillColor(HexColor("#e08a00"))
                    self.c.circle(x + cw - 6, self.Y(y + 6), 3, fill=1, stroke=0)
                    self.t(x + cw - 6, y + 8, "!", "TW-B", 5.5, white, "c")
            y += cella_h + 3
        y = self.legenda(y + 10) + 12
        # fasce per stato + eventi
        yl = self.sezione(y, "Fasce per stato")
        fps = g.t["fasce_per_stato"]
        lw = CW * 0.5 - 8
        righe_t = []
        for k, lab, _ in STATI:
            if k == "sessione_chiusa":
                continue
            def sw(x, yy, w, k=k):
                self.stato(x + 4, yy + 5, 7, 7, k)
                self.t(x + 15, yy + 11, ST_LAB[k], "TW", 8.2)
            righe_t.append([sw, (str(fps.get(k, 0)),)])
        righe_t.append(["Sessione chiusa (resto della giornata)", (str(fps.get("sessione_chiusa", 0)),)])
        righe_t.append([("Fasce della giornata",), (str(g.t["numero_fasce"]),)])
        cols = [("Stato", lw - 36, "l"), ("Fasce", 36, "r")]
        self._tabella_x(M, yl, cols, righe_t, 15)
        xr = M + CW * 0.5 + 8
        self.rect(xr - 14 + 0, y - 9, 2.6, 12, fill=C["gold"], r=1)
        self.t(xr - 6, y, "Eventi della sessione", "TW-B", 11.5, C["dark"])
        yy = yl
        ev = [e for e in d.get("sessione", {}).get("eventi", [])]
        for e in ev[:14]:
            self.t(xr, yy + 11, e["ora"], "TW-B", 8.4, C["dark"])
            lab = EVENTI.get(e["evento"], e["evento"]) + (" (implicito, non registrato)" if e.get("implicito") else "")
            self.t(xr + 34, yy + 11, self.taglia(lab, CW * 0.5 - 50, "TW", 8.2), "TW", 8.2)
            self.c.setStrokeColor(C["line"]); self.c.line(xr, self.Y(yy + 15), W - M, self.Y(yy + 15))
            yy += 15
        if len(ev) > 14:
            self.t(xr, yy + 11, f"… altri {len(ev) - 14} eventi nell'allegato JSON", "TW-I", 7.6, C["muted"]); yy += 15
        for pz in (d.get("raccolta") or {}).get("pause", [])[:4]:
            self.t(xr, yy + 11, pz["dalle"], "TW-B", 8.4, C["dark"])
            self.t(xr + 34, yy + 11, f"Pausa della raccolta, ripresa alle {pz['alle']} ({hm(pz['minuti'])})", "TW", 8.2)
            yy += 15
        self.info(xr, yy + 6, CW * 0.5 - 8, "«Nessuna attività al computer rilevata» non significa inattività: il "
                                            "dipendente può dichiarare cosa ha fatto (pagina 5).", 7)

    def _tabella_x(self, x0, y, colonne, righe, alt=16, size=8.2):
        x = x0
        for tit, w, al in colonne:
            self.t(x + (w - 4 if al == "r" else 4), y + 8, tit.upper(), "TW-B", 6.6, C["primary"], al); x += w
        tw = sum(c[1] for c in colonne)
        self.c.setStrokeColor(C["primary"]); self.c.setLineWidth(0.7); self.c.line(x0, self.Y(y + 12), x0 + tw, self.Y(y + 12))
        y += 12
        for r in righe:
            x = x0
            for (tit, w, al), v in zip(colonne, r):
                if callable(v):
                    v(x, y, w)
                else:
                    font = "TW-B" if isinstance(v, tuple) else "TW"
                    v = v[0] if isinstance(v, tuple) else v
                    self.t(x + (w - 4 if al == "r" else 4), y + alt / 2 + 3, self.taglia(v, w - 8, font, size), font, size,
                           C["text"], al)
                x += w
            self.c.setStrokeColor(C["line"]); self.c.setLineWidth(0.5); self.c.line(x0, self.Y(y + alt), x0 + tw, self.Y(y + alt))
            y += alt
        return y

    def p3(self):
        g = self.g
        self.nuova_pagina("Strumenti e web")
        y = self.titolo(3, "Strumenti utilizzati e attività web riconosciuta", "dati automatici")
        y += self.par(M, y - 8, CW, "Programmi in primo piano durante la sessione attiva, raccolti per fascia di 15 minuti. "
                      "Non vengono registrati titoli delle finestre, nomi di file né contenuti.", 8.4, C["muted"]) + 10
        y = self.sezione(y, "Programmi")
        apps = sorted(g.t.get("per_applicazione", []), key=lambda a: g.app(a["app"]).lower())   # B4: alfabetico
        righe = []
        for a in apps[:9]:
            def nome(x, yy, w, a=a):
                self.t(x + 4, yy + 11, g.app(a["app"]), "TW-B", 8.4)
                sub = g.cat(g.cat_app(a["app"]))
                if a["app"] == "browser":
                    siti = sorted({s for n in g.fasce_di("app", "browser") for s in g.fasce[n]["siti"]})
                    if siti:
                        sub += " · usato per " + ", ".join(g.sito(s) for s in siti)
                self.t(x + 4, yy + 21, self.taglia(sub, w - 8, "TW", 7), "TW", 7, C["muted"])
            righe.append([nome, g.intervalli(g.fasce_di("app", a["app"]))])
        if not righe:
            righe = [["Nessun programma rilevato (fonte non disponibile in modalità a consuntivo o nessun uso).", ""]]
        y = self.tabella(y, [("Programma", CW * 0.54, "l"), ("Quando", CW * 0.46, "l")], righe, alt=27)
        y += 4
        nota = ("«Altra applicazione» (solo documenti precedenti): programma non presente nell'elenco dell'Ente. "
                if any(a["app"] == "altra_applicazione" for a in apps) else "")
        y += self.info(M, y, CW, nota + "Si registrano solo i programmi dell'elenco dell'Ente (mappatura "
                       f"{esc(g.cl.get('versione_mappa', '—'))}); gli altri non lasciano il nome.", 7) + 22
        y = self.sezione(y, "Categorie di lavoro")
        cats = sorted((c_ for c_ in g.t.get("per_categoria", []) if c_["categoria"] != "rete"),
                      key=lambda c_: g.cat(c_["categoria"]).lower())
        righe = [[g.cat(c_["categoria"]), g.intervalli(g.fasce_di("categorie", c_["categoria"]))]
                 for c_ in cats[:8]] or [["Nessuna categoria rilevata.", ""]]
        y = self.tabella(y, [("Categoria", CW * 0.54, "l"), ("Quando", CW * 0.46, "l")], righe, alt=16)
        y += 4
        y += self.info(M, y, CW, "Una fascia può contare per più categorie. Il traffico verso le risorse di rete è descritto "
                                 "a pagina 4.", 7) + 22
        y = self.sezione(y, "Attività web riconosciuta")
        siti = sorted(g.t.get("per_sito", []), key=lambda s: g.sito(s["sito"]).lower())
        righe = [[(g.sito(s["sito"]),), g.cat(g.cat_sito(s["sito"])), g.intervalli(g.fasce_di("siti", s["sito"]))]
                 for s in siti[:8]] or [["Nessun sito dell'elenco dell'Ente.", "", ""]]
        y = self.tabella(y, [("Sito dell'elenco dell'Ente", CW * 0.32, "l"), ("Categoria", CW * 0.32, "l"),
                             ("Quando", CW * 0.36, "l")], righe, alt=16)
        y += 14
        gen = [f["n"] for f in g.fasce if "web_generico" in f["categorie"]]
        self.rect(M, y, CW * 0.36, 52, fill=C["tint2"], r=4)
        self.t(M + 10, y + 22, f"{len(gen)} " + ("fascia" if len(gen) == 1 else "fasce"), "TW-B", 15, C["dark"])
        self.par(M + 10, y + 28, CW * 0.36 - 20, "con navigazione web non riconosciuta"
                 + (f" · {esc(g.intervalli(gen))}" if gen else ""), 7, C["muted"])
        self.rect(M + CW * 0.36 + 10, y, CW * 0.64 - 10, 52, fill=C["tint2"], stroke=C["line"], r=4)
        self.par(M + CW * 0.36 + 20, y + 9, CW * 0.64 - 30, "Il gestionale <b>Halley</b> è un servizio web: viene "
                 "riconosciuto dal nome del sito nell'elenco dell'Ente. Degli altri siti <b>non si registra "
                 "l'indirizzo</b>: risultano solo come «navigazione web».", 8, C["text"])

    def p4(self):
        d, g = self.d, self.g
        self.nuova_pagina("Office, posta e rete")
        y = self.titolo(4, "Office, posta elettronica e risorse di rete", "dati automatici")
        y = self.sezione(y + 2, "Strumenti d'ufficio (Office)")
        off = [a for a in g.t.get("per_applicazione", []) if g.cat_app(a["app"]) == "office"][:2]
        fo = [f["n"] for f in g.fasce if "office" in f["categorie"]]
        kw = (CW - 16) / 3
        card = off + [None] * (2 - len(off))
        for i, a in enumerate(card):
            x = M + i * (kw + 8)
            self.rect(x, y, kw, 52, fill=C["tint2"], r=4)
            if a:
                self.t(x + 8, y + 13, g.app(a["app"]), "TW-SB", 7.6)
                self.t(x + 8, y + 32, self.taglia(g.intervalli(g.fasce_di("app", a["app"])) or "—", kw - 16, "TW-B", 9),
                       "TW-B", 9, C["dark"])
            else:
                self.t(x + 8, y + 13, "—", "TW-SB", 7.6, C["muted"])
        x = M + 2 * (kw + 8)
        self.rect(x, y, kw, 52, fill=white, stroke=C["line"], r=4)
        self.t(x + 8, y + 13, "Fasce con almeno uno strumento d'ufficio", "TW-SB", 7.2)
        self.t(x + 8, y + 32, str(len(fo)), "TW-B", 15, C["dark"])
        self.t(x + 8, y + 44, self.taglia(g.intervalli(fo) if fo else "nessuna", kw - 16, "TW", 6.8), "TW", 6.8, C["muted"])
        y += 60
        y += self.info(M, y, CW, "Si registra solo quale programma è in primo piano: mai i nomi o il contenuto dei documenti.", 7) + 22
        y = self.sezione(y, "Posta elettronica")
        fp = [f["n"] for f in g.fasce if "posta" in f["categorie"]]
        self.rect(M, y, CW, 46, fill=C["tint2"], stroke=C["line"], r=4)
        self.par(M + 10, y + 6, CW - 20, f"<b>Fasce con l'applicazione di posta in primo piano:</b> "
                 f"{esc(g.intervalli(fp) or 'nessuna')}.<br/>Della posta si rileva solo la categoria «Posta "
                 "elettronica» quando il programma di posta è in uso, come per Word o Excel: <b>nessun</b> conteggio "
                 "dei messaggi, testo, oggetto, mittenti, destinatari, cartelle o allegati.", 7.8)
        y += 64
        y = self.sezione(y, "Risorse di rete", ("dato tecnico", "auto"))
        y += self.par(M, y - 6, CW, "Accessi della postazione alle cartelle condivise e ai server dell'Ente. È un dato "
                      "tecnico: indica che il computer era collegato alla rete dell'ente, <b>non</b> misura il lavoro "
                      "svolto; per questo non compare nella prima pagina. Non si registrano nomi di cartelle, file o "
                      "server.", 7.8, C["muted"]) + 2
        fr = [f for f in g.fasce if f["rete"]]
        senza = sum(1 for f in fr if f["stato"] != "attivita_rilevata")
        # Bonifica B4/B5: solo il segnale aggregato (fasce), niente numero di operazioni né grafico per fascia
        cards = [("Fasce con traffico di rete", str(g.t.get("fasce_con_rete", 0)), g.intervalli([f["n"] for f in fr]) or "—"),
                 ("di cui senza attività al computer rilevata", f"{senza} fasce", "il traffico non cambia lo stato della fascia")]
        kw = (CW - 8) / 2
        for i, (k, v, s) in enumerate(cards):
            x = M + i * (kw + 8)
            self.rect(x, y, kw, 46, fill=C["tint2"], r=4)
            self.t(x + 8, y + 12, k, "TW-SB", 7.2)
            self.t(x + 8, y + 30, v, "TW-B", 14, C["dark"])
            self.t(x + 8, y + 40, self.taglia(s, kw - 16, "TW", 6.6), "TW", 6.6, C["muted"])
        y += 56

    def p5(self):
        d, g = self.d, self.g
        self.nuova_pagina("Attività dichiarate")
        y = self.titolo(5, "Attività dichiarate, segnalazioni e osservazioni", "dati dichiarati dal dipendente")
        y += self.par(M, y - 8, CW, "Questa pagina contiene <b>solo informazioni inserite dal dipendente</b> durante la "
                      "revisione (in oro). Non modificano i dati automatici: li completano.", 8.4, C["muted"]) + 12
        y = self.sezione(y, "Attività fuori dal computer", ("dichiarate", "decl"))
        man = d.get("manuali", [])
        righe = []
        for m in man:
            stati = sorted({g.fasce[n]["stato"] for n in g.fasce_manuale(m)})
            righe.append([(f"{ora(m['inizio'])}–{ora(m['fine'])}",), (MANUALI.get(m["categoria"], m["categoria"]),),
                          m.get("descrizione") or "—", ", ".join(ST_BREVE[s].lower() for s in stati) or "—", (hm(m["minuti"]),)])
        if not righe:
            righe = [["—", "", "Nessuna attività dichiarata.", "", ""]]
        y = self.tabella(y, [("Orario", CW * 0.13, "l"), ("Tipo", CW * 0.13, "l"), ("Descrizione", CW * 0.40, "l"),
                             ("Stato rilevato nello stesso orario", CW * 0.24, "l"), ("Tempo", CW * 0.10, "r")], righe,
                         zebra=lambda i: C["decl_bg"], alt=18)
        y += 22
        y = self.sezione(y, "Segnalazioni sui dati automatici")
        segn = d.get("segnalazioni_dipendente", [])
        for s in segn[:6]:
            rif = f"{s['dalle']}–{s['alle']}" if s.get("dalle") else "giornata"
            ril = ""
            if s.get("fascia_da") is not None:
                ril = " · rilevato «" + ST_LAB[g.fasce[s["fascia_da"]]["stato"]] + "»"
            st = ParagraphStyle("n", fontName="TW", fontSize=8.8, leading=12)
            p = Paragraph("«" + esc(s["nota"]) + "»", st); _, ph = p.wrap(CW - 30, 300)
            h = 26 + ph
            self.rect(M, y, CW, h, fill=C["decl_bg"], stroke=C["decl_bd"], r=4)
            self.rect(M, y, 3, h, fill=C["decl"])
            self.t(M + 12, y + 14, rif, "TW-B", 9.5, C["dark"])
            self.t(M + 18 + self.tw(rif, "TW-B", 9.5), y + 14,
                   f"dato segnalato: {CAMPI_SEGNALAZIONE.get(s['campo'], s['campo'])}{ril}", "TW", 7.6, C["muted"])
            lab = "segnalazione del dipendente"
            self.tag(W - M - self.tw(lab, "TW-B", 7) - 16, y + 13, lab, "decl")
            p.drawOn(self.c, M + 12, self.Y(y + 20 + ph))
            y += h + 6
        if not segn:
            self.t(M + 4, y + 8, "Nessuna segnalazione.", "TW", 8.4, C["muted"]); y += 14
        if len(segn) > 6:
            self.t(M + 4, y + 8, f"… altre {len(segn) - 6} segnalazioni nell'allegato JSON.", "TW-I", 7.6, C["muted"]); y += 14
        y += self.info(M, y + 2, CW, "Il dato automatico resta invariato ed è coperto dal sigillo tecnico; la segnalazione lo "
                       "accompagna nel resoconto.", 7) + 22
        y = self.sezione(y, "Osservazioni del dipendente")
        oss = d.get("osservazioni_dipendente") or ""
        st = ParagraphStyle("o", fontName="TW", fontSize=9, leading=13)
        p = Paragraph(esc(oss) or "Nessuna osservazione.", st); _, ph = p.wrap(CW - 24, 400)
        self.rect(M, y, CW, ph + 18, fill=C["decl_bg"], stroke=C["decl_bd"], r=4)
        self.rect(M, y, 3, ph + 18, fill=C["decl"])
        p.drawOn(self.c, M + 12, self.Y(y + 9 + ph))
        self.t(W - M, y + ph + 28, f"{len(oss)} / 500 caratteri", "TW", 7, C["muted"], "r")

    def p6(self):
        d, g = self.d, self.g
        self.nuova_pagina("Riepilogo e firme")
        y = self.titolo(6, "Riepilogo, conferma e firme", "")
        t = g.t
        righe = [["Attività al computer rilevata", lambda x, yy, w: self.tag(x + 4, yy + 12, "rilevato", "auto"),
                  (_fasce(t["fasce_per_stato"]["attivita_rilevata"]),)],
                 ["Attività fuori dal computer", lambda x, yy, w: self.tag(x + 4, yy + 12, "dichiarato", "decl"),
                  (f"{len(d.get('manuali', []))} dichiarate",)]]
        y = self.tabella(y - 6, [("Voce", CW * 0.35, "l"), ("Origine", CW * 0.45, "l"), ("", CW * 0.2, "r")], righe,
                         zebra=lambda i: C["decl_bg"] if i == 1 else None, alt=19)
        fps = t["fasce_per_stato"]
        y = self.tabella(y + 4, [("", CW * 0.35, "l"), ("", CW * 0.15, "r"), ("", CW * 0.3, "l"), ("", CW * 0.2, "r")],
                         [["Nessuna attività al computer rilevata", _fasce(fps.get("nessuna_attivita_informatica_rilevata", 0)),
                           "Computer bloccato", _fasce(fps.get("sessione_bloccata", 0))],
                          ["Raccolta sospesa dal dipendente", _fasce(fps.get("raccolta_sospesa", 0)), "Segnalazioni sui dati",
                           str(len(d.get("segnalazioni_dipendente", [])))]], testa=False, alt=16, size=8)
        y += 14
        self.rect(M, y, CW, 70, fill=C["tint2"], stroke=C["line"], r=4)
        self.t(M + 12, y + 17, "Come leggere questo resoconto", "TW-B", 10, C["dark"])
        self.par(M + 12, y + 24, CW - 24, "I dati <b>rilevati</b> descrivono l'uso della postazione (stato del computer, "
                 "programmi) e sono raccolti automaticamente per fasce di 15 minuti; i dati <b>dichiarati</b> sono inseriti "
                 "dal dipendente. Il resoconto non calcola tempi complessivi, classifiche o indicatori: nessun dato descrive il "
                 "contenuto del lavoro e i periodi senza attività al computer <b>non</b> indicano inattività.", 8.2)
        y += 90
        y = self.sezione(y, "Conferma del dipendente")
        s = d.get("sintesi_ai") or {}
        pv = d.get("presa_visione") or {}
        sf = (d.get("integrita") or {}).get("sigillo_finale") or {}
        voci = [f"Ha preso visione dell'informativa (versione {esc(pv.get('versione', '—'))}, il "
                f"{esc(data_breve(pv['data'][:10]) if pv.get('data') else '—')}).",
                f"Ha verificato la sintesi della giornata ({esc(ORIGINE_SINTESI.get(s.get('origine_testo'), '—'))}, "
                f"{esc(ts_breve(s.get('verificata_il')))}).",
                "Conferma che le attività indicate come <b>dichiarate</b> sono state svolte nella giornata di lavoro agile.",
                f"Ha confermato e sigillato il resoconto il {esc(ts_breve(sf.get('creato_il')))} · codice di verifica "
                f"<b>{esc(self.codice)}</b>."]
        hb = 16 * len(voci) + 12
        self.rect(M, y, CW, hb, fill=white, stroke=C["line"], r=4)
        yy = y + 8
        for v in voci:
            ok = True
            self.rect(M + 10, yy, 9, 9, fill=C["ok"] if ok else white, r=1.5)
            self.spunta(M + 10, yy, 9)
            self.par(M + 26, yy - 1, CW - 36, v, 8.2)
            yy += 16
        y += hb + 6
        self.t(M, y + 6, "Formule da validare con l'ufficio personale.", "TW", 7, C["warn"])
        y += 18
        bw = CW / 2 - 6
        for i, (tit, nome, sotto) in enumerate((("IL/LA DIPENDENTE", self.dip, "Firma · data"),
                                                ("PER PRESA VISIONE · IL RESPONSABILE DEL SERVIZIO", "", "Nome, firma · data"))):
            x = M + i * (bw + 12)
            self.rect(x, y, bw, 104, fill=white, stroke=C["line"], r=4)
            self.t(x + 12, y + 16, tit, "TW-B", 6.8, C["primary"])
            if nome:
                self.t(x + 12, y + 34, self.taglia(nome, bw - 24, "TW-SB", 10.5), "TW-SB", 10.5)
            self.c.setStrokeColor(C["dark"]); self.c.setLineWidth(0.6)
            self.c.line(x + 12, self.Y(y + 80), x + bw - 12, self.Y(y + 80))
            self.t(x + 12, y + 94, sotto, "TW", 7, C["muted"])
        y += 116
        self.info(M, y, CW, "Il resoconto resta sulla postazione del dipendente: non viene inviato a nessuno in automatico.", 7)

    def p7(self):
        d, g = self.d, self.g
        self.nuova_pagina("Allegato tecnico")
        y = self.titolo(7, "Allegato tecnico", "sigilli, fonti, sintesi e verifica")
        integ = d.get("integrita") or {}
        for chiave, tit, sotto in (("sigillo_tecnico", "Sigillo tecnico", "dati automatici, creato alla chiusura della giornata"),
                                   ("sigillo_finale", "Sigillo finale", "dati automatici + dichiarazioni + sintesi, creato alla conferma")):
            s = integ.get(chiave) or {}
            self.rect(M, y - 8, CW, 112, fill=white, stroke=C["line"], r=4)
            self.t(M + 10, y + 6, tit, "TW-B", 10, C["dark"])
            self.t(M + 16 + self.tw(tit, "TW-B", 10), y + 6, sotto, "TW", 7.2, C["muted"])
            yy = y + 12
            firma = s.get("firma") or "—"
            for k, v, font in (("Codice", s.get("codice") or "—", "Mono"),
                               ("Creato il", _ts_completo(s.get("creato_il")), "TW"),
                               ("Impronta SHA-256", s.get("sha256") or "—", "Mono"),
                               ("Firma Ed25519", firma[:64], "Mono"), ("", firma[64:], "Mono"),
                               ("Chiave", f"impronta {s.get('impronta_chiave', '—')} · {s.get('account', '')} su "
                                          f"{s.get('pc', '')}", "TW")):
                if k or v:
                    self.t(M + 12, yy + 10, k, "TW-SB", 7.6, C["muted"])
                    self.t(M + 92, yy + 10, v, font, 10 if k == "Codice" else 7, C["dark"] if k == "Codice" else C["text"])
                    yy += 14 if k else 11
            y += 120
        # sintesi: origine e controllo
        s = d.get("sintesi_ai") or {}
        mo = s.get("motore") or {}
        y = self.sezione(y + 6, "Sintesi: origine e controllo")
        orig = ORIGINE_SINTESI.get(s.get("origine_testo"), "—")
        mod = mo.get("modello") or "nessun modello (testo standard)"
        tent = len((s.get("controllo") or {}).get("tentativi") or [])
        cm_ = s.get("controllo_modifica") or {}
        righe = [["Origine del testo", orig],
                 ["Assistente", f"{mod}" + (f" · profilo {mo.get('profilo')}" if mo.get("profilo") else "")
                  + (f" · temperatura {mo.get('temperatura')} · seme {mo.get('seme')}" if mo.get("modello") else "")],
                 ["Controllo anti-invenzione", f"{(s.get('controllo') or {}).get('esito', '—')} · tentativi {tent}"
                  + f" · riscritture {s.get('riscritture', 0)}"],
                 ["Modifica del dipendente", (f"sì, {ts_breve(s.get('modificata_il'))} · controllo {cm_.get('esito')}"
                                              + (" · avvisi confermati" if cm_.get("accettata_con_avvisi") else ""))
                  if s.get("origine_testo") == "dichiarata" else "no"],
                 ["Verifica del dipendente", ts_breve(s.get("verificata_il")) if s.get("verificata_dal_dipendente") else "no"]]
        y = self._tabella_x(M, y - 2, [("Voce", CW * 0.3, "l"), ("Valore", CW * 0.7, "l")], righe, 14, 7.8) + 22
        # fonti e postazione
        yl = self.sezione(y, "Copertura delle fonti")
        cop = d.get("copertura_fonti") or {}
        hw = CW / 2 - 8
        righe = [[FONTI.get(k, k), COPERTURA.get(cop.get(k), cop.get(k) or "—")] for k in
                 ("app", "attivita", "browser", "rete", "sessione")]
        righe.append(["Traffico di rete: fasce · operazioni", f"{g.t.get('fasce_con_rete', 0)} · {g.t.get('operazioni_rete', 0)}"])
        righe.append(["Note tecniche · avvisi dell'aggregatore", f"{g.t.get('fasce_con_note_tecniche', 0)} · {len(d.get('avvisi', []))}"])
        y1 = self._tabella_x(M, yl - 2, [("Fonte", hw * 0.62, "l"), ("Copertura", hw * 0.38, "r")], righe, 13, 7.6)
        xr = M + CW / 2 + 8
        self.rect(xr - 8, y - 9, 2.6, 12, fill=C["gold"], r=1); self.t(xr, y, "Postazione e versioni", "TW-B", 11.5, C["dark"])
        po = d.get("postazione") or {}
        pa = po.get("profilo_ai") or {}
        ver = d.get("versioni") or {}
        righe = [["Postazione", f"{po.get('host', '—')} · {po.get('tipo', '—')}" + (f" · {po['ram_gb']} GB" if po.get("ram_gb") else "")],
                 ["Profilo assistente", f"{pa.get('profilo', '—')} ({pa.get('modello_indicativo', '')})"],
                 ["Applicazione", f"Rendiconto SW {VERSIONE_APP}"],
                 ["Aggregatore", f"{ver.get('aggregatore', '—')} · {d.get('schema', '')}"],
                 ["Raccolta dati", {"consuntivo": "a consuntivo (pulsanti della giornata)", "collector": "collector"}.get(
                     d.get("modalita"), d.get("modalita", "—"))],
                 ["Mappatura", g.cl.get("versione_mappa", "—")],
                 ["Informativa", f"versione {(d.get('presa_visione') or {}).get('versione', '—')}"],
                 ["Fuso orario", d.get("fuso", "—")]]
        y2 = self._tabella_x(xr, yl - 2, [("Voce", hw * 0.36, "l"), ("Valore", hw * 0.64, "l")], righe, 13, 7.4)
        y = max(y1, y2) + 12
        self.rect(M, y, 96, 96, fill=white, stroke=C["line"], r=4)
        self.qr(M + 8, y + 8, 80)
        x = M + 110
        self.rect(x - 8, y + 1, 2.6, 12, fill=C["gold"], r=1); self.t(x, y + 10, "Come verificare il resoconto", "TW-B", 10, C["dark"])
        self.par(x, y + 18, CW - 110, "1. Il QR contiene la data, il codice di verifica e l'impronta SHA-256 del sigillo "
                 "finale.<br/>2. Il PDF contiene in allegato il file dati <b>resoconto.json</b> con i due sigilli: il "
                 "programma <b>VerificaRendiconto</b> controlla i sigilli, la chiave della postazione nel registro dei "
                 "Sistemi Informativi e che il testo del PDF corrisponda ai dati: esito <b>VALIDO</b>, <b>INTEGRO</b> "
                 "(chiave non registrata) o <b>ALTERATO</b>.<br/>3. Se un dato o il testo è stato modificato dopo la "
                 "conferma, l'esito è <b>ALTERATO</b>.", 7.8)

    def crea(self):
        for p in (self.p1, self.p2, self.p3, self.p4, self.p5, self.p6, self.p7):
            p()
        self.c.showPage()
        self.c.save()


def pdf_bytes(doc: dict, filigrana: str | None = None) -> bytes:
    """PDF senza allegato (usato anche dal verificatore per il confronto del testo)."""
    buf = io.BytesIO()
    Pdf(doc, buf, filigrana).crea()
    return buf.getvalue()


NOME_ALLEGATO = "resoconto.json"


def crea_pdf(doc: dict, percorso: str, filigrana: str | None = None) -> str:
    """Scrive il PDF con il JSON allegato. Richiede il sigillo finale (salvo filigrana di prova)."""
    if not ((doc.get("integrita") or {}).get("sigillo_finale")) and not filigrana:
        raise ValueError("il resoconto non ha il sigillo finale: confermarlo prima di creare il PDF")
    from pypdf import PdfReader, PdfWriter
    base = pdf_bytes(doc, filigrana)
    w = PdfWriter(clone_from=PdfReader(io.BytesIO(base)))
    w.add_attachment(NOME_ALLEGATO, json.dumps(doc, ensure_ascii=False, indent=1).encode("utf-8"))
    import reportlab      # la versione di ReportLab è nei metadati: il confronto grafico del verificatore vale solo a parità di versione
    meta = {"/RendicontoSW": f"{VERSIONE_APP}|{'filigrana' if filigrana else 'sigillato'}|rl{reportlab.Version}"}
    if filigrana:
        meta["/RendicontoSWFiligrana"] = filigrana        # per rigenerare il testo identico nella verifica
    w.add_metadata(meta)
    tmp = percorso + ".tmp"
    with open(tmp, "wb") as f:
        w.write(f)
    os.replace(tmp, percorso)
    return percorso
