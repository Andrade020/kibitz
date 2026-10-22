"""Lançador desktop (instalador / .exe): servidor em segundo plano + ícone na bandeja, sem janela de console.

- Se o app já estiver aberto, só abre o navegador nele (instância única).
- Sem terminal: a saída vai para <dados>/logs/app.log.
- "Sair" no ícone da bandeja encerra o servidor.
"""
import json
import os
import socket
import sys
import threading
import urllib.request
import webbrowser

from . import __version__, paths


def _log_to_file():
    paths.ensure()
    (paths.DATA / "logs").mkdir(parents=True, exist_ok=True)
    f = open(paths.DATA / "logs" / "app.log", "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stderr = f


def _ours(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=3) as r:
            return json.load(r).get("app") == "kibitz"
    except Exception:
        return False


def _free_port(start=5000):
    for p in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise RuntimeError("sem porta livre")


def _tray(url, srv):
    try:
        import pystray
        from PIL import Image
    except Exception:  # sem bandeja (ex.: Linux sem suporte): fica servindo até o processo ser encerrado
        threading.Event().wait()
        return
    menu_items = [pystray.MenuItem("Abrir o Kibitz", lambda i, it: webbrowser.open(url), default=True)]
    if sys.platform == "win32":
        menu_items.append(pystray.MenuItem("Abrir pasta de dados", lambda i, it: os.startfile(paths.DATA)))
    menu_items.append(pystray.MenuItem("Sair", lambda i, it: i.stop()))
    icon = pystray.Icon("Kibitz", Image.open(paths.PKG / "assets" / "icon.png"),
                        f"Kibitz {__version__}", pystray.Menu(*menu_items))
    icon.run()


def main():
    if getattr(sys, "frozen", False) and (sys.stdout is None or sys.stderr is None):
        _log_to_file()
    for port in range(5000, 5010):
        if _ours(port):  # já está rodando: só abre o navegador
            webbrowser.open(f"http://127.0.0.1:{port}")
            return
    paths.ensure()
    from werkzeug.serving import make_server
    from .app import app

    port = _free_port()
    srv = make_server("127.0.0.1", port, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    print(f"Kibitz {__version__} em {url} | dados: {paths.DATA}", flush=True)
    webbrowser.open(url)
    try:
        _tray(url, srv)
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
