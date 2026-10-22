# Contributing

Thanks for helping! This is a beta, so small focused PRs and clear bug reports are the most useful.

## Setup

```bash
git clone https://github.com/Andrade020/kibitz && cd kibitz
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                                              # 26 tests, no network, no tokens
python -m kibitz                         # data goes to ./data (git-ignored)
```

You do **not** need an API key or Claude Code to work on most things: the tests fake the model, and the **demo game** (button on
the home screen) exercises the review UI with a saved review.

## Where to help

- **i18n**: the UI strings are Portuguese and live in `kibitz/static/` (`index.html`, `app.js`). A small string table
  and an English translation would be a great first PR.
- **Packaging**: macOS/Linux installers (PyInstaller specs are in `installer/`).
- **Teaching quality**: prompts in `kibitz/prompts/` (player, reviewer, teacher).
- **UX/accessibility** of the review mode.

## Guidelines

- Keep the player **fair**: nothing that leaks the model's reasoning or a strong engine into the live game by default.
- Anything the model returns that can be checked (moves, squares, ids) must be **validated** before it is shown or saved.
- Add or update a test when you change behavior (`tests/`). Tests must not need the network or spend tokens.
- Match the surrounding style; keep comments to the non-obvious *why*.

## Releasing (maintainers)

Bump `__version__` in `kibitz/__init__.py`, update `CHANGELOG.md`, tag `vX.Y.Z[-beta.N]`; the *Release* workflow builds
the Windows installer and attaches it to the release.
