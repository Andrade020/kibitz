"""Autosave legível: um arquivo markdown por partida em saves/ (sobrescrito a cada lance, sem acumular).

Durante a partida só vão lances e metadados (o raciocínio do agente fica de fora, jogo justo).
Ao terminar, o arquivo inclui o raciocínio, a auditoria e as perguntas/respostas, para ser lido por
uma pessoa ou por uma sessão do Claude Code.
"""
import time
from pathlib import Path

import chess

from . import paths

SAVES = paths.SAVES


def file_for(g):
    day = time.strftime("%Y%m%d", time.localtime(g["created"]))
    return SAVES / f"{day}_{g['id']}.md"


def _movetext(moves, with_comment):
    out = []
    for i, m in enumerate(moves):
        if i % 2 == 0:
            out.append(f"{i // 2 + 1}.")
        out.append(m["san"])
        t = m.get("thought")
        if with_comment and t and t.get("summary"):
            out.append("{" + t["summary"].replace("{", "(").replace("}", ")") + "}")
    return " ".join(out)


def render(g, stats=None):
    over = g["status"] == "over"
    s = g["settings"]
    agent_color = "Pretas" if g["human_color"] == "white" else "Brancas"
    L = [f"# Partida {g['id']} — {time.strftime('%d/%m/%Y %H:%M', time.localtime(g['created']))}", ""]
    L.append(f"- Humano: {'Brancas' if g['human_color'] == 'white' else 'Pretas'} · Agente ({agent_color}): `{s['model']}`"
             f" · esforço {s['effort']} · ajuda do motor: {s.get('assist', 'full')} · fatos: {'on' if s.get('facts', True) else 'off'}"
             f" · revisor: {s['reviewer']}")
    u = g["usage"]
    L.append(f"- Estado: {'ENCERRADA ' + str(g.get('result')) + ' (' + str(g.get('reason')) + ')' if over else 'em andamento'}"
             f" · {len(g['moves'])} lances · {u.get('tokens', 0)} tokens · US${u.get('cost', 0):.2f}")
    L += ["", "## Lances (SAN)", "", _movetext(g["moves"], over), ""]
    b = chess.Board()
    for m in g["moves"]:
        b.push_uci(m["uci"])
    L += ["FEN atual: `" + b.fen() + "`", ""]
    if not over:
        L.append("_Raciocínio do agente omitido enquanto a partida está em andamento._")
        return "\n".join(L) + "\n"

    if stats:
        L += ["## Auditoria do motor (régua rasa de 3 lances: só compare os lados entre si; não é rating)", "",
              "| lado | lances | perda média (cp) | precisão | imprecisões | erros | blunders | = melhor do motor |",
              "|---|---|---|---|---|---|---|---|"]
        for side, name in (("human", "Humano"), ("agent", "Agente")):
            x = stats.get(side, {})
            if x.get("n"):
                L.append(f"| {name} | {x['n']} | {x['acpl']} | {x['accuracy']}% | {x['inaccuracies']} | {x['mistakes']} | "
                         f"{x['blunders']} | {x['top1']}% |")
        L.append("")
    if g.get("briefing"):
        L += ["## Briefing inicial do agente", "", g["briefing"], ""]
    L.append("## Raciocínio do agente, lance a lance")
    for m in g["moves"]:
        t = m.get("thought")
        if m["by"] != "agent" or not t:
            continue
        a = (g.get("audit") or [None] * 999)[m["ply"] - 1] if g.get("audit") else None
        tag = f" — auditoria: {a['cls']} (perda {a['loss']}cp, motor preferia {a['best']})" if a else ""
        L += ["", f"### {(m['ply'] + 1) // 2}{'.' if m['ply'] % 2 else '...'} {m['san']}{tag}",
              f"- nota (brancas): {t.get('eval_pawns')} · confiança {t.get('confidence')}/5",
              f"- leitura: {t.get('position_read', '')}", f"- ameaças: {t.get('opponent_threats', '')}",
              f"- plano: {t.get('plan', '')}"]
        for c in t.get("candidates", []):
            L.append(f"- candidato {c.get('move')}: {c.get('idea')} | risco: {c.get('risk')} | linha: {c.get('line')}")
        L += [f"- decisão: {t.get('decision', '')}", f"- checagem: {t.get('blunder_check', '')}"]
        rv = (m.get("meta") or {}).get("review")
        if rv:
            L.append(f"- revisor: {rv['reason']} → {rv['verdict']} {rv.get('problem', '')}")
    rv = g.get("review")
    if rv:
        L += ["", "## Revisão do professor", "", rv.get("overall", ""), "", "**Por que o resultado:** " + rv.get("result_reason", "")]
        for ph in rv.get("phases", []):
            L.append(f"- **{ph['name']}** ({ph['plies']}): {ph['assessment']} _[{', '.join(ph['concepts'])}]_")
        L += ["", "### Lições"]
        for ls in rv.get("lessons", []):
            L.append(f"- **{ls['title']}**: {ls['explanation']} _Exercício:_ {ls['practice']}")
        if rv.get("agent_insights"):
            L += ["", "### O raciocínio do agente", rv["agent_insights"]]
        L += ["", f"_Motor da revisão: {rv.get('engine_name')} ({'forte' if rv.get('engine_kind') == 'strong' else 'régua rasa'})._",
              "", "### Momentos críticos"]
        for mo in rv.get("moments", []):
            arrows = ", ".join(f"{a['from']}→{a['to']} ({a['kind']}{': ' + a['label'] if a['label'] else ''})" for a in mo["arrows"])
            ev = f"{mo['eval_before']:+.1f} → {mo['eval_after']:+.1f} (brancas), perda {mo['loss']}cp, motor preferia {mo['best']} ({mo.get('best_pv', '')})"
            L += ["", f"#### {mo['label']} {mo['san']} — {mo.get('title') or '(sem explicação)'}", f"- motor: {ev}"]
            if mo.get("status") == "done":
                L += [mo["explanation"], f"- conceitos: {', '.join(mo['concepts'])}" + (f" · melhor: {mo['better']}" if mo["better"] else "")]
                if mo.get("agent_check"):
                    L.append(f"- leitura do agente na época: {mo['agent_check']}")
            elif mo.get("status") == "error":
                L.append(f"- explicação indisponível: {mo.get('error', '')}")
            L.append(f"- setas: {arrows}")
    if g.get("comments"):
        L += ["", "## Perguntas e respostas"]
        for c in g["comments"]:
            L += ["", f"**Lance {c['ply']} — aluno:** {c['question']}", "", c["answer"]]
    return "\n".join(L) + "\n"


def write(g, stats=None):
    SAVES.mkdir(exist_ok=True)
    p = file_for(g)
    p.write_text(render(g, stats), encoding="utf-8")
    return p
