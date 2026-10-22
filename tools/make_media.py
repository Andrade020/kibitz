"""Gera as imagens do README (capturas e GIF, no tema escuro) a partir da partida de demonstração.

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

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "img"
PORT = 5057
BASE = f"http://127.0.0.1:{PORT}"


def call(path, method="GET", data=None, raw=False):
    req = urllib.request.Request(BASE + path, data=data if raw else (json.dumps(data).encode() if data is not None else None),
                                 method=method, headers={} if raw else {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))


def main():
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="tac-media-")
    srv = subprocess.Popen([sys.executable, "-m", "kibitz", "--no-browser", "--port", str(PORT), "--data-dir", tmp],
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
            pg = br.new_page(viewport={"width": 1280, "height": 860}, color_scheme="dark")

            def shot(name, clip=None):
                pg.wait_for_timeout(350)
                pg.screenshot(path=str(OUT / name), clip=clip or {"x": 0, "y": 0, "width": 1280, "height": 860})

            # 1) configuração inicial (simula um computador sem o Claude Code)
            pg.route("**/api/health*", lambda r: r.fulfill(json={
                "version": "0.1.0b2", "claude": {"installed": False, "logged_in": False, "path": None}, "api_providers": 0,
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
            AI_MOMENTS = (1, 7, 10)  # comentários sobre lances da IA (7...exd4, 20...Qe6, 26...Nf3+): é o que vitrine mostra
            n = 0
            while n < 10 and not pg.locator("[data-cm='1']").is_disabled():
                pg.locator("[data-cm='1']").click()
                n += 1
                if n in AI_MOMENTS:
                    frame()
                if n == 7:
                    shot("review-comment.png")
                if n == 10:
                    shot("review-hero.png")
            pg.locator("[data-before]").click()
            shot("review-before.png")
            br.close()

        # GIF do passeio pela revisão
        small = [f.resize((960, int(960 * f.size[1] / f.size[0])), Image.LANCZOS).convert("P", palette=Image.ADAPTIVE, colors=96) for f in frames]
        small[0].save(OUT / "review-walkthrough.gif", save_all=True, append_images=small[1:], duration=[1400] + [2600] * (len(small) - 1),
                      loop=0, optimize=True)
        (OUT / "_frame.png").unlink(missing_ok=True)
        for f in sorted(OUT.iterdir()):
            print(f"{f.name:28s} {f.stat().st_size // 1024:5d} KB")
    finally:
        srv.terminate()


if __name__ == "__main__":
    main()
