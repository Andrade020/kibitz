"""Motor MUITO raso (material + tabelas simples, 2-3 plies + quiescence).

Serve só como "ponto de partida" para o LLM não se perder em becos sem saída.
Não é um motor de verdade: sem tabela de transposição, sem aberturas, sem finais.
"""
import chess
from chess import PAWN, KNIGHT, BISHOP, ROOK, QUEEN, KING, WHITE, BLACK

INF = 10**6
MATE = 100000
VAL = {PAWN: 100, KNIGHT: 320, BISHOP: 330, ROOK: 500, QUEEN: 900, KING: 0}


def material_cp(board):
    """Material puro em centipeões, ponto de vista das brancas."""
    s = 0
    for p in board.piece_map().values():
        s += VAL[p.piece_type] * (1 if p.color == WHITE else -1)
    return s


def _d(sq):
    return max(abs(chess.square_file(sq) - 3.5), abs(chess.square_rank(sq) - 3.5))


def _pst(piece, sq, endgame):
    t = piece.piece_type
    rel = chess.square_rank(sq) if piece.color == WHITE else 7 - chess.square_rank(sq)
    f = chess.square_file(sq)
    if t == KNIGHT:
        return int(10 * (3.5 - _d(sq)))
    if t == BISHOP:
        return int(5 * (3.5 - _d(sq)))
    if t == PAWN:
        return rel * 6 + int(3 * (3.5 - abs(f - 3.5))) if rel < 7 else 0
    if t == ROOK:
        return 20 if rel == 6 else 0
    if t == KING:
        if endgame:
            return int(8 * (3.5 - _d(sq)))
        return 15 if rel == 0 and f in (1, 2, 6, 7) else -10 * rel
    return 0


def evaluate(board, positional=True):
    """Avaliação do ponto de vista de quem joga. positional=False -> só material clássico."""
    if not positional:
        s = material_cp(board)
        return s if board.turn == WHITE else -s
    score = 0
    npm = 0
    for p in board.piece_map().values():
        if p.piece_type not in (PAWN, KING):
            npm += VAL[p.piece_type]
    endgame = npm < 2600
    for sq, p in board.piece_map().items():
        v = VAL[p.piece_type] + _pst(p, sq, endgame)
        score += v if p.color == WHITE else -v
    return score if board.turn == WHITE else -score


class Searcher:
    def __init__(self, node_limit=60000, positional=True):
        self.positional = positional
        self.nodes = 0
        self.node_limit = node_limit

    def _order(self, board, moves):
        def key(m):
            k = 0
            if board.is_capture(m):
                victim = board.piece_at(m.to_square)
                vv = VAL[victim.piece_type] if victim else 100
                k += 10 * vv - VAL[board.piece_type_at(m.from_square)]
            if m.promotion:
                k += 800
            return -k
        return sorted(moves, key=key)

    def qs(self, board, alpha, beta, qd):
        self.nodes += 1
        stand = evaluate(board, self.positional)
        if stand >= beta:
            return stand
        alpha = max(alpha, stand)
        if qd == 0 or self.nodes > self.node_limit:
            return alpha
        for m in self._order(board, list(board.generate_legal_captures())):
            board.push(m)
            s = -self.qs(board, -beta, -alpha, qd - 1)
            board.pop()
            if s >= beta:
                return s
            alpha = max(alpha, s)
        return alpha

    def search(self, board, depth, alpha, beta, ply):
        self.nodes += 1
        moves = list(board.legal_moves)
        if not moves:
            return -MATE + ply if board.is_check() else 0
        if board.is_insufficient_material():
            return 0
        if depth == 0 or self.nodes > self.node_limit:
            return self.qs(board, alpha, beta, 4)
        best = -INF
        for m in self._order(board, moves):
            board.push(m)
            s = -self.search(board, depth - 1, -beta, -alpha, ply + 1)
            board.pop()
            if s > best:
                best = s
            alpha = max(alpha, s)
            if alpha >= beta:
                break
        return best

    def root(self, board, depth):
        """(score, melhor_lance) com janela cheia. depth >= 1."""
        moves = list(board.legal_moves)
        if not moves:
            return (-MATE if board.is_check() else 0), None
        best, bm = -INF, None
        for m in self._order(board, moves):
            board.push(m)
            s = -self.search(board, depth - 1, -INF, INF, 1)
            board.pop()
            if s > best:
                best, bm = s, m
        return best, bm


def _fmt(score):
    """(cp, mate_em_plies|None) a partir do score interno."""
    if abs(score) > MATE - 100:
        n = (MATE - abs(score) + 1) // 2
        return (10000 if score > 0 else -10000), (n if score > 0 else -n)
    return score, None


def analyze(board, depth=3, top_k=6, extra=(), positional=True):
    """Analisa os lances. Retorna lista ordenada (melhor primeiro) de dicts:
    {move, score_cp (ponto de vista de quem joga), mate, pv:[SAN...]}.
    `extra` = lances adicionais (ex.: xeques/capturas) a serem avaliados também."""
    S = Searcher(positional=positional)
    b = board.copy(stack=False)
    moves = list(b.legal_moves)
    quick = []
    for m in moves:
        b.push(m)
        quick.append((-S.search(b, 1, -INF, INF, 1), m))
        b.pop()
    quick.sort(key=lambda x: -x[0])
    chosen = [m for _, m in quick[:top_k]]
    for m in extra:
        if m not in chosen and len(chosen) < top_k + 8:
            chosen.append(m)
    out = []
    for m in chosen:
        san = b.san(m)
        b.push(m)
        pv = [san]
        if b.is_checkmate():
            score = MATE - 1
        else:
            s, reply = S.root(b, max(1, depth - 1))
            score = -s
            if reply is not None:
                pv.append(b.san(reply))
                b.push(reply)
                _, nxt = S.root(b, 1)
                if nxt is not None:
                    pv.append(b.san(nxt))
                b.pop()
        b.pop()
        cp, mate = _fmt(score)
        out.append({"move": m, "san": san, "uci": m.uci(), "score_cp": cp, "mate": mate, "pv": pv})
    out.sort(key=lambda x: -x["score_cp"])
    return out
