"""Icone dell'applicazione (.ico multi-risoluzione) disegnate dai token grafici dell'edizione, senza stemma.

Produce in --uscita: rendiconto.ico (programma e collegamenti), verifica.ico (Verificatore), setup.ico (Setup) e le
icone dell'area di notifica tray_attiva.ico, tray_pausa.ico, tray_nessuna.ico. Con --anteprime salva anche i PNG di
ogni formato e un foglio di confronto. Ogni formato piccolo (16-32 px) ha un disegno semplificato e allineato ai pixel,
non una riduzione del 256 px. Formati: 16, 20, 24, 32, 40, 48, 64, 256 (BMP 32 bit sotto 256, PNG a 256).

Uso: python -m tools.crea_icone --uscita applicazione/assets/icone [--tokens config/design_tokens.json] [--anteprime DIR]
"""
from __future__ import annotations

import argparse
import io
import json
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FORMATI = (16, 20, 24, 32, 40, 48, 64, 256)
NOMI = ("rendiconto", "verifica", "setup", "tray_attiva", "tray_pausa", "tray_nessuna")
SOVRA = 8                     # campionamento: si disegna 8 volte più grande e si riduce
GRIGIO_TILE = ("#7B8A97", "#5F6E7B")
AMBRA = "#E39A00"             # pausa: più chiaro del «warning» testuale, leggibile su barra chiara e scura


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def palette(tokens: dict) -> dict:
    return {"tile": tokens["primary"], "tile_scuro": tokens["primary-800"], "scuro": tokens["dark"],
            "accento": tokens["stemma-gold"], "ok": tokens["success"], "bianco": tokens["surface"],
            "righe": tokens["primary-tint-2"], "piega": tokens["primary-tint-1"]}


class Tela:
    """Coordinate in pixel del formato finale (anche frazionarie); disegno sovracampionato."""

    def __init__(self, n: int):
        self.n = n
        self.im = Image.new("RGBA", (n * SOVRA, n * SOVRA), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.im)

    def _s(self, *v):
        return [round(x * SOVRA) for x in v]

    def rett(self, x0, y0, x1, y1, r, colore, bordo=None, spessore=0):
        self.d.rounded_rectangle(self._s(x0, y0, x1, y1), radius=round(r * SOVRA), fill=colore,
                                 outline=bordo, width=round(spessore * SOVRA))

    def tile(self, x0, y0, x1, y1, r, alto, basso):
        """Riquadro con sfumatura verticale."""
        a, b = _hex(alto), _hex(basso)
        h = round((y1 - y0) * SOVRA)
        grad = Image.new("RGBA", (round((x1 - x0) * SOVRA), h))
        gd = ImageDraw.Draw(grad)
        for y in range(h):
            t = y / max(1, h - 1)
            gd.line([(0, y), (grad.width, y)], fill=tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,))
        maschera = Image.new("L", grad.size, 0)
        ImageDraw.Draw(maschera).rounded_rectangle((0, 0, grad.width - 1, h - 1), radius=round(r * SOVRA), fill=255)
        self.im.paste(grad, (round(x0 * SOVRA), round(y0 * SOVRA)), maschera)

    def poligono(self, punti, colore):
        self.d.polygon([tuple(self._s(x, y)) for x, y in punti], fill=colore)

    def linea(self, punti, colore, spessore):
        self.d.line([tuple(self._s(x, y)) for x, y in punti], fill=colore, width=round(spessore * SOVRA),
                    joint="curve")
        r = spessore * SOVRA / 2
        for x, y in (punti[0], punti[-1]):           # estremi arrotondati
            cx, cy = x * SOVRA, y * SOVRA
            self.d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=colore)

    def cerchio(self, cx, cy, r, colore, bordo=None, spessore=0):
        self.d.ellipse(self._s(cx - r, cy - r, cx + r, cy + r), fill=colore, outline=bordo,
                       width=round(spessore * SOVRA))

    def immagine(self) -> Image.Image:
        return self.im.resize((self.n, self.n), Image.Resampling.LANCZOS if self.n >= 48 else Image.Resampling.BOX)


