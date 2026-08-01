---
title: "Contributing"
status: "current"
authoritative_source: "repository merge, test, and review policy"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "contributors"
maintenance: "hand-maintained"
---

# Contributing

This is a public experimental repository. Coordinate scope before beginning a
large rules or protocol change, and do not publish live game artifacts or
security-sensitive reproductions in issues or pull requests.

## Development setup

Use Python 3.11 or 3.12. Install the editable package and development tools:

```bash
python -m venv .venv
python -m pip install -e . -r requirements-dev.txt
python scripts/build_test_database.py build \
  --fixture tests/fixtures/scryfall-exact-lists.json \
  --output data/test-ci.sqlite3
cd web
npm ci
npm run generate:types
npm run typecheck
npm run build
```

Set `MTG_CARD_DB=data/test-ci.sqlite3`, then run the commands in `AGENTS.md`.
Documentation changes must keep [`docs/index.md`](docs/index.md) complete and
pass `python scripts/validate_documentation.py --check`. Put current metrics in
machine-readable sources and generated reports rather than prose.
Before merging a clean committed branch, run:

```powershell
py -3.11 scripts/local_merge_gate.py `
  --expected-branch <branch> `
  --expected-sha <full-sha>
```

The ignored exact-SHA summary is written below `local/merge-gates/`; do not
commit its logs or database.

## Change boundaries

- Keep `CommanderEngine` authoritative and preserve fixed-seat projection.
- Follow the executable dependency, mutation, specificity, documentation, and
  ADR policies; reviewed exceptions require the documented decision path.
- Keep FastAPI/Uvicorn/HTTP/WebSocket imports out of `mtg_commander_sim`; the
  `server` adapter may depend inward on the transport-neutral package.
- Run the four-context Playwright test for room, authentication, WebSocket,
  reconnect, projection, or browser decision changes.
- Add deterministic tests for rules, target, permission, or protocol changes.
- Fail closed when semantics are unresolved.
- Preserve Game Record v3 and exact command replay.
- Do not commit live records, checkpoints, database files, deck caches,
  capabilities, pilot memory, or model reasoning.
- Do not represent duplicated pods or insufficient samples as matchup evidence.

Use focused commits. Versioned feature work should update the changelog,
architecture documentation, fidelity reporting, and replay tests together.
