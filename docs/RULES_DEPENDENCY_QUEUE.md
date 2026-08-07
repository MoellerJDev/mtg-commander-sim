---
title: "Rules dependency queue"
status: "generated"
authoritative_source: "coverage/rules-dependency-queue.json"
verified: "714624b39754471a3d24178c9f868cff6be233242ea2987662d3af03067d6c3c"
audience: "rules, compiler, and engine contributors"
maintenance: "generated"
generated_source: "coverage/rules-dependency-queue.json"
generation_command: ".\.venv\Scripts\python.exe scripts\update_rules_scheduler.py --write"
---

# Rules dependency queue

Source fingerprint: `5d061ce7788e693a3540a391dd755231ca6dd03964d3d370cbb9c7366aaf6e72`

## Current top-level state

- Pinned rules: `3300`
- Queued rules: `2972`
- Subsystems: `21`
- Selected subsystem: `keyword-abilities`
- Selected batch: `typed-ordinary-cycling-activation`

## Top blockers

- Introduce one immutable typed ordinary-Cycling descriptor that exists in every zone but is activatable only by the card's owner from that player's hand.
- Offer and accept the same seat-scoped Cycling activation, pay its represented cost, discard the exact physical card as a cost, and place the draw ability on the ordinary stack.
- Resolve through the canonical iterative replacement-aware draw transaction without runtime Oracle parsing or direct GameState writes.
- Lower only closed ordinary printed Cycling grammar with precise source spans and one fine-grained capability declaration.
- Preserve rollback, privacy, multiplayer priority, save/load, exact replay, and focused implementation mutation evidence.

Complete rule, subsystem, dependency, classification, and selected-batch data is in the [machine-readable rules queue](../coverage/rules-dependency-queue.json).

Exact generation command:

```powershell
.\.venv\Scripts\python.exe scripts\update_rules_scheduler.py --write
```
