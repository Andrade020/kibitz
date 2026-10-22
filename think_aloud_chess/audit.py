"""Auditoria local pós-jogo: reavalia TODOS os lances (humano e agente) com o mesmo motor raso.

Sem tokens. Mede perda de avaliação por lance, precisão e erros. NÃO estima rating absoluto: a régua rasa não enxerga
os erros que existem (perda média sai artificialmente baixa) e a conversão perda->Elo exige motor forte.
Limitação importante: a régua é um motor de 3 lances; ela erra em táticas profundas e sacrifícios, então
os números valem mais para COMPARAR os dois lados (mesma régua) do que como rating absoluto.
"""
import math

import chess

from . import engine

CAP = 1000          # limita avaliações (mates etc.) a +-10 peões
OPENING_SKIP = 6    # ignora os primeiros plies (teoria/abertura) nas médias
DECIDED = 800       # ignora posições já decididas (> 8 peões) nas médias


def _win(cp):
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * max(-CAP, min(CAP, cp)))) - 1)


def classify(loss):
    if loss >= 200:
        return "blunder"
    if loss >= 100:
        return "mistake"
    if loss >= 50:
        return "inaccuracy"
    return "ok"


def audit_game(moves, progress=None):
    """moves: lista de dicts com 'uci'. Retorna lista (um item por ply) com a análise do lance jogado."""
    b = chess.Board()
    out = []
    for i, m in enumerate(moves):
        mv = chess.Move.from_uci(m["uci"])
        a = engine.analyze(b, depth=3, top_k=1, extra=[mv], positional=True)
        best = a[0]
        played = next(x for x in a if x["move"] == mv)
        bcp = max(-CAP, min(CAP, best["score_cp"]))
        pcp = max(-CAP, min(CAP, played["score_cp"]))
        loss = max(0, bcp - pcp)
        sign = 1 if b.turn == chess.WHITE else -1
        out.append({
            "ply": i + 1, "best": best["san"], "best_cp": bcp, "played_cp": pcp, "loss": loss,
            "cls": classify(loss), "top1": best["move"] == mv,
            "eval_white": sign * pcp, "win_loss": max(0.0, _win(bcp) - _win(pcp)),
        })
        b.push(mv)
        if progress:
            progress(i + 1, len(moves))
    return out


def summarize(audit, moves, human_color):
    """Estatísticas por lado ('human' / 'agent')."""
    res = {}
    for side in ("human", "agent"):
        mine = [(a, m) for a, m in zip(audit, moves) if m["by"] == side]
        counted = [a for a, _ in mine if a["ply"] > OPENING_SKIP and abs(a["best_cp"]) <= DECIDED]
        n = len(counted)
        if not n:
            res[side] = {"n": 0}
            continue
        acpl = sum(min(a["loss"], 300) for a in counted) / n
        acc = sum(max(0.0, min(100.0, 103.1668 * math.exp(-0.04354 * a["win_loss"]) - 3.1669)) for a in counted) / n
        res[side] = {
            "n": n, "moves": len(mine), "acpl": round(acpl, 1), "accuracy": round(acc, 1),
            "inaccuracies": sum(a["cls"] == "inaccuracy" for a in counted),
            "mistakes": sum(a["cls"] == "mistake" for a in counted),
            "blunders": sum(a["cls"] == "blunder" for a in counted),
            "top1": round(100 * sum(a["top1"] for a in counted) / n),
        }
    return res
