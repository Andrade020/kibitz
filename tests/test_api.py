import json
import time

import chess

from think_aloud_chess import agent, app as app_module


def _new_game(client, **kw):
    body = {"human_color": "white", "model": "sonnet", "briefing": "off", "autosave": False, **kw}
    return client.post("/api/games", json=body).get_json()["id"]


def _fake_agent(monkeypatch, delay=0.0):
    def fake(game):
        time.sleep(delay)
        b = agent.rebuild(game)
        m = next(iter(b.legal_moves))
        return {"move": m, "san": b.san(m), "thought": {"summary": "s", "plan_notes": "PLANO", "message_to_human": "oi"},
                "meta": {"usage": {}}, "usage": {"tokens": 1, "cost": 0, "calls": 1}}
    monkeypatch.setattr(agent, "agent_move", fake)


def _wait(client, gid, plies, timeout=10):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = client.get(f"/api/games/{gid}").get_json()
        if len(s["moves"]) >= plies and not s["busy"]:
            return s
        time.sleep(0.05)
    raise AssertionError("agente não respondeu")


def test_health_and_static_pages(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    h = client.get("/api/health").get_json()
    assert h["version"] and "claude" in h and "stockfish" in h


def test_illegal_move_rejected_and_reasoning_hidden_during_game(client, monkeypatch):
    _fake_agent(monkeypatch)
    gid = _new_game(client)
    assert client.post(f"/api/games/{gid}/move", json={"uci": "e2e5"}).status_code == 400
    assert client.post(f"/api/games/{gid}/move", json={"uci": "e2e4"}).status_code == 200
    s = _wait(client, gid, 2)
    thought = s["moves"][1]["thought"]
    assert set(thought) == {"message_to_human"}               # jogo justo: raciocínio oculto
    peek = client.get(f"/api/games/{gid}?peek=1").get_json()
    assert peek["moves"][1]["thought"]["plan_notes"] == "PLANO"
    client.delete(f"/api/games/{gid}")


def test_undo_removes_agent_reply_and_memory(client, monkeypatch):
    _fake_agent(monkeypatch)
    gid = _new_game(client)
    client.post(f"/api/games/{gid}/move", json={"uci": "e2e4"})
    _wait(client, gid, 2)
    s = client.post(f"/api/games/{gid}/undo").get_json()
    assert len(s["moves"]) == 0 and s["turn"] == "white"
    assert app_module.load(gid)["plan_notes"] == ""
    assert client.post(f"/api/games/{gid}/undo").status_code == 400      # nada mais a desfazer
    client.delete(f"/api/games/{gid}")


def test_undo_while_agent_is_thinking_discards_late_result(client, monkeypatch):
    _fake_agent(monkeypatch, delay=0.6)
    gid = _new_game(client)
    client.post(f"/api/games/{gid}/move", json={"uci": "e2e4"})
    time.sleep(0.15)
    client.post(f"/api/games/{gid}/undo")
    time.sleep(1.0)                                                         # a chamada antiga termina e é descartada
    assert len(app_module.load(gid)["moves"]) == 0
    client.delete(f"/api/games/{gid}")


def test_export_import_roundtrip_and_validation(client, demo_game):
    raw = client.get(f"/api/games/{demo_game}/export").data
    r = client.post("/api/games/import", data=raw)
    assert r.status_code == 200
    new_id = r.get_json()["id"]
    assert new_id != demo_game and r.get_json()["review"]["status"] == "done"   # id novo, revisão preservada
    client.delete(f"/api/games/{new_id}")
    assert client.post("/api/games/import", data=b"lixo").status_code == 400
    g = json.loads(__import__("gzip").decompress(raw))
    g["moves"][3]["uci"] = "a1a8"                                                # lance ilegal no arquivo
    assert client.post("/api/games/import", data=json.dumps(g).encode()).status_code == 400


def test_cleanup_only_removes_exported_finished_games(client, demo_game):
    assert client.post("/api/games/cleanup").get_json()["removed"] == 0         # demo não foi exportada
    client.get(f"/api/games/{demo_game}/export")
    assert client.post("/api/games/cleanup").get_json()["removed"] >= 1


def test_demo_opens_with_review_and_is_readable(client, demo_game):
    g = client.get(f"/api/games/{demo_game}").get_json()
    assert g["status"] == "over" and g["review"]["moments"]
    assert all(m["status"] == "done" for m in g["review"]["moments"])
    assert chess.Board().is_valid()                                              # sanidade do ambiente
