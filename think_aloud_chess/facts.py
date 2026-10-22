"""Fatos objetivos sobre a posição, em texto compacto, para o LLM não precisar
"enxergar" o tabuleiro de cabeça (onde ele mais erra)."""
import chess
from chess import PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING, WHITE, BLACK

PTS = {PAWN: 1, KNIGHT: 3, BISHOP: 3, ROOK: 5, QUEEN: 9, KING: 0}
PVAL = {PAWN: 100, KNIGHT: 320, BISHOP: 330, ROOK: 500, QUEEN: 900, KING: 20000}
NAME = {WHITE: "Brancas", BLACK: "Pretas"}


def tag(piece, sq):
    return f"{piece.symbol().upper()}{chess.square_name(sq)}"


def board_ascii(board):
    rows = ["  a b c d e f g h"]
    for r in range(7, -1, -1):
        cells = []
        for f in range(8):
            p = board.piece_at(chess.square(f, r))
            cells.append(p.symbol() if p else ".")
        rows.append(f"{r + 1} {' '.join(cells)} {r + 1}")
    rows.append("  a b c d e f g h")
    return "\n".join(rows)


def san_history(board_start_fen_moves):
    """Recebe lista de SAN -> '1. e4 e5 2. Nf3 ...'"""
    out = []
    for i, san in enumerate(board_start_fen_moves):
        if i % 2 == 0:
            out.append(f"{i // 2 + 1}.")
        out.append(san)
    return " ".join(out)


def material(board):
    res = {}
    for c in (WHITE, BLACK):
        pts = sum(PTS[p.piece_type] for p in board.piece_map().values() if p.color == c)
        bishops = len(board.pieces(BISHOP, c))
        res[c] = (pts, bishops >= 2)
    return res


def en_prise(board, color):
    """Peças de `color` atacadas e (sem defesa OU atacadas por peça de menor valor)."""
    out = []
    for sq, p in board.piece_map().items():
        if p.color != color or p.piece_type == KING:
            continue
        att = board.attackers(not color, sq)
        if not att:
            continue
        dfn = board.attackers(color, sq)
        low_sq = min(att, key=lambda a: PVAL[board.piece_type_at(a)])
        low = PVAL[board.piece_type_at(low_sq)]
        if not dfn or low < PVAL[p.piece_type]:
            why = "sem defesa" if not dfn else "atacada por peça de menor valor"
            out.append((sq, p, tag(board.piece_at(low_sq), low_sq), why))
    return out


def pass_threats(board):
    """O que o adversário ameaça se eu 'passasse' a vez."""
    if board.is_check():
        return ["(você está em xeque)"]
    b = board.copy(stack=False)
    b.push(chess.Move.null())
    me = not b.turn
    res = []
    for m in list(b.legal_moves):
        b.push(m)
        mate = b.is_checkmate()
        b.pop()
        if mate:
            res.append(f"{b.san(m)} = XEQUE-MATE")
    for m in b.legal_moves:
        if not b.is_capture(m):
            continue
        victim = b.piece_at(m.to_square)
        vv = PVAL[victim.piece_type] if victim else 100
        att = PVAL[b.piece_type_at(m.from_square)]
        defended = bool(b.attackers(me, m.to_square))
        gain = vv - (att if defended else 0)
        if gain > 50:
            res.append(f"{b.san(m)} (ganha ~{gain / 100:.1f}p)")
    return res


def king_info(board, color):
    ks = board.king(color)
    f, r = chess.square_file(ks), chess.square_rank(ks)
    rel = r if color == WHITE else 7 - r
    step = 1 if color == WHITE else -1
    pawns = board.pieces(PAWN, color)
    shield = 0
    open_files = []
    for ff in range(max(0, f - 1), min(7, f + 1) + 1):
        own = [s for s in pawns if chess.square_file(s) == ff]
        if not own:
            open_files.append("abcdefgh"[ff])
        for rr in (r + step, r + 2 * step):
            if 0 <= rr <= 7 and chess.square(ff, rr) in pawns:
                shield += 1
                break
    zone = chess.SquareSet(chess.BB_KING_ATTACKS[ks]) | chess.SquareSet.from_square(ks)
    pressure = sum(len(board.attackers(not color, s)) for s in zone)
    if rel == 0 and f in (1, 2, 6, 7):
        castle = "rocado"
    elif board.has_castling_rights(color):
        castle = "ainda pode rocar"
    else:
        castle = "sem direito de roque"
    s = f"rei {chess.square_name(ks)} ({castle}), escudo de peões {shield}/3"
    if open_files:
        s += f", colunas sem peão próprio perto do rei: {','.join(open_files)}"
    s += f", pressão inimiga na zona do rei: {pressure}"
    return s


