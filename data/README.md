# Local card database

The simulator reads a local SQLite database built from Scryfall's Oracle-card and
rulings bulk files. The database is intentionally not committed to source control.

Complete bundle: `scryfall-20260728-compact.sqlite3` is already present here.

Source-only checkout: place `scryfall-20260728-compact.sqlite3.gz` in this directory
and run:

```bash
python scripts/bootstrap_data.py
```

The default runtime path is:

```text
data/scryfall-20260728-compact.sqlite3
```