# ------------------------------------------------------------------------------------------------ elementi
def _riquadro(t: Tela, pal: dict, grigio=False):
    n = t.n
    m = 0 if n <= 24 else n * 0.03
    r = max(2.5, n * 0.19)
    alto, basso = GRIGIO_TILE if grigio else (pal["tile"], pal["tile_scuro"])
    t.tile(m, m, n - m, n - m, r, alto, basso)
    if n >= 32 and not grigio:                       # filo dell'accento come sotto l'intestazione dell'app
        s = max(1.0, n * 0.035)
        y = n - m - r * 0.55 - s
        t.rett(m + r * 0.9, y, n - m - r * 0.9, y + s, s / 2, pal["accento"])


def _foglio(t: Tela, pal: dict, x0, y0, x1, y1, righe=True):
    """Foglio bianco con angolo piegato."""
    n = t.n
    p = (x1 - x0) * 0.32
    t.poligono([(x0, y0), (x1 - p, y0), (x1, y0 + p), (x1, y1), (x0, y1)], pal["bianco"])
    t.poligono([(x1 - p, y0), (x1 - p, y0 + p), (x1, y0 + p)], pal["piega"])
    if righe and n >= 20:
        s = max(1.0, n * 0.045)
        lx0, lx1 = x0 + (x1 - x0) * 0.2, x1 - (x1 - x0) * 0.22
        ys = [y0 + (y1 - y0) * f for f in ((0.42, 0.62) if n < 32 else (0.38, 0.54, 0.70))]
        for i, y in enumerate(ys):
            fine = lx1 if i < len(ys) - 1 else lx0 + (lx1 - lx0) * 0.6
            t.linea([(lx0, y), (fine, y)], pal["righe"], s)


def _orologio(t: Tela, pal: dict, cx, cy, r):
    n = t.n
    anello = max(1.0, n * 0.045)
    s = max(1.0, n * 0.06)
    a = r - anello
    if n <= 24:                                      # piccolo: quadrante chiaro e lancette scure, più contrasto
        t.cerchio(cx, cy, r, pal["scuro"])
        t.cerchio(cx, cy, a, pal["bianco"])
        lancette = pal["scuro"]
    else:
        t.cerchio(cx, cy, r, pal["bianco"])
        t.cerchio(cx, cy, a, pal["scuro"])
        lancette = pal["bianco"]
    t.linea([(cx, cy), (cx, cy - a * 0.62)], lancette, s)
    t.linea([(cx, cy), (cx + a * 0.52, cy + a * 0.1)], lancette, s)
    if n >= 48:
        t.cerchio(cx, cy, s * 0.8, pal["accento"])


def _spunta(t: Tela, colore, cx, cy, r, spessore):
    t.linea([(cx - r * 0.55, cy + r * 0.02), (cx - r * 0.12, cy + r * 0.45), (cx + r * 0.6, cy - r * 0.42)],
            colore, spessore)


def _scudo(t: Tela, pal: dict, cx, cy, w, h):
    pts = [(cx - w / 2, cy - h * 0.38), (cx, cy - h / 2), (cx + w / 2, cy - h * 0.38), (cx + w / 2, cy + h * 0.02),
           (cx + w * 0.3, cy + h * 0.3), (cx, cy + h / 2), (cx - w * 0.3, cy + h * 0.3), (cx - w / 2, cy + h * 0.02)]
    t.poligono(pts, pal["bianco"])


def _freccia(t: Tela, pal: dict, cx, cy, r):
    n = t.n
    anello = max(1.0, n * 0.045)
    t.cerchio(cx, cy, r, pal["bianco"])
    t.cerchio(cx, cy, r - anello, pal["ok"])
    s = max(1.5, n * 0.075)
    a = r - anello
    if n <= 24:                                      # piccolo: freccia piena, leggibile anche a 16 px
        t.rett(cx - s / 2, cy - a * 0.6, cx + s / 2, cy + a * 0.05, 0, pal["bianco"])
        t.poligono([(cx - a * 0.62, cy - a * 0.05), (cx + a * 0.62, cy - a * 0.05), (cx, cy + a * 0.65)],
                   pal["bianco"])
        return
    t.linea([(cx, cy - a * 0.55), (cx, cy + a * 0.45)], pal["bianco"], s)
    t.linea([(cx - a * 0.45, cy + a * 0.02), (cx, cy + a * 0.47), (cx + a * 0.45, cy + a * 0.02)], pal["bianco"], s)


