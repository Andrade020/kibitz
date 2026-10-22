"""Revisão pós-jogo ("professor"): opt-in, usa tokens, fica salva na partida e sai em etapas.

Etapas (cada uma vira visível assim que termina):
  1. plan(): local, sem tokens. Motor forte (se houver) avalia a partida, escolhe os momentos críticos e calcula
     linhas/setas. Sem motor forte, cai na auditoria da régua rasa.
  2. explain_moment(): uma chamada curta por momento, em paralelo. O professor explica por conceitos usando a
     verdade do motor (inclusive quando o Claude errou a leitura durante o jogo).
  3. synthesize(): visão geral, fases, lições e o raciocínio do agente, escrita por último com os momentos prontos.
Tudo verificável (lances legais, casas, momentos) é validado depois, para não aceitar alucinações.
"""
import re
import time

import chess

from . import agent, audit, engine, facts, strong

MOMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"}, "explanation": {"type": "string"},
        "concepts": {"type": "array", "items": {"type": "string"}},
        "better": {"type": "string"}, "agent_check": {"type": "string"},
        "arrows": {"type": "array", "items": {"type": "object", "properties": {
            "from": {"type": "string"}, "to": {"type": "string"},
            "kind": {"type": "string", "enum": ["best", "threat", "plan", "mistake"]},
            "label": {"type": "string"}}, "required": ["from", "to", "kind", "label"]}},
        "squares": {"type": "array", "items": {"type": "object", "properties": {
            "sq": {"type": "string"}, "kind": {"type": "string", "enum": ["key", "weak", "target"]}},
            "required": ["sq", "kind"]}},
    },
    "required": ["title", "explanation", "concepts", "better", "agent_check", "arrows", "squares"],
}

SYNTH_SCHEMA = {
    "type": "object",
    "properties": {
        "overall": {"type": "string"}, "result_reason": {"type": "string"},
        "phases": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "plies": {"type": "string"}, "assessment": {"type": "string"},
            "concepts": {"type": "array", "items": {"type": "string"}}},
            "required": ["name", "plies", "assessment", "concepts"]}},
        "lessons": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "explanation": {"type": "string"}, "practice": {"type": "string"}},
            "required": ["title", "explanation", "practice"]}},
        "agent_insights": {"type": "string"},
    },
    "required": ["overall", "result_reason", "phases", "lessons", "agent_insights"],
}

SQ = re.compile(r"^[a-h][1-8]$")
DEPTHS = {"quick": 6, "full": 10}
KINDS = ("best", "threat", "plan", "mistake")


def _lbl(ply):
    return f"{(ply + 1) // 2}{'.' if ply % 2 else '...'}"


def _board_before(g, ply):
    b = chess.Board()
    for m in g["moves"][:ply - 1]:
        b.push_uci(m["uci"])
    return b


# ---------------------------------------------------------------- etapa 1: plano local

def select_by_series(series, moves, n):
    """Momentos pelo motor forte: maiores variações de avaliação do ponto de vista de quem jogou (erros e acertos)."""
    cp = series["cp"]
    cand = []
    for p in range(1, len(moves) + 1):
        sign = 1 if p % 2 else -1
        w = 1.25 if moves[p - 1]["by"] == "human" else 1.0
        cand.append((w * abs((cp[p] - cp[p - 1]) * sign), p))
    cand.sort(reverse=True)
    chosen = []
    for sc, p in cand:
        if len(chosen) >= n or (sc < 30 and len(chosen) >= 3):
            break
        if all(abs(p - c) >= 2 for c in chosen):
            chosen.append(p)
    return sorted(chosen)


def select_shallow(g, n):
    """Fallback sem motor forte: oscilações da auditoria rasa (peso menor na abertura, onde ela é ruidosa)."""
    A, moves = g["audit"], g["moves"]
    cand = []
    for i, (m, a) in enumerate(zip(moves, A)):
        before = A[i - 1]["eval_white"] if i else 0
        sc = (1.25 if m["by"] == "human" else 1.0) * (min(abs(a["eval_white"] - before), 1000) + 0.5 * a["loss"])
        cand.append((sc * (0.5 if i + 1 <= 10 else 1.0), i + 1))
    cand.sort(reverse=True)
    chosen = []
    for sc, p in cand:
        if len(chosen) >= n or (sc < 20 and len(chosen) >= 3):
            break
        if all(abs(p - c) >= 3 for c in chosen):
            chosen.append(p)
    return sorted(chosen)


