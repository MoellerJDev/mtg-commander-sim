---
title: "Architecture debt status"
status: "generated"
authoritative_source: "coverage/architecture-audit.json"
verified: "0f0e97f1ffec83ba99e378e79cd413c739d3cdcabb2cd68feb54c5c19e4e7b44"
audience: "maintainers and rules contributors"
maintenance: "generated"
generated_source: "coverage/architecture-audit.json"
generation_command: ".\.venv\Scripts\python.exe scripts\update_architecture_audit.py --write --card-db data\scryfall-current.sqlite3"
---

# Architecture debt status

Source fingerprint: `0f0e97f1ffec83ba99e378e79cd413c739d3cdcabb2cd68feb54c5c19e4e7b44`

## Current top-level state

- Production logical lines: `105260`
- Engine logical lines: `12513`
- Direct GameState-write heuristic: `130`
- Registered typed semantic handlers: `85`
- Registered runtime components: `28`
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
