---
title: "Contributing"
status: "current"
authoritative_source: "repository merge, test, and review policy"
verified: "2026-08-05"
audience: "contributors"
maintenance: "hand-maintained"
---

# Contributing

This is a public experimental repository. Coordinate scope before beginning a
large rules or protocol change, and do not publish live game artifacts or
security-sensitive reproductions in issues or pull requests.

## Development setup

Use CPython 3.12.x exactly. Python 3.11 and 3.13+ are unsupported. On Windows,
run `scripts/bootstrap_windows.ps1`, or use the exact project interpreter:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e . -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts\validate_python_runtime.py
.\.venv\Scripts\python.exe scripts\build_test_database.py build `
  --fixture tests/fixtures/scryfall-exact-lists.json `
  --output data/test-ci.sqlite3
npm ci --prefix web
npm run generate:types --prefix web
npm run typecheck --prefix web
npm run build --prefix web
```

Set `MTG_CARD_DB=data/test-ci.sqlite3` for focused tests that use card data.
Before commit, inspect and run the deterministic quick gate:

```powershell
.\.venv\Scripts\python.exe scripts/quick_gate.py --dry-run
.\.venv\Scripts\python.exe scripts/quick_gate.py
```

Documentation changes must keep [`docs/index.md`](docs/index.md) complete and
pass `.\.venv\Scripts\python.exe scripts/validate_documentation.py --check`.
Put current metrics in machine-readable sources and generated reports rather
than prose.

Public pull-request CI is the ordinary exact-head merge authority. Require the
stable `PR / Certification` context, which depends on all Linux shards,
generated and architecture checks, packaging, Windows compatibility, and the
isolated headless browser job. Use the full `scripts/local_merge_gate.py` only
for releases and unusually high-risk persistence, replay, privacy, or packaging
changes. See the [CI pipeline guide](docs/development/ci-pipeline.md) for the
two-slot workflow, shard ownership, nightly depth, and recovery commands.

## Change boundaries

- Keep `CommanderEngine` authoritative and preserve fixed-seat projection.
- Follow the executable dependency, mutation, specificity, documentation, and
  ADR policies; reviewed exceptions require the documented decision path.
- Keep FastAPI/Uvicorn/HTTP/WebSocket imports out of `mtg_commander_sim`; the
  `server` adapter may depend inward on the transport-neutral package.
- Let CI run the isolated four-context headless Playwright test for room,
  authentication, WebSocket, reconnect, projection, or browser decision
  changes. Never open or navigate a visible browser during automated work.
- Add deterministic tests for rules, target, permission, or protocol changes.
- Fail closed when semantics are unresolved.
- Preserve Game Record v3 and exact command replay.
- Do not commit live records, checkpoints, database files, deck caches,
  capabilities, pilot memory, or model reasoning.
- Do not represent duplicated pods or insufficient samples as matchup evidence.

Use focused commits. Versioned feature work should update the changelog,
architecture documentation, fidelity reporting, and replay tests together.

## Repository and documentation hygiene

The repository contains source, schemas, public fixtures, generated reports and
sanitized examples. It must not contain live Game Records, checkpoints, private
zones, raw capabilities, credentials, pilot memory, SQLite databases, Scryfall
archives, image/deck caches, build output or local virtual environments.
`scripts/validate_repository.py` checks tracked files and reachable history;
tests create private records only in temporary directories from sanitized
recipes.

Use the documentation standard in [`docs/index.md`](docs/index.md). Describe
current behavior in present tense, keep changing measurements in generated
reports, and remove superseded guidance in the same pull request. Do not add a
branch handoff, progress diary, archived status page or duplicate architecture
overview. Add an ADR only for a durable decision whose alternatives and
consequences matter after the implementation has changed.
