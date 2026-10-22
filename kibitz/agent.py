"""Cérebro do agente: monta o estado, chama `claude -p` (sem ferramentas), valida o lance.

Economia de tokens:
- Cada lance é uma chamada SEM histórico de conversa: o prompt de sistema é fixo (cache de prompt
  do Claude Code) e o estado vem comprimido (diagrama + fatos + memória curta escrita pelo próprio agente).
  Assim o custo por lance NÃO cresce com o tamanho da partida.
- Um revisor Haiku barato só é chamado quando há sinal de risco.
- Orçamento por partida: ao estourar, cai para esforço baixo e desliga o revisor.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import chess

from . import engine, facts, paths, providers

PROMPTS = paths.PROMPTS
SANDBOX = paths.SANDBOX

PLAYER_SCHEMA = {
    "type": "object",
    "properties": {
        "position_read": {"type": "string", "description": "Leitura da posicao e do ultimo lance do adversario"},
        "opponent_threats": {"type": "string", "description": "Ameacas do adversario"},
        "plan": {"type": "string", "description": "Plano estrategico em linguagem humana"},
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "move": {"type": "string"},
                    "idea": {"type": "string"},
                    "risk": {"type": "string"},
                    "line": {"type": "string", "description": "variante forcada principal"},
                },
                "required": ["move", "idea", "risk", "line"],
            },
        },
        "decision": {"type": "string", "description": "Por que o escolhido supera os outros"},
        "blunder_check": {"type": "string", "description": "Verificacao anti-erro apos o lance"},
        "move": {"type": "string", "description": "Lance em SAN, exatamente um dos legais"},
        "eval_pawns": {"type": "number", "description": "Avaliacao em peoes do SEU ponto de vista: positivo = voce esta melhor, negativo = voce esta pior"},
        "confidence": {"type": "integer", "description": "1 a 5"},
        "summary": {"type": "string", "description": "Resumo de uma linha, ate 140 caracteres"},
        "plan_notes": {"type": "string", "description": "Memoria para o proximo lance, ate 500 caracteres"},
        "message_to_human": {"type": "string", "description": "Frase curta de mesa, pode ser vazia"},
    },
    "required": ["position_read", "opponent_threats", "plan", "candidates", "decision",
                 "blunder_check", "move", "eval_pawns", "confidence", "summary", "plan_notes"],
}

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["ok", "problem"]},
        "problem": {"type": "string"},
    },
    "required": ["verdict", "problem"],
}


class AgentError(Exception):
    pass


# Chamadas em andamento por partida, para poder cancelar (desfazer lance enquanto o agente pensa)
_ctx = threading.local()
_plock = threading.Lock()
PROCS = {}


def set_ctx(gid):
    _ctx.gid = gid


NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows: não abrir janela de console ao chamar o CLI


def find_claude():
    """Caminho do CLI do Claude Code (PATH ou locais comuns, útil quando o app abre fora de um terminal)."""
    p = shutil.which("claude")
    if p:
        return p
    home = Path.home()
    cands = []
    for var, rel in (("LOCALAPPDATA", "Microsoft/WinGet/Links/claude.exe"), ("APPDATA", "npm/claude.cmd")):
        if os.environ.get(var):
            cands.append(Path(os.environ[var]) / rel)
    cands += [home / ".local/bin/claude.exe", home / ".local/bin/claude", home / ".npm-global/claude.cmd",
              home / ".npm-global/bin/claude", Path("/usr/local/bin/claude"), Path("/opt/homebrew/bin/claude")]
    return next((str(c) for c in cands if c.exists()), None)


def claude_status():
    """{installed, logged_in, path}. logged_in=None quando não deu para saber."""
    exe = find_claude()
    if not exe:
        return {"installed": False, "logged_in": False, "path": None}
    try:
        SANDBOX.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([exe, "auth", "status", "--json"], capture_output=True, text=True, encoding="utf-8",
                           timeout=30, cwd=SANDBOX, creationflags=NOWIN)
        return {"installed": True, "logged_in": bool(json.loads(r.stdout).get("loggedIn")), "path": exe}
    except Exception:
        return {"installed": True, "logged_in": None, "path": exe}


def _kill_tree(proc):
    try:
        if sys.platform == "win32":  # claude.CMD -> node: mata a árvore inteira
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, creationflags=NOWIN)
        else:
            proc.kill()
    except Exception:
        pass


def kill(gid):
    with _plock:
        procs = list(PROCS.get(gid, ()))
    for p in procs:
        _kill_tree(p)


def call_claude(prompt, system_file, model, effort=None, schema=None, tools="", web=False, timeout=900):
    SANDBOX.mkdir(parents=True, exist_ok=True)
    exe = find_claude()
    if not exe:
        raise AgentError("CLI do Claude Code não encontrado. Na tela inicial, use \"Configuração\" para instalar e entrar na sua conta, "
                         "ou configure um provedor de API.")
    cmd = [exe, "-p", "--output-format", "json", "--no-session-persistence", "--strict-mcp-config",
           "--setting-sources", "local", "--system-prompt-file", str(system_file), "--model", model,
           "--tools", tools]
    if effort:
        cmd += ["--effort", effort]
    if web:
        cmd += ["--dangerously-skip-permissions"]
    if schema:
        cmd += ["--json-schema", json.dumps(schema)]
    gid = getattr(_ctx, "gid", None)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", cwd=SANDBOX, creationflags=NOWIN)
    if gid:
        with _plock:
            PROCS.setdefault(gid, set()).add(proc)
    try:
        stdout, stderr = proc.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        raise AgentError("timeout ao chamar o claude")
    finally:
        if gid:
            with _plock:
                PROCS.get(gid, set()).discard(proc)
    try:
        data = json.loads(stdout)
    except Exception:
        raise AgentError(f"saída inválida do claude (rc={proc.returncode}): {(stderr or stdout)[:400]}")
    if data.get("is_error"):
        raise AgentError(f"erro do claude: {str(data.get('result'))[:400]}")
    u = data.get("usage", {})
    tokens = (u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
              + u.get("cache_read_input_tokens", 0) + u.get("output_tokens", 0))
    out = data.get("structured_output")
    if schema and out is None:
        try:
            out = json.loads(data.get("result", ""))
        except Exception:
            raise AgentError("resposta sem JSON estruturado")
    return {
        "structured": out, "text": data.get("result", ""),
        "usage": {"tokens": tokens, "output_tokens": u.get("output_tokens", 0),
                  "cached": u.get("cache_read_input_tokens", 0),
                  "cost": data.get("total_cost_usd", 0.0), "ms": data.get("duration_ms", 0)},
    }


def _extract_json(text):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except Exception:
        a, b = t.find("{"), t.rfind("}")
        if a >= 0 and b > a:
            return json.loads(t[a:b + 1])
        raise


def call_llm(prompt, system_file, model, effort=None, schema=None, tools="", web=False, timeout=900):
    """CLI do claude (modelo simples) ou API compatível com OpenAI (modelo 'api:<id>/<nome>')."""
    pm = providers.parse_model(model)
    if pm is None:
        return call_claude(prompt, system_file, model, effort=effort, schema=schema, tools=tools, web=web, timeout=timeout)
    prov, name = pm
    system = Path(system_file).read_text(encoding="utf-8")
    user = prompt
    if schema:
        user += ("\n\nResponda APENAS com um objeto JSON válido (sem texto fora do JSON) seguindo este JSON Schema:\n"
                 + json.dumps(schema, ensure_ascii=False))
    try:
        text, usage = providers.chat(prov, name, system, user, json_mode=bool(schema), timeout=timeout)
    except (RuntimeError, ValueError) as e:
        raise AgentError(str(e))
    out = None
    if schema:
        try:
            out = _extract_json(text)
        except Exception:
            raise AgentError("a API não devolveu JSON válido")
    return {"structured": out, "text": text, "usage": usage}


def _add_usage(total, u):
    for k in ("tokens", "cost", "calls"):
        total[k] = total.get(k, 0) + (u.get(k, 0) if k != "calls" else 1)


def rebuild(game):
    board = chess.Board()
    for m in game["moves"]:
        board.push_uci(m["uci"])
    return board


def resolve_move(board, text):
    """Texto -> chess.Move legal, ou None."""
    t = re.sub(r"^\d+\.(\.\.)?\s*", "", (text or "").strip())
    t = t.replace("0-0-0", "O-O-O").replace("0-0", "O-O").rstrip("!?+# ").strip()
    for fn in (board.parse_san, board.parse_uci):
        try:
            m = fn(t)
            if m in board.legal_moves:
                return m
        except Exception:
            pass
    return None


def make_briefing(color, mode, model):
    if mode == "off":
        return "", {}
    prompt = f"Você jogará de {'Brancas' if color == chess.WHITE else 'Pretas'}. Escreva o briefing."
    web = mode == "web" and not model.startswith("api:")  # busca web só pelo CLI do Claude
    r = call_llm(prompt, PROMPTS / "briefing.md", model, effort="low", tools="WebSearch" if web else "", web=web)
    return r["text"].strip(), r["usage"]


def _eff_settings(game):
    s = game["settings"]
    over = s.get("budget_usd", 0) and game["usage"].get("cost", 0) > s["budget_usd"]
    return ("low" if over else s["effort"]), ("off" if over else s["reviewer"]), bool(over)


AIDS_NOTE = {
    "full": "Ajudas ativas: sondagem do motor raso COM avaliação posicional (dica fraca, ranqueada).",
    "material": "Ajudas ativas: apenas previsão de MATERIAL em capturas/xeques, sem ranking nem avaliação posicional. "
                "A escolha estratégica é inteiramente sua.",
    "none": "Ajudas ativas: nenhuma sondagem de motor. A escolha é inteiramente sua.",
}


def build_prompt(game, board, probes_text, probes_title, legal_san, me, use_facts=True):
    assist = game["settings"].get("assist", "full")
    last = game["moves"][-1]["san"] if game["moves"] else None
    hist = facts.san_history([m["san"] for m in game["moves"]])
    mem = game.get("plan_notes") or "(nenhuma ainda — primeiro lance)"
    recent = [f"{(m['ply'] + 1) // 2}{'.' if m['ply'] % 2 else '...'}{m['san']}: {m['thought']['summary']}"
              for m in game["moves"] if m.get("thought")][-5:]
    parts = [
        f"# Você joga de {facts.NAME[me]}. Lance nº {board.fullmove_number}. Vez: {facts.NAME[board.turn]}.",
        "## Tabuleiro\n" + facts.board_ascii(board) + f"\nFEN: {board.fen()}",
        "## Lances da partida\n" + (hist or "(início)"),
        f"Último lance do adversário: {last}" if last and game["moves"][-1]["by"] == "human" else "",
        ("## Fatos objetivos (calculados por código)\n" + facts.position_report(board, me)) if use_facts
        else "Fatos objetivos desligados: leia a posição só pelo diagrama.",
        (f"## {probes_title}\n" + probes_text) if probes_text else "",
        AIDS_NOTE.get(assist, ""),
        "## Lances legais (escolha exatamente um)\n" + ", ".join(legal_san),
        "## Sua memória\nPlano anotado: " + mem
        + ("\nResumos recentes seus:\n" + "\n".join(recent) if recent else ""),
    ]
    if game.get("briefing"):
        parts.append("## Seu briefing inicial\n" + game["briefing"])
    parts.append("Pense nas camadas e responda no schema.")
    return "\n\n".join(p for p in parts if p)


def should_review(mode, chosen_probe, chosen_cp, best_cp, out, cooldown=False):
    """Gatilhos baratos (locais) para chamar o revisor Haiku. Silencioso por padrão:
    só dispara com sinal forte, nunca em posição decidida e não em lances seguidos."""
    if mode == "off":
        return None
    if mode == "always":
        return "sempre"
    if chosen_probe["mate_risk"]:
        return "permite xeque-mate"
    if cooldown or abs(best_cp) >= 600:
        return None
    gap = best_cp - chosen_cp if chosen_cp is not None else 0
    conf = out.get("confidence", 5)
    if gap >= 200:
        return f"motor raso vê perda de {gap / 100:.1f}p vs melhor"
    if chosen_probe["risky"] and (gap >= 50 or conf <= 2):
        return "peça valiosa fica em risco: " + ", ".join(chosen_probe["new_risk"])
    if conf <= 2 and gap >= 80:
        return "confiança baixa e motor discorda"
    return None


def review_move(board, me, san, probe_info, out, model="haiku"):
    """Revisor: Haiku via CLI; se o jogador usa uma API, o mesmo modelo da API revisa."""
    prompt = "\n\n".join([
        facts.board_ascii(board) + f"\nFEN: {board.fen()}",
        "Fatos:\n" + facts.position_report(board, me),
        f"Lance pretendido por {facts.NAME[me]}: {san}",
        "Sondagem do lance: " + (json.dumps(probe_info, ensure_ascii=False) if probe_info else "(não sondado)"),
        "Checagem do próprio jogador: " + out.get("blunder_check", ""),
    ])
    r = call_llm(prompt, PROMPTS / "reviewer.md", model, schema=REVIEW_SCHEMA)
    return r["structured"], r["usage"]


def reference(board, analysis, move, assist, positional):
    """(melhor, escolhido) segundo o motor raso. Local, sem custo de token."""
    pool = list(analysis) if assist == "full" else []
    if not any(a["move"] == move for a in pool):
        extra = engine.analyze(board, depth=3, top_k=0 if pool else 1, extra=[move], positional=positional)
        pool = list({a["uci"]: a for a in pool + extra}.values())
        pool.sort(key=lambda a: -a["score_cp"])
    return pool[0], next(a for a in pool if a["move"] == move)


def agent_move(game):
    """Escolhe o lance do agente para a posição atual. Devolve dict com lance + registro."""
    board = rebuild(game)
    me = board.turn
    s = game["settings"]
    effort, rev_mode, economy = _eff_settings(game)
    usage = {}

    assist = s.get("assist", "full")
    use_facts = s.get("facts", True)
    forcing = [m for m in board.legal_moves if board.is_capture(m) or board.gives_check(m) or m.promotion]
    base_cp = engine.material_cp(board) * (1 if me == chess.WHITE else -1)
    if assist == "full":
        analysis = engine.analyze(board, depth=3, top_k=5, extra=forcing[:8])
        probes_full = [facts.probe(board, c) for c in analysis]
        probes_text = facts.format_probes(probes_full)
        probes_title = "Sondagem do motor raso (dica fraca, lances candidatos)"
    elif assist == "material":
        # só material clássico, só lances forçantes, ordem neutra (sem ranking)
        analysis = engine.analyze(board, depth=3, top_k=0, extra=forcing[:12], positional=False)
        probes_full = [facts.probe(board, c) for c in analysis]
        probes_text = facts.format_probes_material(probes_full, base_cp)
        probes_title = "Previsão de material em capturas e xeques (sem avaliação posicional)"
    else:
        analysis, probes_full, probes_text, probes_title = [], [], "", ""
    legal_san = sorted(board.san(m) for m in board.legal_moves)
    prompt = build_prompt(game, board, probes_text, probes_title, legal_san, me, use_facts)
    # referência SÓ para auditoria/revisor (nunca vai ao jogador fora do modo 'full')
    ref_positional = assist == "full"

    attempts, move, out = 0, None, None
    extra_msg = ""
    while attempts < 3 and move is None:
        attempts += 1
        r = call_llm(prompt + extra_msg, PROMPTS / "player.md", s["model"], effort=effort, schema=PLAYER_SCHEMA)
        _add_usage(usage, r["usage"])
        out = r["structured"]
        move = resolve_move(board, out.get("move"))
        if move is None:
            extra_msg = (f"\n\nATENÇÃO: seu lance '{out.get('move')}' é ILEGAL nesta posição. "
                         f"Escolha exatamente um destes: {', '.join(legal_san)}. Reverifique o diagrama.")
    fallback = False
    if move is None:
        move, fallback = (analysis or engine.analyze(board, depth=3, top_k=1, positional=ref_positional))[0]["move"], True
        out = out or {}
        out.setdefault("summary", "(lance do motor raso: o modelo não produziu lance legal)")
        out["move"] = board.san(move)

    san = board.san(move)
    # o modelo avalia do PRÓPRIO ponto de vista (menos confuso); guardamos sempre do ponto de vista das brancas
    try:
        own = float(out.get("eval_pawns", 0))
    except (TypeError, ValueError):
        own = 0.0
    out["eval_own"] = own
    out["eval_pawns"] = round(own if me == chess.WHITE else -own, 2)
    best, chosen_eng = reference(board, analysis, move, assist, ref_positional)
    probe_info = facts.probe(board, chosen_eng)
    review = None
    recently = any((m.get("meta") or {}).get("review") for m in game["moves"][-4:])  # intervalo entre revisões
    why = None if fallback else should_review(rev_mode, probe_info, chosen_eng["score_cp"],
                                              best["score_cp"], out, cooldown=recently)
    if why:
        try:
            rv, ru = review_move(board, me, san, probe_info, out,
                                 model=s['model'] if s['model'].startswith('api:') else 'haiku')
            _add_usage(usage, ru)
            review = {"reason": why, "verdict": rv["verdict"], "problem": rv["problem"], "revised": False}
            if rv["verdict"] == "problem":
                msg = (f"\n\nREVISOR (Haiku, rápido) apontou um possível problema no seu lance {san}: {rv['problem']}\n"
                       "Reavalie com cuidado. Pode manter o lance se estiver certo (explique em decision) ou trocar. "
                       "Responda no schema completo de novo.")
                r2 = call_llm(prompt + msg, PROMPTS / "player.md", s["model"], effort=effort, schema=PLAYER_SCHEMA)
                _add_usage(usage, r2["usage"])
                m2 = resolve_move(board, r2["structured"].get("move"))
                if m2 is not None:
                    review["revised"] = (m2 != move)
                    move, out = m2, r2["structured"]
                    try:
                        own = float(out.get("eval_pawns", 0))
                    except (TypeError, ValueError):
                        own = 0.0
                    out["eval_own"] = own
                    out["eval_pawns"] = round(own if me == chess.WHITE else -own, 2)
                    san = board.san(move)
                    best, chosen_eng = reference(board, analysis, move, assist, ref_positional)
        except AgentError as e:
            review = {"reason": why, "verdict": "erro", "problem": str(e), "revised": False}

    meta = {
        "usage": usage, "attempts": attempts, "fallback": fallback, "review": review, "economy": economy,
        "effort": effort, "assist": assist, "facts": use_facts,
        "engine": {
            # referência de auditoria: no modo 'full' é o que o jogador viu; nos outros, só material e NÃO foi mostrado
            "best": best["san"], "best_ev": best["score_cp"] / 100,
            "chosen_ev": chosen_eng["score_cp"] / 100,
            "agrees": best["move"] == move, "positional": ref_positional, "shown": assist != "none",
            "probes": [{"san": p["san"], "ev": p["ev"], "pv": p["pv"], "flags": p["flags"]} for p in probes_full],
        },
    }
    return {"move": move, "san": san, "thought": out, "meta": meta, "usage": usage}


def ask_about(game, ply, question, model):
    """Pergunta pós-jogo sobre um lance (ply 1-based; 0 = posição inicial)."""
    b = chess.Board()
    for m in game["moves"][:ply]:
        b.push_uci(m["uci"])
    rec = game["moves"][ply - 1] if ply > 0 else None
    hist = facts.san_history([m["san"] for m in game["moves"][:ply]])
    parts = [
        "## Posição no momento\n" + facts.board_ascii(b) + f"\nFEN: {b.fen()}",
        "## Lances até aqui\n" + (hist or "(início)"),
    ]
    if rec:
        who = "o aluno (humano)" if rec["by"] == "human" else "você (o agente)"
        parts.append(f"## Lance nº {ply}: {rec['san']} (jogado por {who})")
        if rec.get("thought"):
            t = rec["thought"]
            parts.append("## Seu raciocínio registrado na época\n" + json.dumps(
                {k: t.get(k) for k in ("position_read", "opponent_threats", "plan", "candidates", "decision",
                                       "blunder_check", "eval_pawns", "confidence")}, ensure_ascii=False))
    prior = [c for c in game.get("comments", []) if c["ply"] == ply][-4:]
    if prior:
        parts.append("## Conversa anterior sobre este lance\n" + "\n".join(
            f"Aluno: {c['question']}\nVocê: {c['answer']}" for c in prior))
    parts.append("## Pergunta do aluno\n" + question)
    r = call_llm("\n\n".join(parts), PROMPTS / "professor.md", model, effort="low")
    return r["text"].strip(), r["usage"]
