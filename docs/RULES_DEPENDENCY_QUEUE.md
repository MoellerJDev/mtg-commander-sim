---
title: "Rules dependency queue"
status: "generated"
authoritative_source: "coverage/rules-dependency-queue.json"
verified: "2026-06-19"
audience: "rules, compiler, and engine contributors"
maintenance: "generated"
---

# Rules dependency queue

This report schedules the pinned Comprehensive Rules by coupled subsystem. It does not claim that an unreviewed rule is behavioral; it conservatively keeps that rule queued until review proves otherwise.

## Queue boundary

- Pinned rules: 3,300
- Queued rules: 3,082
- Reviewed behavioral blockers: 358
- Behavioral classification/review required: 2,724
- Passing behavioral rules: 113
- Subsystems: 21
- Queue fingerprint: `8a39ab60b174f86ebf524b5397ef789e764b5641dfc9325516ec527e56a33f57`

## Selected next batch

- Batch: `battle-defense-characteristic`
- Subsystem: `characteristics`
- Rules: `210.1`
- Target capabilities: none registered yet
- Rationale: CR 210.1 is the first dependency-ready reviewed rule after the damage-result batch. Treat its printed-defense characteristic and intrinsic enters-with-defense event as one foundational Battle entry subsystem, rather than widening immediately into the downstream CR 310 casting, protector, combat, and defeated-trigger families.

Exit criteria:

- Represent printed defense as a typed effective characteristic across ordinary, copied, transformed, face-down, and off-battlefield card states without printed-name dispatch.
- Prepare the intrinsic enters-with-defense counter placement before battlefield mutation and route it through the shared replacement-event and counter-placement ordering boundaries.
- Let the affected player make every material replacement or as-enters choice through a seat-scoped replayable continuation before the permanent enters.
- Fail closed for missing, malformed, dynamic, or semantically unresolved defense values and for entry paths that cannot suspend safely.
- Preserve exact copy/new-object identity, zone-change replacement ordering, multiplayer APNAP behavior, privacy, and command replay.
- Compile and preflight the complete pinned Battle census, report exact generic-exact and blocked deltas, and retain downstream CR 310 blockers honestly.
- Extract intrinsic defense-entry ownership from CommanderEngine into a bounded characteristic/entry module without widening the central engine.

## Dependency schedule

| Order | Subsystem | Dependencies | Queued | Reviewed blocked | Review required | Compiler impact |
|---:|---|---|---:|---:|---:|---|
| 1 | `core-game` | — | 100 | 0 | 100 | `none` |
| 2 | `characteristics` | `core-game` | 221 | 1 | 220 | `oracle_normalization`, `card_program_typing`, `mechanic_contracts` |
| 3 | `objects-permanents-tokens` | `core-game`, `characteristics` | 56 | 0 | 56 | `oracle_parser`, `card_program_lowering`, `mechanic_contracts` |
| 4 | `mana-costs-priority` | `core-game`, `characteristics`, `objects-permanents-tokens` | 175 | 0 | 175 | `oracle_parser`, `card_program_costs`, `card_program_targets`, `mechanic_contracts` |
| 5 | `card-types` | `characteristics`, `objects-permanents-tokens` | 168 | 13 | 155 | `oracle_normalization`, `card_program_typing`, `mechanic_contracts` |
| 6 | `zones` | `objects-permanents-tokens`, `card-types` | 39 | 39 | 0 | `card_program_zone_permissions`, `mechanic_contracts` |
| 7 | `resources` | `mana-costs-priority`, `zones` | 82 | 3 | 79 | `oracle_parser`, `card_program_lowering`, `mechanic_contracts` |
| 8 | `damage` | `characteristics`, `objects-permanents-tokens`, `resources` | 11 | 11 | 0 | `oracle_parser`, `card_program_lowering`, `mechanic_contracts` |
| 9 | `turn-structure` | `mana-costs-priority`, `zones`, `resources` | 26 | 26 | 0 | `runtime_contracts`, `mechanic_contracts` |
| 10 | `casting-activation` | `mana-costs-priority`, `zones`, `turn-structure` | 46 | 46 | 0 | `oracle_parser`, `card_program_costs`, `card_program_lowering`, `mechanic_contracts` |
| 11 | `triggered-static-linked` | `objects-permanents-tokens`, `turn-structure`, `casting-activation` | 71 | 71 | 0 | `oracle_parser`, `event_binding`, `card_program_lowering`, `mechanic_contracts` |
| 12 | `resolution-effects` | `zones`, `casting-activation`, `triggered-static-linked` | 42 | 28 | 14 | `oracle_parser`, `card_program_lowering`, `semantic_handlers` |
| 13 | `continuous-effects` | `characteristics`, `objects-permanents-tokens`, `triggered-static-linked`, `resolution-effects` | 68 | 0 | 68 | `oracle_parser`, `card_program_lowering`, `mechanic_contracts` |
| 14 | `replacement-prevention` | `resources`, `damage`, `resolution-effects`, `continuous-effects` | 41 | 41 | 0 | `oracle_parser`, `card_program_lowering`, `event_binding`, `mechanic_contracts` |
| 15 | `combat` | `damage`, `turn-structure`, `continuous-effects` | 75 | 75 | 0 | `runtime_contracts`, `mechanic_contracts` |
| 16 | `game-actions-state` | `zones`, `turn-structure`, `combat`, `resolution-effects`, `replacement-prevention` | 516 | 4 | 512 | `oracle_parser`, `card_program_lowering`, `mechanic_contracts` |
| 17 | `keyword-abilities` | `casting-activation`, `continuous-effects`, `replacement-prevention`, `combat`, `game-actions-state` | 768 | 0 | 768 | `oracle_parser`, `card_program_lowering`, `mechanic_contracts` |
| 18 | `alternate-card-forms` | `card-types`, `zones`, `casting-activation`, `continuous-effects`, `replacement-prevention`, `game-actions-state` | 249 | 0 | 249 | `oracle_normalization`, `oracle_parser`, `card_program_faces`, `card_program_zone_permissions`, `mechanic_contracts` |
| 19 | `designations-variants` | `turn-structure`, `combat`, `triggered-static-linked` | 9 | 0 | 9 | `oracle_parser`, `card_program_lowering`, `mechanic_contracts` |
| 20 | `multiplayer` | `core-game`, `turn-structure`, `combat` | 182 | 0 | 182 | `runtime_contracts`, `mechanic_contracts` |
| 21 | `formats` | `zones`, `casting-activation`, `alternate-card-forms`, `designations-variants`, `multiplayer` | 137 | 0 | 137 | `format_contracts`, `card_program_zone_permissions`, `mechanic_contracts` |

## Commands

```bash
python scripts/update_rules_scheduler.py --check
python simctl.py rules queue --root .
python simctl.py rules next --root . --limit 20
```

`rules next` returns the source-selected subsystem batch. Changing that selection requires changing the machine-readable catalog and regenerating this report; it is not a numerical walk through rule IDs.
