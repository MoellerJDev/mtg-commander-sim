---
title: "Local application operations"
status: "current"
authoritative_source: "server launcher, settings, managed data service, and browser build"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "local users and contributors"
maintenance: "hand-maintained"
---

# Local application operations

## Start

From the repository root in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e . -r requirements-dev.txt
python -m server
```

The one process installs/builds the browser when needed, checks the Scryfall
bulk manifest, creates or activates the local card/rulings SQLite snapshot,
serves local card images on demand, starts HTTP/WebSocket endpoints, and opens
the browser. First setup can remain on the progress screen while data builds.

Use `Ctrl+C` for a clean stop and the same command to resume. Do not run two
local servers against the same data root; on Windows, an older process can hold
the active SQLite file open and delay pending-snapshot activation.

## Useful modes

```powershell
python -m server --no-open
python -m server --offline
$env:MTG_CARD_DB = "data/test-ci.sqlite3"
python -m server --offline
```

`--offline` requires a usable existing database. Runtime records, databases,
bulk archives, images, logs, and capabilities are ignored local data. Do not
commit them.

## Inspect and recover

The setup/system panel reports card-data readiness and pending activation.
Room/game pages expose only seat-safe lifecycle and record inspection. A rules
boundary requires code/semantic work or a fresh compatible game; administrative
resume cannot clear it. See [server/browser details](../../SERVER_BROWSER.md)
and the [local content boundary](../LEGAL_CONTENT_BOUNDARY.md).
