---
title: "Architecture debt status"
status: "generated"
authoritative_source: "coverage/architecture-audit.json"
verified: "4491e543507ebe575443eef1fed3776a26c1a0d8df682c4b79917efb8714a3ff"
audience: "maintainers and rules contributors"
maintenance: "generated"
generated_source: "coverage/architecture-audit.json"
generation_command: ".\.venv\Scripts\python.exe scripts\update_architecture_audit.py --write --card-db data\scryfall-current.sqlite3"
---

# Architecture debt status

Source fingerprint: `4491e543507ebe575443eef1fed3776a26c1a0d8df682c4b79917efb8714a3ff`

## Current top-level state

- Production logical lines: `118586`
- Engine logical lines: `12211`
- Direct GameState-write heuristic: `128`
- Registered typed semantic handlers: `92`
- Registered runtime components: `30`
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
