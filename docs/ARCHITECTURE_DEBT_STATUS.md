---
title: "Architecture debt status"
status: "generated"
authoritative_source: "coverage/architecture-audit.json"
verified: "ec9e0b9dc1962d910d7aca1815fa2af9a1df0dcfd43074d4c1a97ab8c6beb32d"
audience: "maintainers and rules contributors"
maintenance: "generated"
generated_source: "coverage/architecture-audit.json"
generation_command: ".\.venv\Scripts\python.exe scripts\update_architecture_audit.py --write --card-db data\scryfall-current.sqlite3"
---

# Architecture debt status

Source fingerprint: `ec9e0b9dc1962d910d7aca1815fa2af9a1df0dcfd43074d4c1a97ab8c6beb32d`

## Current top-level state

- Production logical lines: `102934`
- Engine logical lines: `12638`
- Direct GameState-write heuristic: `132`
- Registered typed semantic handlers: `85`
- Registered runtime components: `24`
- Oversized production modules: `5`

## Top blockers

- Missing dedicated owner: `turn_priority_and_decisions`.
- Missing dedicated owner: `zones_and_object_identity`.
- Missing dedicated owner: `search_target_and_choice`.
- Missing dedicated owner: `trigger_processing`.

Complete module, symbol, ownership, test, and documentation inventories are in the [machine-readable architecture audit](../coverage/architecture-audit.json).

Exact generation command:

```powershell
.\.venv\Scripts\python.exe scripts\update_architecture_audit.py --write --card-db data\scryfall-current.sqlite3
```
