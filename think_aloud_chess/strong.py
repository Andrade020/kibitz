"""Motor forte (UCI, ex.: Stockfish) usado SÓ pelo professor, depois da partida.

O jogador (Claude) nunca vê este motor: ele existe para o professor corrigir explicações com a verdade da posição,
inclusive quando o próprio Claude errou a leitura durante o jogo. Se não houver motor, a revisão cai na régua rasa.
"""
import glob
import os
import shutil
from pathlib import Path

import chess
import chess.engine

from . import paths, providers

CLIP = 1000  # centipeões; mates viram +-CLIP


def _candidates():
    home = str(Path.home())
    pats = [
        r"C:\Program Files\Stockfish*\**\stockfish*.exe", r"C:\Program Files (x86)\Stockfish*\**\stockfish*.exe",
        r"C:\stockfish*\**\stockfish*.exe", r"C:\tools\stockfish*\**\stockfish*.exe",
        home + r"\stockfish*\**\stockfish*.exe", home + r"\Downloads\stockfish*\**\stockfish*.exe",
        home + r"\Desktop\stockfish*\**\stockfish*.exe", home + r"\AppData\Local\Microsoft\WinGet\Packages\*tockfish*\**\stockfish*.exe",
        home + r"\AppData\Local\Microsoft\WinGet\Links\stockfish*.exe",
        "/usr/games/stockfish", "/usr/bin/stockfish", "/usr/local/bin/stockfish", "/opt/homebrew/bin/stockfish",
    ]
    for p in pats:
        yield from glob.glob(p, recursive=True)


def configured_path():
    return providers._load().get("stockfish_path") or ""


def set_path(path):
    with providers._lock:
        cfg = providers._load()
        cfg["stockfish_path"] = path.strip()
        providers._save(cfg)


def find():
    """Caminho do motor ou None. Ordem: configurado, PATH, locais comuns."""
    p = configured_path()
    if p and Path(p).is_file():
        return p
    for name in ("stockfish.exe", "stockfish"):  # embutido no instalador (ou ./bin num clone)
        if (paths.BIN / name).is_file():
            return str(paths.BIN / name)
    w = shutil.which("stockfish")
    if w:
        return w
    for c in _candidates():
        if Path(c).is_file() and os.access(c, os.X_OK):
            return c
    return None


def probe(path):
    """Abre o motor e devolve o nome (valida o caminho). Levanta exceção se não for UCI."""
    with chess.engine.SimpleEngine.popen_uci(path, timeout=20) as e:
        return e.id.get("name", "motor UCI")


def status():
    p = find()
    if not p:
        return {"found": False, "path": configured_path(), "name": None}
    try:
        return {"found": True, "path": p, "name": probe(p)}
    except Exception as ex:  # noqa
        return {"found": False, "path": p, "name": None, "error": f"{type(ex).__name__}"}


def _cp(score):
    s = score.white().score(mate_score=100000)
    return max(-CLIP, min(CLIP, s))


class Session:
    def __init__(self, path):
        self.eng = chess.engine.SimpleEngine.popen_uci(path, timeout=30)
        self.name = self.eng.id.get("name", "motor UCI")
        try:
            self.eng.configure({"Threads": min(4, os.cpu_count() or 1), "Hash": 128})
        except Exception:  # noqa  (motores sem essas opções)
            pass

    def close(self):
        try:
            self.eng.quit()
        except Exception:  # noqa
            self.eng.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def series(self, moves, depth=14, progress=None):
        """Avaliação (pontos de vista das brancas, em cp) das N+1 posições da partida e o melhor lance de cada."""
        b = chess.Board()
        cps, bests = [], []
        n = len(moves)
        for i in range(n + 1):
            if b.is_game_over():
                if b.is_checkmate():
                    cps.append(-CLIP if b.turn == chess.WHITE else CLIP)
                else:
                    cps.append(0)
                bests.append(None)
            else:
                info = self.eng.analyse(b, chess.engine.Limit(depth=depth, time=1.5))
                cps.append(_cp(info["score"]))
                bests.append(info["pv"][0].uci() if info.get("pv") else None)
            if progress:
                progress(i + 1, n + 1)
            if i < n:
                b.push_uci(moves[i]["uci"])
        return {"cp": cps, "best": bests}

    def deep(self, board, played, depth=18, multipv=3):
        """Melhores linhas na posição ANTES do lance + avaliação do lance jogado (brancas, cp)."""
        infos = self.eng.analyse(board, chess.engine.Limit(depth=depth, time=4.0), multipv=multipv)
        lines = []
        for info in infos if isinstance(infos, list) else [infos]:
            pv = info.get("pv") or []
            if not pv:
                continue
            tmp = board.copy(stack=False)
            sans = []
            for mv in pv[:6]:
                sans.append(tmp.san(mv))
                tmp.push(mv)
            lines.append({"san": sans[0], "uci": pv[0].uci(), "cp": _cp(info["score"]), "pv": " ".join(sans)})
        played_cp = next((l["cp"] for l in lines if l["uci"] == played.uci()), None)
        if played_cp is None:
            info = self.eng.analyse(board, chess.engine.Limit(depth=max(10, depth - 4), time=2.0), root_moves=[played])
            played_cp = _cp(info["score"])
        return {"lines": lines, "played_cp": played_cp}