def strong_stats(series, moves):
    """Estatísticas por lado com a avaliação do motor forte (reaproveita audit.summarize)."""
    cp, entries = series["cp"], []
    for p in range(1, len(moves) + 1):
        sign = 1 if p % 2 else -1
        before, after = cp[p - 1] * sign, cp[p] * sign
        loss = max(0, before - after)
        entries.append({"ply": p, "best_cp": before, "played_cp": after, "loss": loss, "cls": audit.classify(loss),
                        "top1": moves[p - 1]["uci"] == series["best"][p - 1], "eval_white": cp[p],
                        "win_loss": max(0.0, audit._win(before) - audit._win(after))})
    return audit.summarize(entries, moves, None)


def _arrows(uci, best_uci, loss):
    arr = [{"from": uci[:2], "to": uci[2:4], "kind": "played", "label": "jogado"}]
    if best_uci and best_uci[:4] != uci[:4] and loss >= 50:
        arr.append({"from": best_uci[:2], "to": best_uci[2:4], "kind": "best", "label": "motor"})
    return arr


def _skeleton(g, ply, b, ev_before, ev_after, loss, best_san, best_uci, pv, lines):
    m = g["moves"][ply - 1]
    return {
        "ply": ply, "label": _lbl(ply), "by": m["by"], "san": m["san"], "uci": m["uci"], "fen": b.fen(),
        "eval_before": ev_before, "eval_after": ev_after, "loss": loss, "best": best_san, "best_pv": pv,
        "lines": lines, "arrows": _arrows(m["uci"], best_uci, loss), "squares": [],
        "prev": " ".join(f"{_lbl(p)} {g['moves'][p - 1]['san']}" for p in range(max(1, ply - 4), ply)),
        "status": "pending", "title": "", "explanation": "", "concepts": [], "better": "", "agent_check": "",
    }


def plan(g, depth="full", progress=None):
    """Etapa local (sem tokens). Devolve {engine_kind, engine_name, curve, stats, moments, engine_error}."""
    n = DEPTHS.get(depth, DEPTHS["full"])
    err = None
    path = strong.find()
    if path:
        try:
            with strong.Session(path) as S:
                series = S.series(g["moves"], depth=14, progress=lambda d, t: progress and progress("engine", d, t))
                plies = select_by_series(series, g["moves"], n)
                moments = []
                for k, ply in enumerate(plies, 1):
                    b = _board_before(g, ply)
                    mv = chess.Move.from_uci(g["moves"][ply - 1]["uci"])
                    d = S.deep(b, mv)
                    sign = 1 if b.turn == chess.WHITE else -1
                    best = d["lines"][0]
                    loss = max(0, (best["cp"] - d["played_cp"]) * sign)
                    moments.append(_skeleton(g, ply, b, series["cp"][ply - 1] / 100, d["played_cp"] / 100, loss,
                                             best["san"], best["uci"], best["pv"], d["lines"]))
                    if progress:
                        progress("deep", k, len(plies))
                return {"engine_kind": "strong", "engine_name": S.name, "curve": [c / 100 for c in series["cp"]],
                        "stats": strong_stats(series, g["moves"]), "moments": moments, "engine_error": None}
        except Exception as e:  # noqa
            err = f"{type(e).__name__}: {str(e)[:120]}"
    if not g.get("audit"):
        raise agent.AgentError("sem motor forte e a auditoria local ainda não rodou")
    plies = select_shallow(g, n)
    moments = []
    for k, ply in enumerate(plies, 1):
        b = _board_before(g, ply)
        mv = chess.Move.from_uci(g["moves"][ply - 1]["uci"])
        a = g["audit"][ply - 1]
        an = engine.analyze(b, depth=3, top_k=1, extra=[mv], positional=True)
        before = g["audit"][ply - 2]["eval_white"] if ply > 1 else 0
        moments.append(_skeleton(g, ply, b, before / 100, a["eval_white"] / 100, a["loss"], an[0]["san"],
                                 an[0]["uci"], " ".join(an[0]["pv"]), []))
        if progress:
            progress("deep", k, len(plies))
    return {"engine_kind": "shallow", "engine_name": "régua rasa (3 lances)", "engine_error": err,
            "curve": [0.0] + [a["eval_white"] / 100 for a in g["audit"]],
            "stats": audit.summarize(g["audit"], g["moves"], g["human_color"]), "moments": moments}


