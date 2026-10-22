"""Renderiza o trailer: quadros do trailer.html (Playwright) + trilha (make_audio.py) -> MP4 via ffmpeg.

  python tools/trailer/render.py --preview          # contact sheet de quadros-chave em build/trailer/preview.jpg
  python tools/trailer/render.py --preview --at 12.0 --at 36.5   # quadros específicos (em segundos)
  python tools/trailer/render.py --full             # vídeo completo em build/trailer/kibitz-trailer.mp4
Pré-requisitos: python tools/trailer/capture_assets.py (uma vez), pip install playwright pillow numpy scipy imageio-ffmpeg
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = ROOT / "build" / "trailer"
ASSETS = BUILD / "assets"
TL = json.loads((HERE / "timeline.json").read_text(encoding="utf-8"))
SPB = 60 / TL["bpm"]
DURATION = TL["total_beats"] * SPB
KEY_BEATS = [3.2, 8.3, 11.3, 14.3, 17.6, 20.3, 22.2, 25.4, 27.6, 29.9, 33.5, 37.6, 41.8, 42.9, 46.0, 50.6,
             53.6, 56.9, 61.8, 64.6, 66.3, 68.0, 75.2, 77.2, 79.0, 83.0, 85.8, 89.5, 92.8, 96.5, 99.0, 103.0]


def open_page(pw):
    meta = json.loads((ASSETS / "meta.json").read_text(encoding="utf-8"))
    shutil.copy(ROOT / "docs" / "logo.png", BUILD / "icon.png")
    br = pw.chromium.launch(args=["--force-device-scale-factor=1", "--font-render-hinting=none"])
    pg = br.new_page(viewport={"width": 1920, "height": 1080})
    pg.add_init_script("window.__DATA = " + json.dumps({"tl": TL, "meta": meta, "base": ASSETS.as_uri()}))
    pg.goto((HERE / "trailer.html").as_uri())
    pg.wait_for_function("window.__READY === true", timeout=60000)
    return br, pg


def preview(times):
    from playwright.sync_api import sync_playwright
    BUILD.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        br, pg = open_page(pw)
        frames = []
        t0 = time.time()
        for t in times:
            pg.evaluate(f"renderFrame({t})")
            pg.wait_for_timeout(60)
            png = BUILD / "_p.png"
            pg.screenshot(path=str(png))
            frames.append((t, Image.open(png).convert("RGB").resize((640, 360), Image.LANCZOS)))
        br.close()
    print(f"{len(frames)} quadros em {time.time() - t0:.1f}s ({(time.time() - t0) / len(frames):.2f}s/quadro)")
    cols = 3
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 640, rows * 360), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for i, (t, im) in enumerate(frames):
        x, y = (i % cols) * 640, (i // cols) * 360
        sheet.paste(im, (x, y))
        d.text((x + 8, y + 6), f"{t:.1f}s  b{t / SPB:.1f}", fill=(255, 255, 0))
    # várias folhas de 12 quadros para ficarem legíveis
    per = 12
    for k in range(0, len(frames), per):
        sub = sheet.crop((0, (k // cols) * 360, cols * 640, min(rows, (k + per) // cols) * 360))
        sub.save(BUILD / f"preview_{k // per + 1}.jpg", quality=88)
        print("->", BUILD / f"preview_{k // per + 1}.jpg")


def full(out, fps, audio):
    import imageio_ffmpeg
    from playwright.sync_api import sync_playwright
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    n = int(DURATION * fps)
    BUILD.mkdir(parents=True, exist_ok=True)
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-"]
    if audio and Path(audio).exists():
        cmd += ["-i", str(audio)]
    cmd += ["-vf", "scale=in_range=pc:in_color_matrix=bt601:out_range=tv:out_color_matrix=bt709:flags=lanczos,format=yuv420p",
            "-c:v", "libx264", "-preset", "slow", "-crf", "22", "-maxrate", "12M", "-bufsize", "24M", "-profile:v", "high",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv", "-r", str(fps)]
    if audio and Path(audio).exists():
        cmd += ["-c:a", "aac", "-b:a", "224k", "-shortest"]
    cmd += ["-movflags", "+faststart", str(out)]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    with sync_playwright() as pw:
        br, pg = open_page(pw)
        for i in range(n):
            pg.evaluate(f"renderFrame({i / fps})")
            enc.stdin.write(pg.screenshot(type="jpeg", quality=95))
            if i % 90 == 0:
                el = time.time() - t0
                print(f"quadro {i}/{n}  ({i / max(el, .01):.1f} fps, falta ~{(n - i) / max(i / max(el, .01), .01) / 60:.1f} min)", flush=True)
        br.close()
    enc.stdin.close()
    enc.wait()
    print(f"pronto: {out}  ({Path(out).stat().st_size / 1e6:.1f} MB, {n / fps:.1f}s) em {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--at", type=float, action="append")
    ap.add_argument("--fps", type=int, default=TL["fps"])
    ap.add_argument("--audio", default=str(BUILD / "audio.wav"))
    ap.add_argument("--out", default=str(BUILD / "kibitz-trailer.mp4"))
    a = ap.parse_args()
    if a.preview:
        preview(a.at if a.at else [b * SPB for b in KEY_BEATS])
    elif a.full:
        full(a.out, a.fps, a.audio)
    else:
        ap.print_help()
