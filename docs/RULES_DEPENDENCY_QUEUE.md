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
- Queued rules: 3,049
- Reviewed behavioral blockers: 350
- Behavioral classification/review required: 2,699
- Passing behavioral rules: 138
- Subsystems: 21
- Queue fingerprint: `ddbf09750036e2df499d652f2f7c72c93488d035e76bd9cc9f93749a44eb4a59`

## Selected next batch

- Batch: `canonical-life-and-simple-zone-triggers`
- Subsystem: `triggered-static-linked`
- Rules: `603.2`
- Target capabilities: `trigger.event.normalized_zone_change`, `life.change.effect`, `zone.draw.library_to_hand`
- Rationale: The pinned Commander-legal residual census makes trigger wording the largest high-frequency executable family: simple enters-the-battlefield life-gain and draw triggers alone account for 180 repeated normalized instructions. The existing stack-placement/APNAP boundary is trusted, while normalized event production, generic life-change ownership, and draw dependency closure still prevent broad CardProgram promotion. This batch therefore joins one reusable zone-change trigger detector to canonical result transactions before expanding into target, modal, reflexive, or state-trigger grammar.

Exit criteria:

- Produce typed normalized battlefield-enter and battlefield-leave/death occurrences from the canonical zone-change commit, including simultaneous objects and last-known source facts.
- Detect one represented trigger occurrence per matching event and place it through the existing ordinary APNAP/controller-order stack boundary.
- Route fixed life gain and loss through one replacement-capable life-change capability, and either certify or explicitly retain the draw capability blocker.
- Lower closed targetless self-enter and self-dies fixed life/draw wording without printed-name or Oracle-ID dispatch.
- Cover source departure, control change, multiplayer simultaneous entry/death, rollback, projection privacy, save/load, and exact replay.
- Measure Commander-legal exact and capability-closed gains; keep targeted, modal, intervening-if, reflexive, state, and visibility-dependent trigger families residual.

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
| 14 | `replacement-prevention` | `resources`, `damage`, `resolution-effects`, `continuous-effects` | 33 | 33 | 0 | `oracle_parser`, `card_program_lowering`, `event_binding`, `mechanic_contracts` |
| 15 | `combat` | `damage`, `turn-structure`, `continuous-effects` | 75 | 75 | 0 | `runtime_contracts`, `mechanic_contracts` |
| 16 | `game-actions-state` | `zones`, `turn-structure`, `combat`, `resolution-effects`, `replacement-prevention` | 516 | 4 | 512 | `oracle_parser`, `card_program_lowering`, `mechanic_contracts` |
| 17 | `keyword-abilities` | `casting-activation`, `continuous-effects`, `replacement-prevention`, `combat`, `game-actions-state` | 745 | 0 | 745 | `oracle_parser`, `card_program_lowering`, `mechanic_contracts` |
| 18 | `alternate-card-forms` | `card-types`, `zones`, `casting-activation`, `continuous-effects`, `replacement-prevention`, `game-actions-state` | 249 | 0 | 249 | `oracle_normalization`, `oracle_parser`, `card_program_faces`, `card_program_zone_permissions`, `mechanic_contracts` |
| 19 | `designations-variants` | `turn-structure`, `combat`, `triggered-static-linked` | 9 | 0 | 9 | `oracle_parser`, `card_program_lowering`, `mechanic_contracts` |
| 20 | `multiplayer` | `core-game`, `turn-structure`, `combat` | 182 | 0 | 182 | `runtime_contracts`, `mechanic_contracts` |
| 21 | `formats` | `zones`, `casting-activation`, `alternate-card-forms`, `designations-variants`, `multiplayer` | 135 | 0 | 135 | `format_contracts`, `card_program_zone_permissions`, `mechanic_contracts` |

## Commands

```bash
python scripts/update_rules_scheduler.py --check
python simctl.py rules queue --root .
python simctl.py rules next --root . --limit 20
```

`rules next` returns the source-selected subsystem batch. Changing that selection requires changing the machine-readable catalog and regenerating this report; it is not a numerical walk through rule IDs.
