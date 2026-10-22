# Architecture

Think-Aloud Chess is a small Flask app (`think_aloud_chess/`) with a vanilla-JS single page (`static/`). Games are plain JSON
(gzip-compressed on disk). There is no database and no build step for the front end.

## One move, end to end

1. **Validate** your move with `python-chess` and append it to the game.
2. **`facts.py`** computes objective facts: material, king safety, pawn structure, open files, pieces *en prise*, and what the
   opponent threatens if you passed. They are given to the model so it never has to reconstruct the board from memory.
3. **`engine.py`** (optional, you pick the level) runs a *shallow* alpha-beta search (3 plies + quiescence) and `facts.probe`
   flags consequences ("leaves a piece hanging", "allows mate"). Levels: **full** (material + piece-square tables, ranked),
   **material** (captures/checks only, unranked), **none**.
4. **`agent.py`** builds a compact, *stateless* prompt (ASCII board + FEN + move list + facts + probes + the model's own
   carried-over notes) and asks for structured JSON: reading → threats → plan → candidates → decision → blunder check →
   move → evaluation → confidence. The model is called through the **Claude Code CLI** with **no tools**, or through any
   **OpenAI-compatible API** (`providers.py`).
5. The move is **checked against the legal moves** (3 attempts; then a labeled engine fallback).
6. A **reviewer** model (Haiku) runs only on a strong local signal: a valuable piece newly at risk, a mate threat, a large
   shallow-engine disagreement, or low confidence combined with disagreement; never in decided positions or two moves in a
   row. If it objects, the player reconsiders once.
7. Per-move usage is recorded; past the soft budget the game drops to low effort and silences the reviewer.

The model's reasoning is **hidden in API responses while the game is ongoing** (`public()` in `app.py`), so the human can't
peek by accident. Every move also records whether it equals the hidden engine's best move.

## After the game

- **Audit** (`audit.py`): the shallow engine re-evaluates every move of both sides — accuracy, average loss, error classes.
  It is a deliberately weak ruler, so numbers are for *comparing the two sides*, not for absolute ratings.
- **Teacher review** (`review.py`, opt-in, uses tokens), in three stages that are saved as they finish:
  1. *Plan* (local, no tokens): **Stockfish** (`strong.py`, UCI) evaluates the whole game, picks the critical moments, computes
     lines and the engine's best-move arrows. Without Stockfish it falls back to the shallow audit.
  2. *Moments* (3 in parallel): one short call per moment; the teacher explains by **concepts**, using the engine's lines as
     ground truth (also to correct the model's own misreadings). Suggested moves are re-validated as legal; arrow squares are
     validated; hallucinations are dropped.
  3. *Synthesis*: summary, phases, lessons with exercises, and what the model got right/wrong.
- The front end walks the review like chess.com: the comment and arrows for a move appear as you step; the arrows live in an
  SVG layer above the pieces; the evaluation bar uses the Stockfish curve.

## Files

| Path | Role |
|---|---|
| `think_aloud_chess/app.py` | Flask routes, game storage, background threads (agent, audit, review), setup assistant endpoints |
| `agent.py`, `providers.py` | Player/reviewer/professor calls; Claude Code CLI and OpenAI-compatible providers |
| `engine.py`, `facts.py`, `audit.py` | Shallow engine, objective facts, local audit |
| `strong.py`, `review.py` | Stockfish (UCI) integration and the teacher review pipeline |
| `autosave.py`, `paths.py` | Markdown autosave; where code resources and user data live |
| `cli.py`, `desktop.py` | `think-aloud-chess` command; tray launcher used by the Windows installer |
| `prompts/` | System prompts (player, reviewer, teacher, professor, briefing) |
| `installer/` | PyInstaller spec, Inno Setup script, build script |
| `tools/` | Icon and README-media generators |
| `tests/` | 26 tests, no network, no tokens (a fake UCI engine covers the Stockfish integration) |

## Storage

`games/<id>.json.gz` (compact JSON, FENs recomputed on load), `saves/*.md` (readable autosave), `config.json` (providers and
keys), all under the data directory (`paths.py`). Export/import is the same gzip JSON; import re-plays every move and rejects
illegal ones.