# --------------------------------------------------------------------------------------------- icone intere
def rendiconto(n: int, pal: dict) -> Image.Image:
    t = Tela(n)
    _riquadro(t, pal)
    if n <= 24:
        _foglio(t, pal, n * 0.2, n * 0.14, n * 0.66, n * 0.84)
        _orologio(t, pal, n * 0.68, n * 0.68, n * 0.3)
    else:
        _foglio(t, pal, n * 0.22, n * 0.14, n * 0.64, n * 0.74)
        _orologio(t, pal, n * 0.68, n * 0.64, n * 0.22)
    return t.immagine()


def verifica(n: int, pal: dict) -> Image.Image:
    t = Tela(n)
    m = 0 if n <= 24 else n * 0.03
    t.tile(m, m, n - m, n - m, max(2.5, n * 0.19), pal["scuro"], pal["tile_scuro"])
    if n >= 32:
        s = max(1.0, n * 0.035)
        r = n * 0.19
        y = n - m - r * 0.55 - s
        t.rett(m + r * 0.9, y, n - m - r * 0.9, y + s, s / 2, pal["accento"])
    _scudo(t, pal, n / 2, n * 0.49, n * (0.62 if n <= 24 else 0.54), n * (0.74 if n <= 24 else 0.64))
    _spunta(t, pal["ok"], n / 2, n * 0.47, n * (0.24 if n <= 24 else 0.2), max(1.5, n * 0.085))
    return t.immagine()


def setup(n: int, pal: dict) -> Image.Image:
    t = Tela(n)
    _riquadro(t, pal)
    if n <= 24:
        _foglio(t, pal, n * 0.2, n * 0.14, n * 0.66, n * 0.84)
        _freccia(t, pal, n * 0.68, n * 0.68, n * 0.3)
    else:
        _foglio(t, pal, n * 0.22, n * 0.14, n * 0.64, n * 0.74)
        _freccia(t, pal, n * 0.68, n * 0.64, n * 0.22)
    return t.immagine()


def tray(n: int, pal: dict, stato: str) -> Image.Image:
    """Area di notifica: stesso riquadro del programma; lo stato si legge da colore E forma (non solo colore)."""
    t = Tela(n)
    _riquadro(t, pal, grigio=(stato == "nessuna"))
    if n >= 32:
        _foglio(t, pal, n * 0.22, n * 0.14, n * 0.64, n * 0.74)
    else:
        _foglio(t, pal, n * 0.2, n * 0.12, n * 0.64, n * 0.82, righe=n >= 24)
    if stato == "nessuna":
        return t.immagine()
    cx = cy = n * (0.72 if n < 32 else 0.68)
    r = n * (0.27 if n < 32 else 0.23)
    anello = max(1.0, n * 0.06)
    if stato == "attiva":
        t.cerchio(cx, cy, r, pal["bianco"])
        t.cerchio(cx, cy, r - anello, pal["ok"])
        a = r - anello                               # triangolo «in corso» da 24 px; sotto, il solo disco verde
        if n >= 24:
            t.poligono([(cx - a * 0.32, cy - a * 0.5), (cx + a * 0.55, cy), (cx - a * 0.32, cy + a * 0.5)],
                       pal["bianco"])
    else:                                            # pausa: quadrato ambra con due barre (forma diversa dal disco)
        t.rett(cx - r, cy - r, cx + r, cy + r, r * 0.35, pal["bianco"])
        t.rett(cx - r + anello, cy - r + anello, cx + r - anello, cy + r - anello, r * 0.25, AMBRA)
        a = r - anello
        b = max(1.0, a * 0.3)
        for dx in (-a * 0.32, a * 0.32):
            t.rett(cx + dx - b / 2, cy - a * 0.5, cx + dx + b / 2, cy + a * 0.5, b / 3, pal["bianco"])
    return t.immagine()


def disegna(nome: str, n: int, pal: dict) -> Image.Image:
    if nome.startswith("tray_"):
        return tray(n, pal, nome[5:])
    return {"rendiconto": rendiconto, "verifica": verifica, "setup": setup}[nome](n, pal)