# ---------------------------------------------------------------- etapa 2: um momento

def header(g):
    s = g["settings"]
    return (f"# Partida: aluno (humano) de {'Brancas' if g['human_color'] == 'white' else 'Pretas'} contra o agente "
            f"`{s['model']}` (ajuda do motor durante o jogo: {s.get('assist', 'full')}). Resultado: {g.get('result')} "
            f"({g.get('reason')}). {len(g['moves'])} meios-lances.\n## Lances\n"
            + facts.san_history([m["san"] for m in g["moves"]]))


def _engine_note(kind, name, mo):
    sign = lambda v: f"{v:+.1f}"  # noqa
    if kind == "strong":
        ls = "; ".join(f"{l['san']} ({sign(l['cp'] / 100)}): {l['pv']}" for l in mo["lines"])
        return (f"VERDADE DO MOTOR FORTE ({name}), avaliação das BRANCAS em peões: antes do lance {sign(mo['eval_before'])}, "
                f"depois do lance jogado {sign(mo['eval_after'])}. Melhores linhas na posição: {ls}. "
                f"O lance jogado custou {mo['loss']} centipeões a quem o jogou. Estes números são confiáveis: se o aluno ou o "
                f"agente pensaram diferente na época, explique onde a leitura deles falhou.")
    return (f"Régua rasa (3 lances, pouco confiável): avaliação das brancas {sign(mo['eval_before'])} → {sign(mo['eval_after'])}; "
            f"preferia {mo['best']} (linha {mo['best_pv']}); perda {mo['loss']}cp. Não vê táticas profundas: use só como pista.")


def moment_prompt(g, ctx, mo):
    who = "ALUNO" if mo["by"] == "human" else "AGENTE"
    b = chess.Board(mo["fen"])
    parts = [ctx["header"],
             f"## Momento a explicar: lance {mo['label']} {mo['san']} jogado pelo {who} (ply={mo['ply']})",
             "Posição ANTES do lance:\n" + facts.board_ascii(b) + f"\nFEN: {mo['fen']}",
             f"Lances imediatamente anteriores: {mo['prev'] or '(início)'}",
             _engine_note(ctx["engine_kind"], ctx["engine_name"], mo)]
    m = g["moves"][mo["ply"] - 1]
    t = m.get("thought")
    if t:
        parts.append(f"Raciocínio que o agente registrou na época: leitura: {str(t.get('position_read'))[:300]} | plano: "
                     f"{str(t.get('plan'))[:240]} | ameaças vistas: {str(t.get('opponent_threats'))[:220]} | decisão: "
                     f"{str(t.get('decision'))[:240]} | confiança {t.get('confidence')}/5")
    else:
        prev = next((x for x in reversed(g["moves"][:mo["ply"] - 1]) if x.get("thought")), None)
        if prev:
            parts.append(f"O agente planejava (antes do lance do aluno): {str(prev['thought'].get('plan'))[:280]}")
    parts.append("Explique ESTE momento no schema (agent_check: se foi lance do agente ou ele planejava algo, diga o que a "
                 "leitura dele acertou ou errou em relação à verdade da posição; vazio se não se aplica).")
    return "\n\n".join(parts)


def _clean_moment(g, out, mo):
    b = chess.Board(mo["fen"])
    better = (out.get("better") or "").strip()
    bm = agent.resolve_move(b, better) if better else None
    dropped = 1 if (better and bm is None) else 0
    arrows = list(mo["arrows"])  # jogado (+ melhor do motor)
    seen = {(a["from"], a["to"]) for a in arrows}
    for a in (out.get("arrows") or [])[:4]:
        f, t = str(a.get("from", "")).lower(), str(a.get("to", "")).lower()
        if SQ.match(f) and SQ.match(t) and f != t and (f, t) not in seen:
            seen.add((f, t))
            arrows.append({"from": f, "to": t, "kind": a.get("kind") if a.get("kind") in KINDS else "plan",
                           "label": str(a.get("label", ""))[:24]})
    if bm is not None and (bm.uci()[:2], bm.uci()[2:4]) not in seen:
        arrows.append({"from": bm.uci()[:2], "to": bm.uci()[2:4], "kind": "best", "label": "sugerido"})
    squares = [{"sq": str(s.get("sq", "")).lower(), "kind": s.get("kind") if s.get("kind") in ("key", "weak", "target") else "key"}
               for s in (out.get("squares") or [])[:4] if SQ.match(str(s.get("sq", "")).lower())]
    return {
        "status": "done", "title": str(out.get("title", ""))[:120], "explanation": out.get("explanation", ""),
        "concepts": [str(c) for c in (out.get("concepts") or [])][:5], "better": b.san(bm) if bm else "",
        "agent_check": out.get("agent_check", ""), "arrows": arrows, "squares": squares,
    }, dropped


