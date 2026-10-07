"""Genera le immagini del wizard di Inno Setup (BMP 24 bit) senza logo, con palette e nome dell'Ente letti da config/ente.json (predefiniti neutri) e font Titillium Web.

Uso (dalla radice del repository):  python tools/pacchetto/setup/genera_immagini.py
Scrive in tools/pacchetto/setup/:  wizard_100/150/200.bmp (pannello a sinistra di Benvenuto/Fine, rapporto 164:314,
202/336/430 px di larghezza) e wizard_piccola_100/150/200.bmp (58/97/124 px) (quadrata, in alto a destra nelle altre pagine), più le anteprime PNG in anteprime/.
Palette come applicazione/tema.py (config/ente.json); font Titillium Web (OFL) da applicazione/assets/fonts.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

QUI = Path(__file__).resolve().parent
RADICE = QUI.parents[2]
FONT = RADICE / "applicazione" / "assets" / "fonts"
sys.path.insert(0, str(RADICE))
from resoconto import ente  # noqa: E402

import argparse
ap=argparse.ArgumentParser();ap.add_argument("--config");ap.add_argument("--output")
ns=ap.parse_args() if __name__=="__main__" else ap.parse_args([])
ENTE = ente.carica(ns.config) if ns.config else ente.carica()
DEST=Path(ns.output) if ns.output else QUI
DEST.mkdir(parents=True,exist_ok=True)
VERSIONE = "5.0.0"

def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


PRIMARY, DARK, GOLD, TINT, WHITE = *(_rgb(ENTE["colori"][k]) for k in ("primario", "scuro", "accento", "tenue")), (255, 255, 255)
GRIGIO = (0xB8, 0xC9, 0xDB)


def font(peso, dim):
    return ImageFont.truetype(str(FONT / f"TitilliumWeb-{peso}.ttf"), dim)


def gradiente(l, a):
    im = Image.new("RGB", (l, a))
    d = ImageDraw.Draw(im)
    for y in range(a):
        t = y / max(1, a - 1)
        c = tuple(round(PRIMARY[i] + (DARK[i] - PRIMARY[i]) * t * 0.85) for i in range(3))
        d.line([(0, y), (l, y)], fill=c)
    return im


def centra(d, testo, f, y, l, colore):
    w = d.textlength(testo, font=f)
    d.text(((l - w) / 2, y), testo, font=f, fill=colore)


def grande(l):
    a = round(l * 314 / 164)
    s = l / 202  # scala rispetto all'area a 100 % (202x386)
    im = gradiente(l, a)
    d = ImageDraw.Draw(im)
    d.rectangle([l - max(2, round(3 * s)), 0, l, a], fill=GOLD)  # filetto oro come nei mockup
    lu = l - max(2, round(3 * s))
    if ENTE["logo"]:
        logo = Image.open(ENTE["logo"]).convert("RGBA")
        logo.thumbnail((round(96*s), round(96*s)), Image.Resampling.LANCZOS)
        im.paste(logo, ((lu-logo.width)//2, round(22*s)), logo)
    y = round(140 * s)
    for riga in ("Resoconto", "lavoro agile"):
        centra(d, riga, font("Bold", round(23 * s)), y, lu, WHITE)
        y += round(32 * s)
    y += round(6 * s)
    centra(d, f"Versione {VERSIONE}", font("Regular", round(13.5 * s)), y, lu, TINT)
    y += round(20 * s)
    centra(d, ENTE["nome"], font("SemiBold", round(13.5 * s)), y, lu, TINT)
    y += round(30 * s)
    d.line([(lu * 0.3, y), (lu * 0.7, y)], fill=GOLD, width=max(1, round(2 * s)))
    y += round(16 * s)
    for riga in ("Resoconto della giornata", "di lavoro agile"):
        centra(d, riga, font("Regular", round(12.5 * s)), y, lu, GRIGIO)
        y += round(18 * s)
    centra(d, ENTE["nome"], font("Regular", round(11*s)), a-round(30*s), lu, WHITE)
    return im


def piccola(n):
    """Stemma originale ridimensionato proporzionalmente, nessun ridisegno."""
    im = Image.new("RGB", (n, n), PRIMARY)
    if ENTE["logo"]:
        logo = Image.open(ENTE["logo"]).convert("RGBA")
        logo.thumbnail((n-4, n-4), Image.Resampling.LANCZOS)
        im.paste(logo, ((n-logo.width)//2, (n-logo.height)//2), logo)
        return im
    d = ImageDraw.Draw(im)
    f = font("Bold", round(n * 0.42))
    w = d.textlength("SW", font=f)
    d.text(((n - w) / 2, n * 0.22), "SW", font=f, fill=WHITE)
    return im


def main():
    prev = DEST / "anteprime"
    prev.mkdir(exist_ok=True)
    for perc, l in ((100, 202), (150, 336), (200, 430)):
        im = grande(l)
        im.save(DEST / f"wizard_{perc}.bmp")
        if l == 336:
            im.save(prev / "wizard_grande.png")
    for perc, n in ((100, 58), (150, 97), (200, 124)):
        im = piccola(n)
        im.save(DEST / f"wizard_piccola_{perc}.bmp")
        if n == 124:
            im.save(prev / "wizard_piccola.png")
    print("immagini scritte in", DEST)


if __name__ == "__main__":
    main()
