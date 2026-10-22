"""Gera as imagens do README (capturas, GIF e pré-visualização social) a partir da partida de demonstração.

Sobe o app numa pasta de dados temporária (como uma instalação nova), então não usa nem altera suas partidas.
Requer: pip install playwright pillow && python -m playwright install chromium
Uso:    python tools/make_media.py
"""
import gzip
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "img"
PORT = 5057
BASE = f"http://127.0.0.1:{PORT}"
FONTS = {"regular": r"C:\Windows\Fonts\segoeui.ttf", "bold": r"C:\Windows\Fonts\segoeuib.ttf"}


def call(path, method="GET", data=None, raw=False):
    req = urllib.request.Request(BASE + path, data=data if raw else (json.dumps(data).encode() if data is not None else None),
                                 method=method, headers={} if raw else {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))


def font(kind, size):
    p = FONTS[kind]
    return ImageFont.truetype(p, size) if Path(p).exists() else ImageFont.load_default()


def social(hero_png, out):
    W, H = 1280, 640
    img = Image.new("RGB", (W, H), (20, 24, 32))
    d = ImageDraw.Draw(img)
    for y in range(H):  # degradê
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(18 + 14 * t), int(24 + 22 * t), int(36 + 34 * t)))
    logo = Image.open(ROOT / "docs" / "logo.png").convert("RGBA").resize((150, 150), Image.LANCZOS)
    img.paste(logo, (70, 70), logo)
    d.text((70, 250), "Think-Aloud", font=font("bold", 76), fill=(246, 224, 94))
    d.text((70, 335), "Chess", font=font("bold", 76), fill=(255, 255, 255))
    for i, line in enumerate(["Play chess against an LLM that", "thinks out loud — then let it teach", "you with arrows and concepts."]):
        d.text((72, 450 + i * 36), line, font=font("regular", 28), fill=(190, 200, 214))
    shot = Image.open(hero_png).convert("RGB")
    shot = shot.crop((0, 70, 1280, 800)).resize((700, int(700 * 730 / 1280)), Image.LANCZOS)
    mask = Image.new("L", shot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, shot.size[0] - 1, shot.size[1] - 1], radius=18, fill=255)
    img.paste(shot, (W - 700 - 40, (H - shot.size[1]) // 2 + 10), mask)
    img.save(out, optimize=True)


def main():
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="tac-media-")
    srv = subprocess.Popen([sys.executable, "-m", "think_aloud_chess", "--no-browser", "--port", str(PORT), "--data-dir", tmp],
                           cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                call("/api/health")
                break
            except Exception:
                time.sleep(0.5)
        demo = call("/api/demo", "POST")["id"]
        # partida "em andamento" (vez das brancas) feita da demonstração, para mostrar o raciocínio oculto
        raw = gzip.decompress(urllib.request.urlopen(urllib.request.Request(f"{BASE}/api/games/{demo}/export")).read())
        g = json.loads(raw)
        g.update(id="live", status="ongoing", result=None, reason=None)
        g["moves"] = g["moves"][:20]
        for k in ("review", "audit", "exported_at"):
            g.pop(k, None)
        call("/api/games/import", "POST", gzip.compress(json.dumps(g).encode()), raw=True)

        with sync_playwright() as p:
            br = p.chromium.launch()
            pg = br.new_page(viewport={"width": 1280, "height": 860})

            def shot(name, clip=None):
                pg.wait_for_timeout(350)
                pg.screenshot(path=str(OUT / name), clip=clip or {"x": 0, "y": 0, "width": 1280, "height": 860})

            # 1) configuração inicial (simula um computador sem o Claude Code)
            pg.route("**/api/health*", lambda r: r.fulfill(json={
                "version": "0.1.0b1", "claude": {"installed": False, "logged_in": False, "path": None}, "api_providers": 0,
                "stockfish": {"found": True, "name": "Stockfish 19"}, "data_dir": "", "demo": True, "can_auto_install": True,
                "setup": {"installing": False, "log": "", "ok": None}}))
            pg.goto(BASE + "/")
            pg.wait_for_selector("#health .step")
            shot("setup.png", {"x": 0, "y": 0, "width": 1280, "height": 640})
            pg.unroute("**/api/health*")

            # 2) novo jogo (opções avançadas abertas)
            pg.reload()
            pg.wait_for_selector("#health .step")
            pg.locator("#new-card details.adv summary").click()
            pg.wait_for_timeout(300)
            shot("new-game.png", {"x": 0, "y": 0, "width": 1280, "height": 860})

            # 3) partida em andamento: raciocínio oculto (jogo justo)
            pg.goto(BASE + "/#g/live")
            pg.reload()
            pg.wait_for_selector("#board .sq")
            pg.locator("#moves .m").nth(19).click()
            shot("live-game.png")

            # 4) revisão: lance a lance, com setas
            pg.goto(BASE + f"/#g/{demo}")
            pg.reload()
            pg.wait_for_selector("#rv-start")
            pg.locator("#rv-start").click()
            pg.wait_for_timeout(500)
            frames = [Image.open(OUT / "setup.png")][:0]
            clip = {"x": 0, "y": 56, "width": 1280, "height": 790}

            def frame():
                pg.wait_for_timeout(450)
                path = OUT / "_frame.png"
                pg.screenshot(path=str(path), clip=clip)
                frames.append(Image.open(path).convert("RGB").copy())

            frame()  # posição inicial do modo revisão
            n = 0
            while not pg.locator("[data-cm='1']").is_disabled():
                pg.locator("[data-cm='1']").click()
                n += 1
                frame()
                if n == 3:
                    shot("review-comment.png")           # um comentário com setas
                if n == 7:
                    shot("review-hero.png")
                if n >= 9:
                    break
            pg.locator("[data-before]").click()
            shot("review-before.png")
            pg.locator("[data-tab='sum']").click()
            shot("review-summary.png")
            br.close()

        # GIF do passeio pela revisão
        small = [f.resize((960, int(960 * f.size[1] / f.size[0])), Image.LANCZOS).convert("P", palette=Image.ADAPTIVE, colors=96) for f in frames]
        small[0].save(OUT / "review-walkthrough.gif", save_all=True, append_images=small[1:], duration=[1400] + [2600] * (len(small) - 1),
                      loop=0, optimize=True)
        (OUT / "_frame.png").unlink(missing_ok=True)
        social(OUT / "review-hero.png", OUT / "social-preview.png")
        for f in sorted(OUT.iterdir()):
            print(f"{f.name:28s} {f.stat().st_size // 1024:5d} KB")
    finally:
        srv.terminate()


if __name__ == "__main__":
    main()
