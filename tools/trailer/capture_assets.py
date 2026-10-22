"""Captura o material REAL do trailer (telas do programa em 2560x1440) a partir da partida de demonstração.

Sobe o app numa pasta de dados temporária (não usa nem altera suas partidas). Saída: build/trailer/assets/
Uso: python tools/trailer/capture_assets.py
"""
import gzip
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build" / "trailer" / "assets"
PORT = 5058
BASE = f"http://127.0.0.1:{PORT}"
SEL = {"board": "#board", "evalbar": "#evalbar", "panel": "#rv-panel", "cmt": ".cmt", "next": "[data-cm='1']",
       "status": "#status", "moves": "#moves", "thought": "#thought-card", "wrap": ".boardwrap"}


def call(path, method="GET", data=None, raw=False):
    req = urllib.request.Request(BASE + path, data=data if raw else (json.dumps(data).encode() if data is not None else None),
                                 method=method, headers={} if raw else {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))


def rects(pg):
    return pg.evaluate("""(sel) => Object.fromEntries(Object.entries(sel).map(([k, s]) => {
        const e = document.querySelector(s); if (!e || e.hidden) return [k, null];
        const r = e.getBoundingClientRect(); return [k, [r.x, r.y, r.width, r.height]]; }))""", SEL)


def main():
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="tac-trailer-")
    srv = subprocess.Popen([sys.executable, "-m", "kibitz", "--no-browser", "--port", str(PORT), "--data-dir", tmp],
                           cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    meta = {"viewport": [1280, 720], "scale": 2, "states": {}}
    try:
        for _ in range(60):
            try:
                call("/api/ping")
                break
            except Exception:
                time.sleep(0.5)
        demo = call("/api/demo", "POST")["id"]
        game = call(f"/api/games/{demo}?peek=1")
        # raciocínio REAL de um lance do agente (para o cartão "pensando em voz alta")
        pick = next(m for m in game["moves"] if m["by"] == "agent" and m["san"] == "Qe6" and m.get("thought"))
        t = pick["thought"]
        meta["reasoning"] = {k: t.get(k) for k in ("position_read", "opponent_threats", "plan", "candidates", "decision", "blunder_check")}
        meta["reasoning"]["san"] = pick["san"]
        # partida "em andamento" derivada da demonstração (mostra o raciocínio trancado)
        raw = gzip.decompress(urllib.request.urlopen(urllib.request.Request(f"{BASE}/api/games/{demo}/export")).read())
        g = json.loads(raw)
        g.update(id="live", status="ongoing", result=None, reason=None)
        g["moves"] = g["moves"][:20]
        for k in ("review", "audit", "exported_at"):
            g.pop(k, None)
        call("/api/games/import", "POST", gzip.compress(json.dumps(g).encode()), raw=True)

        with sync_playwright() as p:
            br = p.chromium.launch()
            ctx = br.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=2, color_scheme="dark")
            pg = ctx.new_page()

            def shot(name, **kw):
                pg.wait_for_timeout(450)
                pg.screenshot(path=str(OUT / f"{name}.png"), **kw)
                meta["states"][name] = rects(pg)

            # 1) partida em andamento: raciocínio trancado
            pg.goto(BASE + "/#g/live")
            pg.reload()
            pg.wait_for_selector("#board .sq")
            pg.locator("#moves .m").nth(19).click()
            shot("live")
            pg.locator(".boardwrap").screenshot(path=str(OUT / "board.png"))

            # 2) revisão: cada comentário com e sem setas
            pg.goto(BASE + f"/#g/{demo}")
            pg.reload()
            pg.wait_for_selector("#rv-start")
            pg.locator("#rv-start").click()
            pg.wait_for_timeout(500)
            shot("rv_start")
            for i in range(1, 11):
                pg.locator("[data-cm='1']").click()
                pg.wait_for_timeout(500)
                if i not in (1, 7, 10):   # só comentários sobre lances da IA (7...exd4, 20...Qe6, 26...Nf3+)
                    continue
                shot(f"m{i}_arrows")
                pg.evaluate("document.querySelector('#arrows').innerHTML = ''; document.querySelector('#arrow-legend').hidden = true;")
                shot(f"m{i}_noarrows")
                pg.evaluate("render()")   # redesenha a tela (e as setas) com a função do próprio app
            pg.locator("[data-tab='sum']").click()
            shot("summary")

            # 3) assistente de primeira abertura (simula um PC sem o Claude Code)
            pg.route("**/api/health*", lambda r: r.fulfill(json={
                "version": "0.1.0b2", "claude": {"installed": False, "logged_in": False, "path": None}, "api_providers": 0,
                "stockfish": {"found": True, "name": "Stockfish 19"}, "data_dir": "", "demo": True, "can_auto_install": True,
                "setup": {"installing": False, "log": "", "ok": None}}))
            pg.goto(BASE + "/")
            pg.reload()
            pg.wait_for_selector("#health .step")
            shot("setup")
            br.close()
        (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        for f in sorted(OUT.iterdir()):
            print(f"{f.name:22s} {f.stat().st_size // 1024:5d} KB")
    finally:
        srv.terminate()


if __name__ == "__main__":
    main()
