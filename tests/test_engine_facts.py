import chess

from think_aloud_chess import engine, facts


def test_engine_finds_mate_in_one():
    b = chess.Board("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1")  # Rd8#
    best = engine.analyze(b, depth=2, top_k=3)[0]
    assert best["san"] == "Rd8#" and best["mate"]


def test_engine_takes_hanging_queen():
    b = chess.Board("4k3/8/8/3q4/8/8/8/3RK3 w - - 0 1")
    assert engine.analyze(b, depth=2, top_k=3)[0]["san"] == "Rxd5"


def test_material_only_mode_ignores_position():
    b = chess.Board()
    assert engine.evaluate(b, positional=False) == 0


def test_facts_flag_hanging_piece_and_threats():
    b = chess.Board("4k3/8/8/3q4/8/8/8/3RK3 b - - 0 1")  # dama preta atacada pela torre, sem defesa
    risk = facts.en_prise(b, chess.BLACK)
    assert any(chess.square_name(sq) == "d5" for sq, *_ in risk)
    assert "XEQUE-MATE" in " ".join(facts.pass_threats(chess.Board("6k1/5ppp/8/8/8/8/5PPP/3R2K1 b - - 0 1")))


def test_board_ascii_has_files_and_ranks():
    txt = facts.board_ascii(chess.Board())
    assert txt.splitlines()[0].strip() == "a b c d e f g h" and len(txt.splitlines()) == 10


def test_probe_flags_mate_risk():
    b = chess.Board("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1")
    cand = next(c for c in engine.analyze(b, depth=2, top_k=5) if c["san"] == "Rd8#")
    assert "DÁ XEQUE-MATE" in facts.probe(b, cand)["flags"]
