---
title: "Rules dependency queue"
status: "generated"
authoritative_source: "coverage/rules-dependency-queue.json"
verified: "10d6e34a3aee7b482dae988f590d14b52652f46ddca071a15bff67091364c7de"
audience: "rules, compiler, and engine contributors"
maintenance: "generated"
generated_source: "coverage/rules-dependency-queue.json"
generation_command: ".\.venv\Scripts\python.exe scripts\update_rules_scheduler.py --write"
---

# Rules dependency queue

Source fingerprint: `d4f1d7c29615b09deff2b93f452af5cf3512912b1c5b7d9e360864ee362a8761`

## Current top-level state

- Pinned rules: `3300`
- Queued rules: `2982`
- Subsystems: `21`
- Selected subsystem: `keyword-abilities`
- Selected batch: `typed-attack-transition-keyword-triggers`

## Top blockers

- Introduce one typed immutable completed attack transition shared by attack declarations, Exalted, Battle Cry, Melee, trigger batching, replay, and projection.
- Lower ordinary printed Exalted, Battle Cry, and Melee generically with precise source spans and fine-grained capability closure.
- Derive one occurrence per current ability instance using exact attacks-alone, other-attacker, and distinct-defending-player semantics from the sealed transition.
- Apply resolving power and toughness changes through the canonical continuous-characteristic owner without direct GameState writes or runtime Oracle parsing.
- Preserve multiplayer declaration completion, APNAP trigger ordering, exact replay, rollback, privacy, source departure, multiple-instance, and focused mutation evidence.

Complete rule, subsystem, dependency, classification, and selected-batch data is in the [machine-readable rules queue](../coverage/rules-dependency-queue.json).

Exact generation command:

```powershell
.\.venv\Scripts\python.exe scripts\update_rules_scheduler.py --write
```
