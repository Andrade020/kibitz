"""Servidor local: python app.py  ->  http://127.0.0.1:5000"""
import gzip
import io
import json
import re
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import uuid
from pathlib import Path

import chess
from flask import Flask, jsonify, request, send_from_directory, send_file, abort

from . import __version__, agent, audit, autosave, paths, providers, review, strong

paths.ensure()
GAMES = paths.GAMES
app = Flask(__name__, static_folder=str(paths.STATIC), static_url_path="/static")
LOCK = threading.RLock()
BUSY = {}  # game_id -> mensagem de status enquanto o agente trabalha


MAX_IMPORT = 20 * 1024 * 1024


def path(gid):
    if not gid.isalnum():
        abort(404)
    return GAMES / f"{gid}.json.gz"


def _legacy(gid):
    return GAMES / f"{gid}.json"


def _restore_fens(g):
    """fen_after não é gravado em disco (dá para recalcular); recria na leitura."""
    b = chess.Board()
    for m in g["moves"]:
        b.push_uci(m["uci"])
        m["fen_after"] = b.fen()
    return g


def _strip(g):
    g = dict(g)
    g["moves"] = [{k: v for k, v in m.items() if k != "fen_after"} for m in g["moves"]]
    return g


def pack(g):
    return gzip.compress(json.dumps(_strip(g), ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)


def unpack(raw):
    if raw[:2] == bytes([0x1f, 0x8b]):
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def load(gid):
    p = path(gid)
    if p.exists():
        return _restore_fens(unpack(p.read_bytes()))
    if gid.isalnum() and _legacy(gid).exists():  # formato antigo, migra ao salvar
        return _restore_fens(json.loads(_legacy(gid).read_text(encoding="utf-8")))
    abort(404)


REVIEWING = {}   # game_id -> True enquanto o professor trabalha
REVIEW_ERR = {}  # game_id -> mensagem da última falha
REVIEW_PROGRESS = {}  # game_id -> {stage, done, total}
AUDIT = {}  # game_id -> (feitos, total) enquanto a auditoria local roda


def stats_of(g):
    if not g.get("audit"):
        return None
    return audit.summarize(g["audit"], g["moves"], g["human_color"])


def save(g):
    with LOCK:
        path(g["id"]).write_bytes(pack(g))
        _legacy(g["id"]).unlink(missing_ok=True)
        if g["settings"].get("autosave"):
            try:
                autosave.write(g, stats_of(g))
            except Exception:  # autosave nunca pode derrubar a partida
                pass
        if g["status"] == "over" and not g.get("audit") and g["id"] not in AUDIT and g["moves"]:
            AUDIT[g["id"]] = (0, len(g["moves"]))
            threading.Thread(target=run_audit, args=(g["id"],), daemon=True).start()


def run_audit(gid):
    try:
        g = load(gid)
        res = audit.audit_game(g["moves"], progress=lambda i, n: AUDIT.__setitem__(gid, (i, n)))
        with LOCK:
            g = load(gid)
            if len(g["moves"]) != len(res):  # lance desfeito durante a auditoria
                return
            g["audit"] = res
            AUDIT.pop(gid, None)
            save(g)
    except Exception:  # noqa
        pass
    finally:
        AUDIT.pop(gid, None)


def all_game_files():
    return list(GAMES.glob("*.json.gz")) + list(GAMES.glob("*.json"))


def board_of(g):
    return agent.rebuild(g)


def end_check(g):
    b = board_of(g)
    if g["status"] != "ongoing":
        return
    res = None
    if b.is_checkmate():
        res = ("0-1" if b.turn == chess.WHITE else "1-0", "xeque-mate")
    elif b.is_stalemate():
        res = ("1/2-1/2", "afogamento")
    elif b.is_insufficient_material():
        res = ("1/2-1/2", "material insuficiente")
    elif b.can_claim_threefold_repetition() or b.is_repetition(3):
        res = ("1/2-1/2", "tripla repetição")
    elif b.is_seventyfive_moves():
        res = ("1/2-1/2", "regra dos 75 lances")
    elif b.can_claim_fifty_moves():
        res = ("1/2-1/2", "regra dos 50 lances")
    if res:
        g["status"], g["result"], g["reason"] = "over", res[0], res[1]


def add_usage(g, u):
    g["usage"]["tokens"] = g["usage"].get("tokens", 0) + u.get("tokens", 0)
    g["usage"]["cost"] = g["usage"].get("cost", 0) + u.get("cost", 0)
    g["usage"]["calls"] = g["usage"].get("calls", 0) + u.get("calls", 1)


def agent_color(g):
    return chess.BLACK if g["human_color"] == "white" else chess.WHITE


def agent_turn(g):
    return g["status"] == "ongoing" and board_of(g).turn == agent_color(g)


EPOCH = {}  # game_id -> contador; muda quando um lance é desfeito, invalidando chamadas em andamento


def run_agent(gid):
    with LOCK:
        if gid in BUSY:
            return
        BUSY[gid] = "pensando"
        my = EPOCH.get(gid, 0)
    agent.set_ctx(gid)

    def stale():
        return EPOCH.get(gid, 0) != my

    try:
        g = load(gid)
        if not g.get("briefing_done"):
            BUSY[gid] = "preparando briefing"
            text, u, berr = "", None, None
            try:
                text, u = agent.make_briefing(agent_color(g), g["settings"]["briefing"], g["settings"]["model"])
            except agent.AgentError as e:
                berr = str(e)
            with LOCK:
                if stale():
                    return
                g = load(gid)  # recarrega: nunca grava por cima de um estado mais novo
                g["briefing"], g["briefing_done"] = text, True
                if berr:
                    g["briefing_error"] = berr
                if u:
                    add_usage(g, u)
                save(g)
        BUSY[gid] = "pensando"
        r = agent.agent_move(g)
        with LOCK:
            if stale():
                return
            f = load(gid)
            if len(f["moves"]) != len(g["moves"]):
                return
            b = board_of(f)
            mv = r["move"]
            san = b.san(mv)
            b.push(mv)
            f["moves"].append({
                "ply": len(f["moves"]) + 1, "san": san, "uci": mv.uci(), "by": "agent",
                "fen_after": b.fen(), "thought": r["thought"], "meta": r["meta"], "t": time.time(),
            })
            f["plan_notes"] = (r["thought"].get("plan_notes") or "")[:700]
            f["error"] = None
            add_usage(f, r["usage"])
            end_check(f)
            save(f)
    except Exception as e:  # noqa
        with LOCK:
            if not stale():
                f = load(gid)
                f["error"] = f"{type(e).__name__}: {e}"
                save(f)
    finally:
        with LOCK:
            if not stale():
                BUSY.pop(gid, None)


def spawn_agent(gid):
    threading.Thread(target=run_agent, args=(gid,), daemon=True).start()


def public(g, peek=False):
    """Esconde o raciocínio do agente enquanto a partida corre (jogo justo), a menos que peek."""
    g = json.loads(json.dumps(g))
    b = board_of(g)
    hide = g["status"] == "ongoing" and not peek
    for m in g["moves"]:
        if hide:
            t = m.get("thought") or {}
            m["thought"] = {"message_to_human": t.get("message_to_human", "")} if t else None
            m.pop("meta", None)
    if hide:
        g.pop("briefing", None)
        g.pop("plan_notes", None)
        g.pop("audit", None)
    g["stats"] = None if hide else stats_of(g)
    g["audit_progress"] = AUDIT.get(g["id"])
    g["review_busy"] = bool(REVIEWING.get(g["id"]))
    g["review_progress"] = REVIEW_PROGRESS.get(g["id"])
    g["review_error"] = REVIEW_ERR.get(g["id"])
    g["autosave_file"] = (autosave.file_for(g).relative_to(paths.DATA).as_posix()
                          if g["settings"].get("autosave") else None)
    g["fen"] = b.fen()
    g["turn"] = "white" if b.turn == chess.WHITE else "black"
    g["legal"] = [m.uci() for m in b.legal_moves] if g["status"] == "ongoing" and not agent_turn(g) else []
    g["busy"] = BUSY.get(g["id"])
    g["check"] = b.is_check()
    g["hidden"] = hide
    return g


@app.get("/")
def index():
    return send_from_directory(paths.STATIC, "index.html")


@app.get("/api/games")
def games_list():
    out, total = [], 0
    for p in sorted(all_game_files(), key=lambda x: -x.stat().st_mtime):
        try:
            g = unpack(p.read_bytes())
        except Exception:
            continue
        size = p.stat().st_size
        total += size
        out.append({"id": g["id"], "created": g["created"], "human_color": g["human_color"], "status": g["status"],
                    "result": g.get("result"), "plies": len(g["moves"]), "cost": g["usage"].get("cost", 0),
                    "model": g["settings"]["model"], "size": size, "exported": bool(g.get("exported_at"))})
    return jsonify({"games": out, "total_size": total})


def _model_ok(m):
    try:
        return providers.parse_model(m) is not None
    except ValueError:
        return False


@app.post("/api/games")
def games_new():
    d = request.get_json(force=True)
    color = d.get("human_color", "white")
    if color == "random":
        color = "white" if uuid.uuid4().int % 2 else "black"
    g = {
        "id": uuid.uuid4().hex[:10], "created": time.time(), "human_color": color, "status": "ongoing",
        "result": None, "reason": None, "moves": [], "plan_notes": "", "briefing": "", "briefing_done": False,
        "comments": [], "usage": {"tokens": 0, "cost": 0.0, "calls": 0}, "error": None,
        "settings": {
            "model": d.get("model", "opus") if (not d.get("model", "").startswith("api:") or _model_ok(d["model"])) else "opus", "effort": d.get("effort", "medium"),
            "briefing": d.get("briefing", "memory"), "reviewer": d.get("reviewer", "auto"),
            "budget_usd": float(d.get("budget_usd", 8)),
            "assist": d.get("assist", "full") if d.get("assist") in ("full", "material", "none") else "full",
            "facts": bool(d.get("facts", True)), "autosave": bool(d.get("autosave", True)),
        },
    }
    save(g)
    if agent_turn(g):
        spawn_agent(g["id"])
    return jsonify(public(g))


@app.get("/api/games/<gid>")
def games_get(gid):
    return jsonify(public(load(gid), peek=request.args.get("peek") == "1"))


@app.post("/api/games/<gid>/move")
def games_move(gid):
    with LOCK:
        g = load(gid)
        if g["status"] != "ongoing" or agent_turn(g) or gid in BUSY:
            return jsonify({"error": "não é a sua vez"}), 400
        b = board_of(g)
        uci = request.get_json(force=True).get("uci", "")
        try:
            mv = chess.Move.from_uci(uci)
        except Exception:
            return jsonify({"error": "lance inválido"}), 400
        if mv not in b.legal_moves:
            return jsonify({"error": "lance ilegal"}), 400
        san = b.san(mv)
        b.push(mv)
        g["moves"].append({"ply": len(g["moves"]) + 1, "san": san, "uci": uci, "by": "human",
                           "fen_after": b.fen(), "thought": None, "t": time.time()})
        end_check(g)
        save(g)
    if agent_turn(g):
        spawn_agent(gid)
    return jsonify(public(g))


@app.post("/api/games/<gid>/autosave")
def games_autosave(gid):
    with LOCK:
        g = load(gid)
        g["settings"]["autosave"] = bool(request.get_json(force=True).get("on"))
        save(g)
    return jsonify(public(g))


@app.post("/api/games/<gid>/audit")
def games_audit(gid):
    with LOCK:
        g = load(gid)
        if g["status"] != "over":
            return jsonify({"error": "disponível só depois do fim da partida"}), 400
        if gid not in AUDIT:
            g.pop("audit", None)
            save(g)  # dispara a auditoria
    return jsonify(public(load(gid)))


@app.post("/api/games/<gid>/undo")
def games_undo(gid):
    """Volta à posição anterior ao seu último lance. O raciocínio/memória do agente depois dele é apagado."""
    with LOCK:
        g = load(gid)
        mv = g["moves"]
        last_h = max((i for i, m in enumerate(mv) if m["by"] == "human"), default=None)
        if last_h is None:
            return jsonify({"error": "não há lance seu para desfazer"}), 400
        EPOCH[gid] = EPOCH.get(gid, 0) + 1  # invalida qualquer chamada do agente em andamento
        BUSY.pop(gid, None)
        AUDIT.pop(gid, None)
        agent.kill(gid)
        del mv[last_h:]
        g["status"], g["result"], g["reason"], g["error"] = "ongoing", None, None, None
        g.pop("audit", None)
        g.pop("review", None)
        REVIEWING.pop(gid, None)  # cancela uma revisão em andamento
        REVIEW_PROGRESS.pop(gid, None)
        g["comments"] = [c for c in g.get("comments", []) if c["ply"] <= len(mv)]
        prev = next((m for m in reversed(mv) if m.get("thought")), None)
        g["plan_notes"] = ((prev["thought"].get("plan_notes") or "")[:700]) if prev else ""
        g["undos"] = g.get("undos", 0) + 1
        save(g)
    return jsonify(public(g))


class _Cancelled(Exception):
    pass


def run_review(gid, model, effort, depth, token):
    """Revisão em etapas; cada etapa é gravada assim que fica pronta (a tela mostra conforme chega)."""
    agent.set_ctx(gid)

    def upd(fn):
        with LOCK:
            if REVIEWING.get(gid) != token:
                raise _Cancelled()
            g = load(gid)
            if g["status"] != "over":
                raise _Cancelled()
            fn(g)
            save(g)

    def prog(stage, done, total):
        REVIEW_PROGRESS[gid] = {"stage": stage, "done": done, "total": total}

    try:
        g = load(gid)
        REVIEW_PROGRESS[gid] = {"stage": "engine", "done": 0, "total": len(g["moves"]) + 1}
        pl = review.plan(g, depth, prog)  # local, sem tokens
        ctx = review.new_context(g, pl)

        def start(g):
            g["review"] = review.skeleton_review(pl, model, effort, depth)
        upd(start)

        lock_tok = threading.Lock()
        done_n = [0]

        def work(mo):
            last = None
            for _ in range(2):  # 1 retentativa por momento
                try:
                    out, dropped, u = review.explain_moment(g, ctx, mo, model, effort)
                    return mo["ply"], out, dropped, u, None
                except _Cancelled:
                    raise
                except Exception as e:  # noqa
                    last = f"{type(e).__name__}: {str(e)[:160]}"
            return mo["ply"], None, 0, {}, last

        def merge(ply, out, dropped, u, err):
            def f(g):
                rv = g["review"]
                mo = next(m for m in rv["moments"] if m["ply"] == ply)
                if out:
                    mo.update(out)
                    rv["dropped"] += dropped
                else:
                    mo["status"], mo["error"] = "error", err
                if u:
                    for k in ("tokens", "cost"):
                        rv["usage"][k] = rv["usage"].get(k, 0) + u.get(k, 0)
                    rv["usage"]["calls"] += 1
                    add_usage(g, u)
            upd(f)

        with ThreadPoolExecutor(max_workers=3) as pool:
            futs = [pool.submit(work, mo) for mo in pl["moments"]]
            for fu in as_completed(futs):
                merge(*fu.result())
                with lock_tok:
                    done_n[0] += 1
                    prog("moments", done_n[0], len(futs))

        prog("synth", 0, 1)
        g = load(gid)
        rv = g["review"]
        try:
            syn, u = review.synthesize(g, ctx, rv, model, effort)
        except _Cancelled:
            raise
        except Exception as e:  # noqa
            syn, u = None, {}
            REVIEW_ERR[gid] = f"síntese falhou: {type(e).__name__}: {str(e)[:160]} (os momentos estão salvos)"

        def fin(g):
            r = g["review"]
            if syn:
                r.update(syn)
                for k in ("tokens", "cost"):
                    r["usage"][k] = r["usage"].get(k, 0) + u.get(k, 0)
                r["usage"]["calls"] += 1
                add_usage(g, u)
            r["status"] = "done"
        upd(fin)
    except _Cancelled:
        pass
    except Exception as e:  # noqa
        REVIEW_ERR[gid] = f"{type(e).__name__}: {e}"
        try:
            upd(lambda g: g.get("review") and g["review"].update(status="error"))
        except Exception:  # noqa
            pass
    finally:
        with LOCK:
            if REVIEWING.get(gid) == token:
                REVIEWING.pop(gid, None)
                REVIEW_PROGRESS.pop(gid, None)


@app.post("/api/games/<gid>/review")
def games_review(gid):
    d = request.get_json(force=True)
    with LOCK:
        g = load(gid)
        if g["status"] != "over":
            return jsonify({"error": "disponível só depois do fim da partida"}), 400
        if not g.get("audit") and not strong.find():
            return jsonify({"error": "sem motor forte, aguarde a auditoria local terminar (alguns minutos)"}), 400
        if REVIEWING.get(gid):
            return jsonify({"error": "já está em andamento"}), 400
        model = d.get("model") or g["settings"]["model"]
        if model.startswith("api:") and not _model_ok(model):
            return jsonify({"error": "provedor não encontrado"}), 400
        effort = d.get("effort") if d.get("effort") in ("low", "medium", "high", "xhigh") else "medium"
        depth = d.get("depth") if d.get("depth") in review.DEPTHS else "full"
        token = uuid.uuid4().hex
        REVIEWING[gid] = token
        REVIEW_ERR.pop(gid, None)
    threading.Thread(target=run_review, args=(gid, model, effort, depth, token), daemon=True).start()
    return jsonify(public(load(gid)))


@app.post("/api/games/<gid>/retry")
def games_retry(gid):
    g = load(gid)
    if agent_turn(g) and gid not in BUSY:
        spawn_agent(gid)
    return jsonify(public(g))


@app.post("/api/games/<gid>/resign")
def games_resign(gid):
    with LOCK:
        g = load(gid)
        if g["status"] == "ongoing":
            g["status"], g["reason"] = "over", "abandono"
            g["result"] = "0-1" if g["human_color"] == "white" else "1-0"
            save(g)
    return jsonify(public(g))


@app.post("/api/games/<gid>/draw")
def games_draw(gid):
    """Humano oferece empate; o agente aceita se a última avaliação dele estiver dentro de ±0.5."""
    with LOCK:
        g = load(gid)
        if g["status"] != "ongoing" or gid in BUSY:
            return jsonify({"error": "indisponível agora"}), 400
        last = next((m for m in reversed(g["moves"]) if m.get("thought")), None)
        ev = (last["thought"].get("eval_pawns", 0) if last else 0)
        mine = ev if agent_color(g) == chess.WHITE else -ev
        if mine <= 0.5:
            g["status"], g["result"], g["reason"] = "over", "1/2-1/2", "empate por acordo"
            save(g)
            return jsonify({"accepted": True, "game": public(g)})
    return jsonify({"accepted": False, "game": public(g)})


@app.post("/api/games/<gid>/ask")
def games_ask(gid):
    g = load(gid)
    d = request.get_json(force=True)
    ply, q = int(d.get("ply", 0)), (d.get("question") or "").strip()
    if not q or not (0 <= ply <= len(g["moves"])):
        return jsonify({"error": "pergunta/lance inválido"}), 400
    try:
        ans, u = agent.ask_about(g, ply, q, g["settings"]["model"])
    except agent.AgentError as e:
        return jsonify({"error": str(e)}), 500
    with LOCK:
        g = load(gid)
        g["comments"].append({"ply": ply, "question": q, "answer": ans, "t": time.time()})
        add_usage(g, u)
        save(g)
    return jsonify({"answer": ans, "comments": g["comments"], "usage": g["usage"]})


CLI_MODELS = [("opus", "Claude Opus (CLI)"), ("sonnet", "Claude Sonnet (CLI)"), ("fable", "Claude Fable (CLI)")]


_HEALTH = {"t": 0, "claude": None, "stockfish": None}
SETUP = {"installing": False, "log": "", "ok": None}


@app.get("/api/ping")
def ping():
    """Instantâneo: usado pelo lançador para saber se já existe uma instância rodando."""
    return jsonify({"app": "think-aloud-chess", "version": __version__})


@app.get("/api/health")
def health():
    """Estado da configuração (o status do Claude é cacheado por 15 s: chamar o CLI custa ~1 s)."""
    if request.args.get("refresh") == "1" or time.time() - _HEALTH["t"] > 15 or SETUP["installing"]:
        _HEALTH["claude"], _HEALTH["stockfish"], _HEALTH["t"] = agent.claude_status(), strong.status(), time.time()
    return jsonify({
        "version": __version__, "claude": _HEALTH["claude"],
        "api_providers": sum(1 for p in providers.list_public() if p["ready"]),
        "stockfish": _HEALTH["stockfish"], "data_dir": str(paths.DATA),
        "demo": (paths.EXAMPLES / "demo-game.xadrez.gz").exists(),
        "can_auto_install": sys.platform == "win32" and bool(shutil.which("winget")),
        "setup": {"installing": SETUP["installing"], "log": SETUP["log"][-400:], "ok": SETUP["ok"]},
    })


def _run_install():
    try:
        r = subprocess.run(["winget", "install", "--id", "Anthropic.ClaudeCode", "--exact", "--silent",
                            "--accept-package-agreements", "--accept-source-agreements"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
                           creationflags=agent.NOWIN)
        SETUP["log"], SETUP["ok"] = (r.stdout or "") + (r.stderr or ""), r.returncode == 0 or bool(agent.find_claude())
    except Exception as e:  # noqa
        SETUP["log"], SETUP["ok"] = f"{type(e).__name__}: {e}", False
    finally:
        SETUP["installing"] = False
        _HEALTH["t"] = 0


@app.post("/api/setup/install-claude")
def setup_install():
    """Instala o Claude Code pelo winget (pacote oficial Anthropic.ClaudeCode)."""
    if not (sys.platform == "win32" and shutil.which("winget")):
        return jsonify({"error": "instalação automática só no Windows com winget; veja o README para instalar manualmente"}), 400
    with LOCK:
        if SETUP["installing"]:
            return jsonify({"ok": True})
        SETUP.update(installing=True, log="", ok=None)
    threading.Thread(target=_run_install, daemon=True).start()
    return jsonify({"ok": True})


@app.post("/api/setup/login-claude")
def setup_login():
    """Abre uma janela de terminal com `claude auth login` (o login acontece no navegador)."""
    exe = agent.find_claude()
    if not exe:
        return jsonify({"error": "Claude Code ainda não está instalado"}), 400
    try:
        if sys.platform == "win32":
            subprocess.Popen(["cmd", "/c", "start", "Entrar no Claude", exe, "auth", "login"])
        elif sys.platform == "darwin":
            subprocess.Popen(["osascript", "-e", f'tell app "Terminal" to do script "\\"{exe}\\" auth login"'])
        else:
            subprocess.Popen(["x-terminal-emulator", "-e", exe, "auth", "login"])
    except Exception as e:  # noqa
        return jsonify({"error": f"não consegui abrir o terminal: {type(e).__name__}"}), 500
    _HEALTH["t"] = 0
    return jsonify({"ok": True})


@app.post("/api/demo")
def demo_open():
    """Abre a partida de demonstração (já com revisão do professor): explorar a revisão sem gastar tokens."""
    src = paths.EXAMPLES / "demo-game.xadrez.gz"
    if not src.exists():
        return jsonify({"error": "partida de demonstração não encontrada"}), 404
    g = unpack(src.read_bytes())
    with LOCK:
        if not path(g["id"]).exists():
            save(g)
    return jsonify({"id": g["id"]})


@app.get("/api/engine")
def engine_get():
    return jsonify(strong.status())


@app.post("/api/engine")
def engine_set():
    path = (request.get_json(force=True).get("path") or "").strip().strip('"')
    if path:
        try:
            strong.probe(path)
        except Exception as e:  # noqa
            return jsonify({"error": f"não consegui abrir como motor UCI ({type(e).__name__})"}), 400
    strong.set_path(path)
    return jsonify(strong.status())


@app.get("/api/models")
def models_list():
    out = [{"value": v, "label": l} for v, l in CLI_MODELS]
    for p in providers.list_public():
        if p["ready"]:
            out += [{"value": f"api:{p['id']}/{m}", "label": f"{m} — {p['name']} (API)"} for m in p["models"]]
    return jsonify(out)


@app.get("/api/providers")
def providers_get():
    return jsonify(providers.list_public())


@app.post("/api/providers")
def providers_set():
    d = request.get_json(force=True)
    pid = providers.upsert(d)
    return jsonify({"id": pid, "providers": providers.list_public()})


@app.post("/api/providers/<pid>/fetch_models")
def providers_fetch(pid):
    p = providers.get(pid)
    if not p or not (p["base_url"] and p["api_key"]):
        return jsonify({"error": "preencha URL base e chave primeiro"}), 400
    try:
        ms = providers.fetch_models(p)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 502
    providers.upsert({"id": pid, "models": ms})
    return jsonify({"models": ms, "providers": providers.list_public()})


@app.delete("/api/providers/<pid>")
def providers_del(pid):
    providers.remove(pid)
    return jsonify(providers.list_public())


@app.get("/api/games/<gid>/export")
def games_export(gid):
    g = load(gid)
    with LOCK:
        g["exported_at"] = time.time()
        save(g)
    return send_file(io.BytesIO(pack(g)), mimetype="application/gzip", as_attachment=True,
                     download_name=f"xadrez_{time.strftime('%Y%m%d', time.localtime(g['created']))}_{gid}.xadrez.gz")


@app.post("/api/games/import")
def games_import():
    raw = request.get_data()
    if not raw or len(raw) > MAX_IMPORT:
        return jsonify({"error": "arquivo vazio ou grande demais (máx. 20 MB)"}), 400
    try:
        g = unpack(raw)
        assert isinstance(g, dict) and isinstance(g["moves"], list)
        for k in ("id", "created", "human_color", "status", "usage", "settings"):
            assert k in g
        b = chess.Board()
        for i, m in enumerate(g["moves"]):
            b.push_uci(m["uci"])  # levanta se algum lance for ilegal
            m["ply"], m["by"] = i + 1, m.get("by", "human")
        g.setdefault("comments", [])
        g.setdefault("plan_notes", "")
        g.setdefault("briefing", "")
        g.setdefault("briefing_done", True)
        g["error"] = None
        g["human_color"] = "black" if g["human_color"] == "black" else "white"
    except Exception as e:  # noqa
        return jsonify({"error": f"arquivo inválido: {type(e).__name__}"}), 400
    if not re.fullmatch(r"[A-Za-z0-9]{1,16}", str(g["id"])) or path(str(g["id"])).exists() or _legacy(str(g["id"])).exists():
        g["id"] = uuid.uuid4().hex[:10]  # evita sobrescrever uma partida existente
    g["exported_at"] = g.get("exported_at") or time.time()
    save(g)
    return jsonify(public(g, peek=False))


@app.post("/api/games/cleanup")
def games_cleanup():
    """Apaga só partidas encerradas que já foram exportadas para arquivo."""
    n = freed = 0
    for p in all_game_files():
        try:
            g = unpack(p.read_bytes())
        except Exception:
            continue
        if g.get("status") == "over" and g.get("exported_at") and g["id"] not in BUSY:
            freed += p.stat().st_size
            p.unlink()
            n += 1
    return jsonify({"removed": n, "freed": freed})


@app.delete("/api/games/<gid>")
def games_delete(gid):
    path(gid).unlink(missing_ok=True)
    _legacy(gid).unlink(missing_ok=True)
    return jsonify({"ok": True})