# --------------------------------------------------------------------------------------------- file .ico
def _dib(im: Image.Image) -> bytes:
    """Immagine BMP per ICO: BITMAPINFOHEADER, 32 bit BGRA dal basso, maschera AND a 1 bit."""
    w, h = im.size
    px = im.convert("RGBA").tobytes("raw", "BGRA")
    righe = [px[y * w * 4:(y + 1) * w * 4] for y in range(h)]
    xor = b"".join(reversed(righe))
    passo = ((w + 31) // 32) * 4
    alfa = im.getchannel("A").tobytes()
    mask = bytearray()
    for y in reversed(range(h)):
        riga = bytearray(passo)
        for x in range(w):
            if alfa[y * w + x] == 0:
                riga[x // 8] |= 0x80 >> (x % 8)
        mask += riga
    head = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, len(xor) + len(mask), 0, 0, 0, 0)
    return head + xor + bytes(mask)


def scrivi_ico(path: Path, immagini: list[Image.Image]) -> None:
    dati = []
    for im in sorted(immagini, key=lambda i: i.size[0]):
        if im.size[0] >= 256:
            b = io.BytesIO()
            im.save(b, "PNG", optimize=True)
            dati.append((im.size[0], b.getvalue()))
        else:
            dati.append((im.size[0], _dib(im)))
    out = bytearray(struct.pack("<HHH", 0, 1, len(dati)))
    off = 6 + 16 * len(dati)
    for n, b in dati:
        out += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(b), off)
        off += len(b)
    for _, b in dati:
        out += b
    path.write_bytes(bytes(out))


def crea(uscita: Path, tokens: dict, anteprime: Path | None = None, etichetta: str = "") -> list[Path]:
    pal = palette(tokens)
    uscita.mkdir(parents=True, exist_ok=True)
    fatti = []
    tutte = {}
    for nome in NOMI:
        imm = [disegna(nome, n, pal) for n in FORMATI]
        tutte[nome] = imm
        p = uscita / f"{nome}.ico"
        scrivi_ico(p, imm)
        fatti.append(p)
        if anteprime:
            (anteprime / nome).mkdir(parents=True, exist_ok=True)
            for im in imm:
                im.save(anteprime / nome / f"{nome}_{im.size[0]}.png")
    if anteprime:
        foglio(tutte, anteprime / "foglio_icone.png", etichetta)
    return fatti


def foglio(tutte: dict, path: Path, etichetta: str = "") -> None:
    """Confronto di tutte le icone e formati su sfondo chiaro e scuro (barra delle applicazioni)."""
    mostra = (16, 20, 24, 32, 48, 64, 256)
    larg = 40 + sum(max(n, 40) + 24 for n in mostra) + 150
    alt_riga = 280
    im = Image.new("RGB", (larg, 70 + len(tutte) * alt_riga * 1), "#FFFFFF")
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype("segoeui.ttf", 15)
        fb = ImageFont.truetype("segoeuib.ttf", 18)
    except OSError:
        f = fb = ImageFont.load_default()
    d.text((20, 18), "Anteprima icone" + (f" — {etichetta}" if etichetta else ""), fill="#17334F", font=fb)
    y = 60
    for nome, imm in tutte.items():
        per = {i.size[0]: i for i in imm}
        d.text((20, y + 4), nome, fill="#17334F", font=fb)
        for k, sfondo in enumerate(("#FFFFFF", "#F3F3F3", "#202020")):
            x = 150
            yy = y + 34 + k * 80 if k < 2 else y + 34 + 160
            if k == 0:
                yy = y + 34
            for n in mostra:
                if n == 256 and k:
                    continue
                cella = max(n, 40) + 12
                if n < 256:
                    d.rectangle((x - 6, yy - 6, x - 6 + cella, yy - 6 + max(n, 40) + 12), fill=sfondo)
                    src = per[n]
                    im.paste(src, (x, yy), src)
                    if k == 0:
                        d.text((x, yy + max(n, 40) + 8), f"{n}", fill="#5D7083", font=f)
                x += max(n, 40) + 24
        big = per[256]
        im.paste(big.resize((128, 128), Image.Resampling.LANCZOS), (larg - 150, y + 20),
                 big.resize((128, 128), Image.Resampling.LANCZOS))
        y += alt_riga
    im.save(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="crea_icone")
    ap.add_argument("--uscita", required=True)
    ap.add_argument("--tokens", help="design_tokens.json (predefinito: quello dell'edizione scelta)")
    ap.add_argument("--anteprime")
    ap.add_argument("--etichetta", default="")
    ns = ap.parse_args(argv)
    if ns.tokens:
        tokens = json.loads(Path(ns.tokens).read_text(encoding="utf-8-sig"))
    else:
        from resoconto.tokens import carica
        tokens = carica()
    for p in crea(Path(ns.uscita), tokens, Path(ns.anteprime) if ns.anteprime else None, ns.etichetta):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
