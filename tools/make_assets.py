"""Gera os ícones do app (PNG para a bandeja, ICO para o .exe/instalador). Rode: python tools/make_assets.py

Usa uma fonte do sistema com o glifo ♞ (Segoe UI Symbol no Windows, DejaVu no Linux). Os arquivos gerados
ficam versionados em think_aloud_chess/assets e installer/, então o CI não precisa de fonte.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = [r"C:\Windows\Fonts\seguisym.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"]


def font(size):
    for f in FONTS:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    raise SystemExit("nenhuma fonte com o glifo do cavalo encontrada")


def knight(size=512):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(size * 0.22)
    # fundo: degradê vertical azul-petróleo
    grad = Image.new("RGBA", (size, size))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / size
        gd.line([(0, y), (size, y)], fill=(int(24 + 20 * t), int(34 + 40 * t), int(52 + 50 * t), 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=255)
    img.paste(grad, (0, 0), mask)
    f = font(int(size * 0.78))
    glyph = "♞"
    bbox = d.textbbox((0, 0), glyph, font=f)
    x = (size - (bbox[2] - bbox[0])) / 2 - bbox[0]
    y = (size - (bbox[3] - bbox[1])) / 2 - bbox[1] - size * 0.02
    d.text((x + size * 0.012, y + size * 0.012), glyph, font=f, fill=(0, 0, 0, 90))  # sombra
    d.text((x, y), glyph, font=f, fill=(246, 224, 94, 255))
    # balão de "pensamento": três pontos
    for i, rad in enumerate((0.028, 0.04, 0.055)):
        cx, cy = size * (0.70 + 0.07 * i), size * (0.20 - 0.045 * i)
        rr = size * rad
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(255, 255, 255, 235))
    return img


if __name__ == "__main__":
    img = knight(512)
    (ROOT / "think_aloud_chess" / "assets").mkdir(exist_ok=True)
    (ROOT / "installer").mkdir(exist_ok=True)
    img.resize((256, 256), Image.LANCZOS).save(ROOT / "think_aloud_chess" / "assets" / "icon.png")
    img.save(ROOT / "installer" / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.save(ROOT / "docs" / "logo.png") if (ROOT / "docs").exists() else None
    print("ok")
