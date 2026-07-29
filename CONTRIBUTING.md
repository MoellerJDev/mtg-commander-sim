# Contributing

This is a private experimental repository. Coordinate scope before beginning a
large rules or protocol change.

## Development setup

Use Python 3.11 or 3.12. Install the editable package and development tools:

```bash
python -m venv .venv
python -m pip install -e . -r requirements-dev.txt
python scripts/build_test_database.py build \
  --fixture tests/fixtures/scryfall-exact-lists.json \
  --output data/test-ci.sqlite3
```

Set `MTG_CARD_DB=data/test-ci.sqlite3`, then run the commands in `AGENTS.md`.

## Change boundaries

- Keep `CommanderEngine` authoritative and preserve fixed-seat projection.
- Add deterministic tests for rules, target, permission, or protocol changes.
- Fail closed when semantics are unresolved.
- Preserve Game Record v3 and exact command replay.
- Do not commit live records, checkpoints, database files, deck caches,
  capabilities, pilot memory, or model reasoning.
- Do not represent duplicated pods or insufficient samples as matchup evidence.

Use focused commits. Versioned feature work should update the changelog,
architecture documentation, fidelity reporting, and replay tests together.
