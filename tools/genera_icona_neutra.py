"""Icona geometrica di un documento, senza elementi araldici o identità dell'Ente."""
from pathlib import Path
from PIL import Image, ImageDraw

FORMATI = (16, 24, 32, 48, 64, 128, 256)


def genera(destinazione=None):
    target = Path(destinazione) if destinazione else Path(__file__).resolve().parents[1] / "applicazione/assets/rendiconto.ico"
    im = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((30, 30, 482, 482), radius=85, fill="#0066CC")
    d.rounded_rectangle((134, 86, 378, 426), radius=24, fill="white")
    for y in (158, 204, 250):
        d.rounded_rectangle((176, y, 334, y + 14), radius=7, fill="#0066CC")
    d.line((180, 338, 218, 373, 326, 298), fill="#0066CC", width=23, joint="curve")
    target.parent.mkdir(parents=True, exist_ok=True)
    im.save(target, format="ICO", sizes=[(n, n) for n in FORMATI])
    return target


if __name__ == "__main__":
    print(genera())
