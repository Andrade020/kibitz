import os
import stat
import sys
import textwrap

import chess
import pytest

from think_aloud_chess import audit, review, strong


def _game(sans):
    b, moves = chess.Board(), []
    for i, s in enumerate(sans):
        m = b.parse_san(s)
        moves.append({"ply": i + 1, "san": s, "uci": m.uci(), "by": "human" if i % 2 == 0 else "agent"})
        b.push(m)
    return {"id": "t", "moves": moves, "human_color": "white", "settings": {"model": "opus"}, "status": "over",
            "result": "1-0", "reason": "teste"}


def test_clean_moment_drops_illegal_suggestions_and_bad_squares():
    g = _game("e4 e5 Nf3 Nc6".split())
    pl = {"engine_kind": "strong", "engine_name": "x"}
    mo = review._skeleton(g, 3, chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"),
                          0.2, 0.1, 10, "Nf3", "g1f3", "Nf3 Nc6", [])
    out, dropped = review._clean_moment(g, {
        "title": "t", "explanation": "e", "concepts": ["centro"], "better": "Qh9",
        "arrows": [{"from": "e2", "to": "e4", "kind": "best", "label": "ok"}, {"from": "z9", "to": "a1", "kind": "plan", "label": ""}],
        "squares": [{"sq": "e4", "kind": "key"}, {"sq": "k1", "kind": "weak"}]}, mo)
    assert dropped == 1 and out["better"] == ""
    assert [a["kind"] for a in out["arrows"]] == ["played", "best"]               # seta inválida (z9) descartada
    assert out["squares"] == [{"sq": "e4", "kind": "key"}]


def test_clean_moment_adds_verified_suggestion_arrow():
    g = _game("e4 e5 Nf3 Nc6".split())
    b = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2")
    mo = review._skeleton(g, 3, b, 0, 0, 0, "Nf3", "g1f3", "", [])
    out, dropped = review._clean_moment(g, {"title": "", "explanation": "", "concepts": [], "better": "Bc4", "arrows": [], "squares": []}, mo)
    assert dropped == 0 and out["better"] == "Bc4" and any(a["from"] + a["to"] == "f1c4" for a in out["arrows"])


def test_shallow_fallback_when_no_strong_engine(monkeypatch):
    g = _game("e4 e5 Nf3 Nc6 Bb5 a6".split())
    g["audit"] = audit.audit_game(g["moves"])
    monkeypatch.setattr(strong, "find", lambda: None)
    pl = review.plan(g, "quick")
    assert pl["engine_kind"] == "shallow" and pl["moments"] and len(pl["curve"]) == len(g["moves"]) + 1


def test_selection_prefers_big_swings():
    series = {"cp": [0, 20, 10, 15, -400, -390, -380], "best": [None] * 7}
    moves = [{"by": "human" if i % 2 == 0 else "agent"} for i in range(6)]
    assert 4 in review.select_by_series(series, moves, 2)                       # o lance que derrubou a avaliação


@pytest.fixture()
def fake_engine(tmp_path):
    """Motor UCI de mentira (usa o motor raso do projeto) para testar a integração sem Stockfish."""
    src = textwrap.dedent('''
        import sys
        sys.path.insert(0, %r)
        import chess
        from think_aloud_chess import engine
        board, mpv = chess.Board(), 1
        for line in sys.stdin:
            t = line.split()
            if not t: continue
            c = t[0]
            if c == "uci":
                print("id name FakeFish\\noption name MultiPV type spin default 1 min 1 max 5\\nuciok", flush=True)
            elif c == "isready": print("readyok", flush=True)
            elif c == "setoption" and "MultiPV" in t: mpv = int(t[-1])
            elif c == "position":
                i = t.index("moves") if "moves" in t else len(t)
                board = chess.Board() if t[1] == "startpos" else chess.Board(" ".join(t[2:i]))
                for u in t[i + 1:]: board.push_uci(u)
            elif c == "go":
                sm = []
                if "searchmoves" in t:
                    sm = [chess.Move.from_uci(x) for x in t[t.index("searchmoves") + 1:] if len(x) in (4, 5) and x[0] in "abcdefgh"]
                moves = sm or list(board.legal_moves)
                res = [r for r in engine.analyze(board, depth=2, top_k=len(moves), extra=moves) if r["move"] in moves]
                for k, r in enumerate(res[:max(1, mpv)], 1):
                    sc = ("mate %%d" %% r["mate"]) if r["mate"] else ("cp %%d" %% r["score_cp"])
                    print("info depth 2 multipv %%d score %%s pv %%s" %% (k, sc, r["uci"]), flush=True)
                print("bestmove " + (res[0]["uci"] if res else "0000"), flush=True)
            elif c == "quit": break
    ''') % os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    py = tmp_path / "fake_uci.py"
    py.write_text(src, encoding="utf-8")
    if sys.platform == "win32":
        wrapper = tmp_path / "fake_uci.bat"
        wrapper.write_text(f'@echo off\r\n"{sys.executable}" "{py}"\r\n')
    else:
        wrapper = tmp_path / "fake_uci.sh"
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{py}"\n')
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
    return str(wrapper)


def test_uci_session_series_and_deep(fake_engine):
    assert strong.probe(fake_engine) == "FakeFish"
    moves = [{"uci": u} for u in "e2e4 e7e5 g1f3".split()]
    with strong.Session(fake_engine) as S:
        s = S.series(moves, depth=2)
        assert len(s["cp"]) == 4 and all(abs(c) <= strong.CLIP for c in s["cp"])
        b = chess.Board()
        b.push_uci("e2e4")
        d = S.deep(b, chess.Move.from_uci("e7e5"), depth=2, multipv=3)
        assert len(d["lines"]) == 3 and isinstance(d["played_cp"], int)


def test_plan_uses_strong_engine_when_available(fake_engine, monkeypatch):
    g = _game("e4 e5 Nf3 Nc6".split())
    monkeypatch.setattr(strong, "find", lambda: fake_engine)
    pl = review.plan(g, "quick")
    assert pl["engine_kind"] == "strong" and pl["engine_name"] == "FakeFish" and pl["moments"]
