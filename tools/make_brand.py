"""Gera a identidade visual do Kibitz: faixa do README (EN e PT) e imagem de capa para redes sociais.

Estilo: escuro e cinematográfico (fundo quase preto, dourado como destaque, tipografia condensada em maiúsculas),
igual ao trailer. Requer: pip install playwright && python -m playwright install chromium; internet (Google Fonts).
Antes: python tools/make_assets.py (logo) e python tools/make_media.py (captura usada na capa).
Uso: python tools/make_brand.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "img"

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@500;600&family=JetBrains+Mono:wght@400&family=Oswald:wght@500;700&display=swap');
*{margin:0;padding:0;box-sizing:border-box}
body{background:#05070a;overflow:hidden;font-family:Inter,'Segoe UI',sans-serif;color:#eef1f6}
.bg{position:absolute;inset:0;background:radial-gradient(ellipse at 18% 30%,rgba(246,224,94,.16),transparent 55%),radial-gradient(ellipse at 90% 90%,rgba(90,162,255,.12),transparent 50%),#05070a}
.grid{position:absolute;inset:0;background:repeating-conic-gradient(#fff 0 25%,transparent 0 50%) 0 0/96px 96px;opacity:.045;
  -webkit-mask-image:radial-gradient(ellipse at 70% 50%,#000 10%,transparent 75%);mask-image:radial-gradient(ellipse at 70% 50%,#000 10%,transparent 75%)}
.vig{position:absolute;inset:0;background:radial-gradient(ellipse at center,transparent 55%,rgba(0,0,0,.55) 100%)}
.word{font-family:Oswald,Impact,sans-serif;font-weight:700;text-transform:uppercase;letter-spacing:.05em;line-height:.9;color:#fff;text-shadow:0 6px 40px rgba(0,0,0,.6)}
.bar{height:7px;width:120px;background:#f6e05e;border-radius:4px}
.tag{font-weight:600;color:#dfe5ee}
.def{font-family:'JetBrains Mono',Consolas,monospace;color:#8a94a6}
.def b{color:#f6e05e;font-weight:400}
svg.arrows{position:absolute;inset:0}
"""

ARROWS = """<svg class="arrows" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <g stroke-linecap="round" fill="none" opacity=".9">
    <path d="M{a} L{b}" stroke="#2fb344" stroke-width="12"/><path d="M{c} L{d}" stroke="#ff5d73" stroke-width="12"/><path d="M{e} L{f}" stroke="#5aa2ff" stroke-width="12"/>
  </g>
  <g fill="#2fb344"><polygon points="{ah}"/></g><g fill="#ff5d73"><polygon points="{ch}"/></g><g fill="#5aa2ff"><polygon points="{eh}"/></g>
</svg>"""


def arrows(w, h, k=1.0):
    # três setas (verde, vermelha, azul), como as da revisão
    def head(x, y, ang):
        import math
        L, W = 34 * k, 22 * k
        ux, uy = math.cos(ang), math.sin(ang)
        px, py = -uy, ux
        return f"{x},{y} {x - ux * L + px * W},{y - uy * L + py * W} {x - ux * L - px * W},{y - uy * L - py * W}"
    import math
    a0, a1 = (w * .56, h * .86), (w * .80, h * .26)
    c0, c1 = (w * .98, h * .80), (w * .72, h * .48)
    e0, e1 = (w * .60, h * .30), (w * .88, h * .70)
    ang = lambda p, q: math.atan2(q[1] - p[1], q[0] - p[0])
    return ARROWS.format(w=w, h=h, a=f"{a0[0]},{a0[1]}", b=f"{a1[0]},{a1[1]}", c=f"{c0[0]},{c0[1]}", d=f"{c1[0]},{c1[1]}",
                         e=f"{e0[0]},{e0[1]}", f=f"{e1[0]},{e1[1]}",
                         ah=head(*a1, ang(a0, a1)), ch=head(*c1, ang(c0, c1)), eh=head(*e1, ang(e0, e1)))


def banner_html(lang):
    tag, defn = {
        "en": ("The chess AI that thinks out loud.", "<b>kibitz</b> /ˈkɪbɪts/ <i>v.</i> to comment on someone else's game."),
        "pt": ("A IA de xadrez que pensa em voz alta.", "<b>kibitz</b> /ˈkɪbɪts/ <i>v.</i> comentar a partida de quem está jogando."),
    }[lang]
    return f"""<style>{CSS}</style><div class="bg"></div><div class="grid"></div>
    <div class="vig"></div>
    <div style="position:absolute;left:78px;top:0;bottom:0;display:flex;align-items:center;gap:44px">
      <img src="{(ROOT / 'docs' / 'logo.png').as_uri()}" style="width:176px;height:176px;filter:drop-shadow(0 18px 50px rgba(246,224,94,.28))">
      <div><div class="word" style="font-size:150px">Kibitz</div><div class="bar" style="margin:18px 0 20px"></div>
      <div class="tag" style="font-size:31px">{tag}</div><div class="def" style="font-size:17px;margin-top:10px">{defn}</div></div></div>"""


def social_html():
    shot = (OUT / "review-hero.png").as_uri()
    return f"""<style>{CSS}</style><div class="bg"></div><div class="grid"></div><div class="vig"></div>
    <div style="position:absolute;left:84px;top:62px"><img src="{(ROOT / 'docs' / 'logo.png').as_uri()}" style="width:118px;height:118px;filter:drop-shadow(0 14px 40px rgba(246,224,94,.3))"></div>
    <div style="position:absolute;left:80px;top:212px;width:560px">
      <div class="word" style="font-size:150px">Kibitz</div><div class="bar" style="margin:20px 0 24px"></div>
      <div class="tag" style="font-size:36px;line-height:1.22">The chess AI that<br>thinks out loud.</div>
      <div class="def" style="font-size:17px;margin-top:18px;line-height:1.5"><b>kibitz</b> /ˈkɪbɪts/ <i>v.</i> to comment<br>on someone else's game.</div></div>
    <div style="position:absolute;left:660px;top:104px;width:700px;transform:perspective(1800px) rotateY(-12deg) rotateX(2deg);transform-origin:left center;
      border-radius:18px;overflow:hidden;box-shadow:0 40px 110px rgba(0,0,0,.85),0 0 0 2px rgba(255,255,255,.1)">
      <img src="{shot}" style="display:block;width:700px"></div>"""


def main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = p.chromium.launch()
        for name, size, html in (("banner-en.png", (1280, 360), banner_html("en")), ("banner-pt.png", (1280, 360), banner_html("pt")),
                                 ("social-preview.png", (1280, 640), social_html())):
            pg = br.new_page(viewport={"width": size[0], "height": size[1]})
            tmp = ROOT / "build" / "_brand.html"
            tmp.parent.mkdir(exist_ok=True)
            tmp.write_text(f"<!doctype html><meta charset='utf-8'>{html}", encoding="utf-8")
            pg.goto(tmp.as_uri(), wait_until="load")
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(900)
            pg.screenshot(path=str(OUT / name))
            print(name, (OUT / name).stat().st_size // 1024, "KB")
        br.close()


if __name__ == "__main__":
    main()