def pawn_notes(board, color):
    pawns = list(board.pieces(PAWN, color))
    enemy = list(board.pieces(PAWN, not color))
    files = [chess.square_file(s) for s in pawns]
    doubled = sorted({"abcdefgh"[f] for f in files if files.count(f) > 1})
    isolated, passed = [], []
    for s in pawns:
        f, r = chess.square_file(s), chess.square_rank(s)
        if not any(abs(chess.square_file(o) - f) == 1 for o in pawns):
            isolated.append(chess.square_name(s))
        ahead = (lambda rr: rr > r) if color == WHITE else (lambda rr: rr < r)
        if not any(abs(chess.square_file(e) - f) <= 1 and ahead(chess.square_rank(e)) for e in enemy):
            passed.append(chess.square_name(s))
    parts = []
    if doubled:
        parts.append("dobrados em " + ",".join(doubled))
    if isolated:
        parts.append("isolados " + ",".join(isolated))
    if passed:
        parts.append("PASSADOS " + ",".join(passed))
    return "; ".join(parts) or "estrutura normal"


def files_report(board):
    wp = {chess.square_file(s) for s in board.pieces(PAWN, WHITE)}
    bp = {chess.square_file(s) for s in board.pieces(PAWN, BLACK)}
    opens = ["abcdefgh"[f] for f in range(8) if f not in wp and f not in bp]
    out = []
    if opens:
        out.append("colunas abertas: " + ",".join(opens))
    for c in (WHITE, BLACK):
        mine = wp if c == WHITE else bp
        theirs = bp if c == WHITE else wp
        semi = ["abcdefgh"[f] for f in range(8) if f not in mine and f in theirs]
        if semi:
            out.append(f"semiabertas para {NAME[c]}: " + ",".join(semi))
        seventh = [tag(board.piece_at(s), s) for s in board.pieces(ROOK, c)
                   if (chess.square_rank(s) if c == WHITE else 7 - chess.square_rank(s)) == 6]
        if seventh:
            out.append(f"torre(s) na 7ª de {NAME[c]}: " + ",".join(seventh))
    return "; ".join(out) or "sem colunas abertas"


HOME = {WHITE: {chess.B1: KNIGHT, chess.G1: KNIGHT, chess.C1: BISHOP, chess.F1: BISHOP},
        BLACK: {chess.B8: KNIGHT, chess.G8: KNIGHT, chess.C8: BISHOP, chess.F8: BISHOP}}


def undeveloped(board, color):
    out = []
    for sq, t in HOME[color].items():
        p = board.piece_at(sq)
        if p and p.color == color and p.piece_type == t:
            out.append(tag(p, sq))
    return out


