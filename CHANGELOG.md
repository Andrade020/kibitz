# Changelog

All notable changes are documented here. Format based on [Keep a Changelog](https://keepachangelog.com/); versions follow
[SemVer](https://semver.org/) with `-beta.N` pre-releases.

## [0.1.0-beta.2] — 2026-10-22

### Changed
- **Renamed to Kibitz** (formerly "Think-Aloud Chess"). *Kibitz* is the chess term for commenting on someone else's game.
  The Python package, command (`kibitz`), installer (`Kibitz-<version>-Setup.exe`), data folder (`%LOCALAPPDATA%\Kibitz`) and the
  repository (`Andrade020/kibitz`) all follow the new name; the old repository URL redirects.
- New visual identity: dark, cinematic look; new logo (a knight "commenting" with a `!?` bubble), README banner and social preview.
- README rewritten (English and Portuguese) with a clearer story and screenshots in the dark theme.

## [0.1.0-beta.1] — 2026-10-22

First public beta.

### Added
- Play chess against an LLM that **thinks out loud** (layered reasoning saved for every move), via the Claude Code CLI or any
  OpenAI-compatible API (DeepSeek, OpenAI, OpenRouter, Groq, Ollama…).
- **Hallucination guards**: legal-move validation with retries, objective facts computed by code, optional quiet reviewer model.
- **Adjustable engine help** (full / material-only / none) plus a hidden audit of agreement with the engine; reasoning hidden
  until the game ends.
- **AI teacher review** (opt-in): Stockfish ground truth, critical moments, concept-based explanations, arrows, chess.com-style
  walkthrough with evaluation bar, "next comment" navigation and sounds.
- Local **audit** (accuracy, average loss, error counts), token/cost tracking with soft budget.
- Games: undo, compact `.gz` export/import, readable Markdown autosave, cleanup of exported games.
- **Windows installer** (per-user, bundled Python + Stockfish, tray icon) with a first-run setup assistant (install Claude Code,
  sign in, or add an API key) and a **demo game** with a full review that costs no tokens.
- 26 automated tests, CI, and reproducible installer build.

### Known issues
- UI is Portuguese only. Windows installer is unsigned (SmartScreen shows "Unknown publisher"). No macOS/Linux installer yet.