def explain_moment(g, ctx, mo, model, effort):
    r = agent.call_llm(moment_prompt(g, ctx, mo), agent.PROMPTS / "teacher.md", model,
                       effort=effort if not model.startswith("api:") else None, schema=MOMENT_SCHEMA)
    out, dropped = _clean_moment(g, r["structured"] or {}, mo)
    return out, dropped, r["usage"]


# ---------------------------------------------------------------- etapa 3: síntese

def synth_prompt(g, ctx, rv):
    agent_lines = []
    for m in g["moves"]:
        t = m.get("thought")
        if m["by"] == "agent" and t and t.get("summary"):
            agent_lines.append(f"{_lbl(m['ply'])} {m['san']}: {t['summary'][:150]}")
    curve = " ".join(f"{i}:{c:+.1f}" for i, c in enumerate(rv["curve"]) if i and i % 4 == 0)
    parts = [ctx["header"],
             "## Raciocínio que o agente registrou na época (resumo por lance dele)\n" + ("\n".join(agent_lines) or "(não registrado)"),
             f"## Curva de avaliação ({ctx['engine_name']}; brancas, em peões; a cada 4 meios-lances)\n" + curve]
    for side, name in (("human", "Aluno"), ("agent", "Agente")):
        x = (rv.get("stats") or {}).get(side, {})
        if x.get("n"):
            parts.append(f"{name}: perda média {x['acpl']}cp, precisão {x['accuracy']}%, imprecisões/erros/blunders "
                         f"{x['inaccuracies']}/{x['mistakes']}/{x['blunders']}.")
    parts.append("## Momentos críticos já analisados")
    for mo in rv["moments"]:
        if mo["status"] == "done":
            parts.append(f"- {mo['label']} {mo['san']} ({'aluno' if mo['by'] == 'human' else 'agente'}; {mo['eval_before']:+.1f}→{mo['eval_after']:+.1f}): "
                         f"{mo['title']}. {mo['explanation'][:380]} [{', '.join(mo['concepts'])}]")
    parts.append("Escreva a SÍNTESE da revisão no schema: overall, result_reason, phases, lessons (3 a 5, com exercício) e agent_insights.")
    return "\n\n".join(parts)


def synthesize(g, ctx, rv, model, effort):
    r = agent.call_llm(synth_prompt(g, ctx, rv), agent.PROMPTS / "teacher.md", model,
                       effort=effort if not model.startswith("api:") else None, schema=SYNTH_SCHEMA)
    o = r["structured"] or {}
    return {"overall": o.get("overall", ""), "result_reason": o.get("result_reason", ""),
            "phases": o.get("phases", []), "lessons": o.get("lessons", []),
            "agent_insights": o.get("agent_insights", "")}, r["usage"]


def new_context(g, pl):
    return {"header": header(g), "engine_kind": pl["engine_kind"], "engine_name": pl["engine_name"]}


def skeleton_review(pl, model, effort, depth):
    return {
        "created": time.time(), "model": model, "effort": effort, "depth": depth, "status": "running",
        "stage": "moments", "engine_kind": pl["engine_kind"], "engine_name": pl["engine_name"],
        "engine_error": pl.get("engine_error"), "curve": pl["curve"], "stats": pl["stats"],
        "moments": pl["moments"], "overall": "", "result_reason": "", "phases": [], "lessons": [],
        "agent_insights": "", "dropped": 0, "usage": {"tokens": 0, "cost": 0.0, "calls": 0},
    }
