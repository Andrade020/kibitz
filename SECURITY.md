# Security

## Where your secrets live

- API keys are stored **in plain text** in `config.json` inside your local data folder
  (`%LOCALAPPDATA%\Kibitz` on Windows, `./data` when running from a clone). The file never leaves your machine, is
  git-ignored, and the keys are never written to games, exports, autosaves, logs or sent to the browser (the UI only sees a masked
  value).
- Anyone with access to your user account can read that file. Use a key with a spending limit, and **revoke it** at the
  provider if you ever share the folder.
- Your Claude account is handled by the official Claude Code CLI; this app never sees your credentials.

## Network access

The app listens only on `127.0.0.1` by default. It contacts: the model provider you configured; winget when you click
"install Claude Code"; nothing else. There is no telemetry. If you pass `--host 0.0.0.0` you expose an unauthenticated app to
your network — don't.

## Reporting a vulnerability

Please use GitHub's **private vulnerability reporting** ("Security" tab → "Report a vulnerability"), not a public issue.
This is a beta maintained by one person; expect a reply within a few days.
