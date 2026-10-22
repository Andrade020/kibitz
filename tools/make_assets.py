"""Gera o logo do Kibitz: PNG para a bandeja/README e ICO para o .exe e o instalador.  python tools/make_assets.py

O ícone é um cavalo dourado com um balão de fala contendo "!?", a anotação de xadrez para um lance interessante
(e o que um *kibitzer* faz: comentar o jogo). Usa fontes do sistema (Segoe UI no Windows, DejaVu no Linux); os arquivos
gerados ficam versionados em kibitz/assets e installer/, então o CI não precisa de fonte.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SYMBOL = [r"C:\Windows\Fonts\seguisym.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
          "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"]
BOLD = [r"C:\Windows\Fonts\segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
GOLD = (246, 224, 94, 255)


def font(candidates, size):
    for f in candidates:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    raise SystemExit("fonte não encontrada")


def logo(size=512):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    # fundo: degradê quase preto -> azul-petróleo, cantos arredondados
    grad = Image.new("RGBA", (size, size))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / size
        gd.line([(0, y), (size, y)], fill=(int(14 + 14 * t), int(20 + 30 * t), int(32 + 44 * t), 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * .22), fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    # cavalo (um pouco menor e para baixo/esquerda, abrindo espaço para o balão)
    f = font(SYMBOL, int(size * .70))
    bb = d.textbbox((0, 0), "♞", font=f)
    x = size * .47 - (bb[2] - bb[0]) / 2 - bb[0]
    y = size * .60 - (bb[3] - bb[1]) / 2 - bb[1]
    d.text((x + size * .012, y + size * .012), "♞", font=f, fill=(0, 0, 0, 100))
    d.text((x, y), "♞", font=f, fill=GOLD)
    # balão de fala com "!?"
    bx0, by0, bx1, by1 = size * .53, size * .07, size * .94, size * .36
    d.polygon([(size * .60, by1 - 4), (size * .66, by1 - 4), (size * .575, by1 + size * .08)], fill=(255, 255, 255, 255))
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=size * .09, fill=(255, 255, 255, 255))
    ft = font(BOLD, int(size * .25))
    tb = d.textbbox((0, 0), "!?", font=ft)
    d.text(((bx0 + bx1) / 2 - (tb[2] - tb[0]) / 2 - tb[0], (by0 + by1) / 2 - (tb[3] - tb[1]) / 2 - tb[1] - size * .005), "!?",
           font=ft, fill=(14, 20, 32, 255))
    return img


if __name__ == "__main__":
    img = logo(512)
    (ROOT / "kibitz" / "assets").mkdir(exist_ok=True)
    (ROOT / "installer").mkdir(exist_ok=True)
    (ROOT / "docs").mkdir(exist_ok=True)
    img.resize((256, 256), Image.LANCZOS).save(ROOT / "kibitz" / "assets" / "icon.png")
    img.resize((256, 256), Image.LANCZOS).save(ROOT / "kibitz" / "static" / "icon.png")
    img.save(ROOT / "installer" / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    img.save(ROOT / "docs" / "logo.png")
    print("ok")
