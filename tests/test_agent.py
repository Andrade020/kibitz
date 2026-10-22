import chess
import pytest

from kibitz import agent


def test_resolve_move_accepts_san_uci_and_annotations():
    b = chess.Board()
    assert agent.resolve_move(b, "e4").uci() == "e2e4"
    assert agent.resolve_move(b, "1.e4").uci() == "e2e4"
    assert agent.resolve_move(b, "Nf3!?").uci() == "g1f3"
    assert agent.resolve_move(b, "g1f3").uci() == "g1f3"


def test_resolve_move_rejects_illegal_and_garbage():
    b = chess.Board()
    for bad in ("Ke2", "e5", "Qh5", "xyz", "", None):
        assert agent.resolve_move(b, bad) is None


def test_castling_notation_variants():
    b = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
    assert agent.resolve_move(b, "0-0").uci() == "e1g1"
    assert agent.resolve_move(b, "O-O-O").uci() == "e1c1"


def test_review_triggers_are_quiet_by_default():
    probe = {"mate_risk": False, "risky": False, "new_risk": []}
    out = {"confidence": 3}
    assert agent.should_review("auto", probe, 10, 20, out) is None            # lance normal
    assert agent.should_review("off", {**probe, "mate_risk": True}, 0, 0, out) is None
    assert agent.should_review("auto", {**probe, "mate_risk": True}, 0, 0, out)  # mate sempre dispara
    assert agent.should_review("auto", probe, -300, 0, out)                    # motor vê perda grande
    assert agent.should_review("auto", probe, -300, 900, out) is None          # posição decidida
    assert agent.should_review("auto", probe, -300, 0, out, cooldown=True) is None
    assert agent.should_review("auto", {**probe, "risky": True, "new_risk": ["Nd4"]}, 0, 20, {"confidence": 2})


def test_agent_move_retries_illegal_then_falls_back(monkeypatch):
    calls = []

    def fake_llm(prompt, *a, **k):
        calls.append(prompt)
        return {"structured": {"move": "Qh9", "eval_pawns": 0, "confidence": 3, "summary": "x", "plan_notes": "",
                               "blunder_check": ""}, "text": "", "usage": {"tokens": 1, "cost": 0}}

    monkeypatch.setattr(agent, "call_llm", fake_llm)
    game = {"settings": {"model": "opus", "effort": "low", "reviewer": "off", "budget_usd": 0, "assist": "none", "facts": False},
            "usage": {}, "moves": [{"ply": 1, "san": "e4", "uci": "e2e4", "by": "human"}], "plan_notes": "", "briefing": ""}
    r = agent.agent_move(game)
    assert len(calls) == 3 and r["meta"]["fallback"] is True      # 3 tentativas ilegais -> motor raso
    assert "ILEGAL" in calls[1]
    assert chess.Board("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1").is_legal(r["move"])


def test_eval_is_stored_from_white_point_of_view(monkeypatch):
    out = {"move": "e5", "eval_pawns": -2.0, "confidence": 3, "summary": "x", "plan_notes": "", "blunder_check": ""}
    monkeypatch.setattr(agent, "call_llm", lambda *a, **k: {"structured": dict(out), "text": "", "usage": {"tokens": 1, "cost": 0}})
    game = {"settings": {"model": "opus", "effort": "low", "reviewer": "off", "budget_usd": 0, "assist": "none", "facts": False},
            "usage": {}, "moves": [{"ply": 1, "san": "e4", "uci": "e2e4", "by": "human"}], "plan_notes": "", "briefing": ""}
    r = agent.agent_move(game)       # o Claude joga de pretas e diz -2 (ele está pior) => +2 para as brancas
    assert r["thought"]["eval_pawns"] == 2.0 and r["thought"]["eval_own"] == -2.0


def test_missing_claude_cli_gives_actionable_error(monkeypatch):
    monkeypatch.setattr(agent, "find_claude", lambda: None)
    with pytest.raises(agent.AgentError, match="Claude Code"):
        agent.call_claude("x", agent.PROMPTS / "player.md", "opus")
