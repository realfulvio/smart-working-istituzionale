"""Banner della pagina principale del repository (docs/img/hero.png) dalle schermate di esempio."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RADICE = Path(__file__).resolve().parents[1]
SC = RADICE / "docs" / "screenshots"
FONT = RADICE / "applicazione" / "assets" / "fonts"
W, H = 1600, 700
P, D = (0x1F, 0x4E, 0x79), (0x12, 0x26, 0x3A)


def f(peso, n):
    return ImageFont.truetype(str(FONT / f"TitilliumWeb-{peso}.ttf"), n)


def ombra(base, im, xy):
    sh = Image.new("RGBA", (im.width + 80, im.height + 80), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle([40, 40, 40 + im.width, 40 + im.height], fill=(0, 0, 0, 120))
    sh = sh.filter(ImageFilter.GaussianBlur(18))
    base.alpha_composite(sh, (xy[0] - 40, xy[1] - 30))
    base.alpha_composite(im.convert("RGBA"), xy)


def main():
    bg = Image.new("RGBA", (W, H))
    d = ImageDraw.Draw(bg)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(P[i] + (D[i] - P[i]) * t) for i in range(3)) + (255,))
    d.rectangle([0, H - 6, W, H], fill=(0x9A, 0x6B, 0x00, 255))
    d.text((60, 110), "Smart Working", font=f("Bold", 72), fill="white")
    d.text((60, 190), "Istituzionale", font=f("Bold", 72), fill="white")
    chiaro = (0xE8, 0xEE, 0xF4)
    for i, riga in enumerate(("Il resoconto giornaliero del lavoro agile", "per gli enti pubblici: poca raccolta,", "tutto sul PC, rivisto dal dipendente", "e sigillato.")):
        d.text((60, 310 + i * 40), riga, font=f("Regular", 29), fill=chiaro)
    for i, riga in enumerate(("EUPL-1.2  ·  Windows", "AI locale, nessun cloud", "PDF sigillato Ed25519")):
        d.text((60, 520 + i * 32), riga, font=f("SemiBold", 22), fill=(0xB8, 0xC9, 0xDB))
    a = Image.open(SC / "04_revisione.png").convert("RGB")
    a = a.resize((680, round(680 * a.height / a.width)), Image.LANCZOS)
    ombra(bg, a, (690, 170))
    b = Image.open(SC / "pdf_pagina-1.png").convert("RGB")
    b = b.resize((370, round(370 * b.height / b.width)), Image.LANCZOS)
    ombra(bg, b, (1190, 100))
    bg.convert("RGB").save(RADICE / "docs" / "img" / "hero.png", optimize=True)


if __name__ == "__main__":
    main()
