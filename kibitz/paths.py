"""Onde ficam os arquivos: recursos do pacote (somente leitura) e dados do usuário (gravável).

Dados do usuário (partidas, autosaves, config.json com chaves de API):
  1. variável de ambiente TAC_DATA_DIR (ou --data-dir na linha de comando), se existir;
  2. rodando de um clone do repositório: ./data (ignorado pelo git);
  3. instalado (pip) ou executável: pasta de dados do sistema (ex.: %LOCALAPPDATA%\\Kibitz).
"""
import os
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parent
STATIC = PKG / "static"
PROMPTS = PKG / "prompts"
EXAMPLES = PKG / "examples"
# executáveis embutidos (Stockfish): ao lado do .exe instalado, ou ./bin num clone
BIN = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else PKG.parent) / "bin"


def _default_data_dir():
    env = os.environ.get("TAC_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    if (PKG.parent / "pyproject.toml").exists():  # clone do repositório
        return PKG.parent / "data"
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "Kibitz"


DATA = _default_data_dir()
GAMES = DATA / "games"
SAVES = DATA / "saves"
SANDBOX = DATA / "sandbox"
CONFIG = DATA / "config.json"


def ensure():
    for d in (DATA, GAMES, SAVES, SANDBOX):
        d.mkdir(parents=True, exist_ok=True)