def position_report(board, me):
    """Relatório factual. `me` = cor do agente."""
    opp = not me
    m = material(board)
    lines = []
    diff = m[me][0] - m[opp][0]
    lines.append(
        f"Material (P=1,C/B=3,T=5,D=9): Brancas {m[WHITE][0]}{' +par de bispos' if m[WHITE][1] else ''} | "
        f"Pretas {m[BLACK][0]}{' +par de bispos' if m[BLACK][1] else ''} | "
        f"saldo para você: {diff:+d}")
    for c, label in ((me, "SEU"), (opp, "ADVERSÁRIO")):
        lines.append(f"{label} {king_info(board, c)}")
    for c in (WHITE, BLACK):
        lines.append(f"Peões {NAME[c]}: {pawn_notes(board, c)}")
    lines.append("Colunas: " + files_report(board))
    mine = en_prise(board, me)
    theirs = en_prise(board, opp)
    lines.append("Suas peças em risco: " + (", ".join(f"{tag(p, s)} ({a}, {w})" for s, p, a, w in mine) or "nenhuma"))
    lines.append("Peças adversárias em risco (você pode capturar): " +
                 (", ".join(f"{tag(p, s)} ({a}, {w})" for s, p, a, w in theirs) or "nenhuma"))
    thr = pass_threats(board)
    lines.append("Ameaças do adversário se você passasse a vez: " + ("; ".join(thr) or "nenhuma imediata"))
    if board.fullmove_number <= 20:
        ud_me, ud_op = undeveloped(board, me), undeveloped(board, opp)
        lines.append(f"Menores não desenvolvidas — suas: {', '.join(ud_me) or 'nenhuma'}; do adversário: {', '.join(ud_op) or 'nenhuma'}")
    extra = []
    if board.is_check():
        extra.append("VOCÊ ESTÁ EM XEQUE")
    if board.is_repetition(2):
        extra.append("esta posição já ocorreu 2x (3ª = empate)")
    if board.halfmove_clock >= 30:
        extra.append(f"{board.halfmove_clock} meios-lances sem captura/peão (regra dos 50)")
    if extra:
        lines.append("Alertas: " + "; ".join(extra))
    return "\n".join(lines)


def probe(board, cand):
    """Sondagem de consequências de um lance candidato (dict vindo de engine.analyze)."""
    me = board.turn
    b = board.copy(stack=False)
    m = cand["move"]
    b.push(m)
    flags = []
    if b.is_checkmate():
        flags.append("DÁ XEQUE-MATE")
    elif b.is_check():
        flags.append("xeque")
    if board.is_capture(m):
        flags.append("captura")
    risk = en_prise(b, me)
    if risk and not b.is_checkmate():
        flags.append("deixa em risco: " + ", ".join(f"{tag(p, s)} (por {a})" for s, p, a, _ in risk))
    # risco NOVO e relevante (para o revisor): peça valiosa que não estava em risco antes do lance,
    # descontando troca em que a captura já pagou o valor da própria peça
    before = {s for s, _, _, _ in en_prise(board, me)}
    gained = 0
    if board.is_capture(m):
        victim = board.piece_at(m.to_square)
        gained = PVAL[victim.piece_type] if victim else PVAL[PAWN]
    new_risk = []
    for s, p, a, _ in risk:
        if s in before or PVAL[p.piece_type] < 300:
            continue
        if s == m.to_square and gained >= PVAL[p.piece_type]:
            continue
        new_risk.append(tag(p, s))
    mate_risk = False
    if not b.is_checkmate():
        for om in list(b.legal_moves):
            b.push(om)
            mate = b.is_checkmate()
            b.pop()
            if mate:
                flags.append(f"PERMITE MATE ({b.san(om)})")
                mate_risk = True
                break
    if b.is_repetition(2):
        flags.append("repete posição")
    cp, mate = cand["score_cp"], cand["mate"]
    ev = f"#{mate}" if mate else f"{cp / 100:+.2f}"
    return {
        "san": cand["san"], "ev": ev, "cp": cp, "pv": " ".join(cand["pv"]), "flags": flags,
        "risky": bool(new_risk), "new_risk": new_risk, "mate_risk": mate_risk,
    }


def format_probes(probes):
    lines = []
    for p in probes:
        fl = f"  [{'; '.join(p['flags'])}]" if p["flags"] else ""
        lines.append(f"- {p['san']}: motor-raso {p['ev']} | linha: {p['pv']}{fl}")
    return "\n".join(lines)


def format_probes_material(probes, base_cp):
    """Modo 'só material': lances forçantes em ordem neutra (alfabética), sem ranking nem nota posicional."""
    lines = []
    for p in sorted(probes, key=lambda x: x["san"]):
        d = p["cp"] - base_cp
        fl = f"  [{'; '.join(p['flags'])}]" if p["flags"] else ""
        lines.append(f"- {p['san']}: saldo de material ao fim da linha forçada {d / 100:+.1f} | linha: {p['pv']}{fl}")
    return "\n".join(lines) or "(nenhuma captura ou xeque disponível)"
