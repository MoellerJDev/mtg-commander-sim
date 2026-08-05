---
title: "Local card database"
status: "current"
authoritative_source: "managed Scryfall data service and card database schema"
verified: "2026-08-05"
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

For the complete local corpus, start the application normally or run the managed
bulk-data refresh explicitly:

```powershell
.\.venv\Scripts\python.exe scripts\bootstrap_data.py `
  --refresh-from-scryfall `
  --output data/scryfall-current.sqlite3
```

The active runtime path is:

```text
data/scryfall-current.sqlite3
```

Managed snapshots, compressed bulk files and card images are local cache data.
They are ignored by Git and are not packaged in the wheel.
