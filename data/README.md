---
title: "Local card database"
status: "current"
authoritative_source: "managed Scryfall data service and card database schema"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "local operators and data-layer contributors"
maintenance: "hand-maintained"
---

# Local card database

The simulator reads a local SQLite database built from Scryfall's Oracle-card
and rulings bulk files. Databases are ignored local artifacts and are not
committed to the public repository.

For deterministic tests, rebuild the compact database from the committed
sanitized fixture:

```bash
python scripts/build_test_database.py build \
  --fixture tests/fixtures/scryfall-exact-lists.json \
  --output data/test-ci.sqlite3
```

For a complete local corpus, use the bulk-data refresh command documented in
the root README. A legacy complete bundle may instead place
`scryfall-20260728-compact.sqlite3.gz` here and run:

```bash
python scripts/bootstrap_data.py
```

The legacy default runtime path is:

```text
data/scryfall-20260728-compact.sqlite3
```

Neither database path is packaged in the wheel.
