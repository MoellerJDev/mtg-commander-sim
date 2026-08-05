---
title: "Local application operations"
status: "current"
authoritative_source: "server launcher, settings, managed data service, and browser build"
verified: "2026-08-05"
audience: "local users and contributors"
maintenance: "hand-maintained"
---

# Local application operations

## Start

From the repository root in PowerShell:

```powershell
.\scripts\bootstrap_windows.ps1
.\.venv\Scripts\python.exe -m server
```

The application requires CPython 3.12.x exactly. The bootstrap script never
changes global `PATH`, removes another Python, elevates itself, or opens a
browser. If 3.12 is missing it prints a safe per-user `winget` command and
stops. Manual setup uses `py -3.12 -m venv .venv` and the resulting
`.\.venv\Scripts\python.exe` for every project command.

The one process installs/builds the browser when needed, checks the Scryfall
bulk manifest, creates or activates the local card/rulings SQLite snapshot,
serves local card images on demand, starts HTTP/WebSocket endpoints, and prints
the local URL. It does not open or focus a browser unless you explicitly add
`--open`. First setup can remain on the progress screen while data builds.

Use `Ctrl+C` for a clean stop and the same command to resume. Do not run two
local servers against the same data root; on Windows, an older process can hold
the active SQLite file open and delay pending-snapshot activation.

## Useful modes

```powershell
.\.venv\Scripts\python.exe -m server --open
.\.venv\Scripts\python.exe -m server --offline
$env:MTG_CARD_DB = "data/test-ci.sqlite3"
.\.venv\Scripts\python.exe -m server --offline
```

`--open` opts into automatic browser launch. The legacy `--no-open` flag is
still accepted but is now equivalent to the safe default. `--offline` requires
a usable existing database. Runtime records, databases,
bulk archives, images, logs, and capabilities are ignored local data. Do not
commit them.

## Inspect and recover

The setup/system panel reports card-data readiness and pending activation.
Room/game pages expose only seat-safe lifecycle and record inspection. A rules
boundary requires code/semantic work or a fresh compatible game; administrative
resume cannot clear it. See [server/browser details](../../SERVER_BROWSER.md)
and the [local content boundary](../LEGAL_CONTENT_BOUNDARY.md).
