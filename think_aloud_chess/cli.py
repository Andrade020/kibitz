"""Linha de comando: sobe o servidor local e abre o navegador."""
import argparse
import os
import socket
import sys
import threading
import time
import webbrowser


def _free_port(host, start):
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host, port)) != 0:  # ninguém escutando: porta livre
                return port
    raise SystemExit(f"Nenhuma porta livre entre {start} e {start + 49}.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="think-aloud-chess", description="Jogue xadrez contra um LLM que pensa em voz alta.")
    ap.add_argument("--host", default="127.0.0.1", help="endereço (padrão 127.0.0.1: só este computador)")
    ap.add_argument("--port", type=int, default=5000, help="porta inicial (procura a próxima livre)")
    ap.add_argument("--data-dir", help="pasta de partidas, autosaves e config.json")
    ap.add_argument("--no-browser", action="store_true", help="não abrir o navegador")
    ap.add_argument("--version", action="store_true")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # nenhum print futuro derruba o app por causa da codificação do console
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    if args.data_dir:
        os.environ["TAC_DATA_DIR"] = args.data_dir  # antes de importar o app (os caminhos são fixados na importação)

    from . import __version__, paths
    if args.version:
        print(__version__)
        return
    paths.ensure()
    from .app import app

    port = _free_port(args.host, args.port)
    url = f"http://{args.host}:{port}"
    print(f"\n  Think-Aloud Chess {__version__}\n  Abra {url}  (Ctrl+C para encerrar)\n  Dados: {paths.DATA}\n")
    if not args.no_browser:
        threading.Thread(target=lambda: (time.sleep(1.2), webbrowser.open(url)), daemon=True).start()
    app.run(host=args.host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
