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
- Queue fingerprint: `432019295dff0f360101f903724e9c07b0cf5a34d495245de8696406296d54cb`

## Selected next batch

- Batch: `damage-prevention-continuations-and-aftermath`
- Subsystem: `replacement-prevention`
- Rules: `615.1`, `615.2`, `615.5`, `615.9`, `616.1`
- Target capabilities: `damage.prevention.persistent_amount`, `damage.prevention.order`, `damage.result.replacement_order`
- Rationale: Typed dynamic/divided and per-object shields, the represented face-up CR 609.7a candidate universe, incarnation-safe permanent-spell continuity, closed source-property rechecks, replacement-capable life aftermath, permanent-counter aftermath, same-chooser event ordering, and resumable mana-payment choices are represented. Face-down source characteristics remain fail-closed. The next dependency-ready prevention boundary is closed damage-dealing and target-dependent aftermath wording plus the nested transaction and trigger behavior those results require.

Exit criteria:

- Add closed generic aftermath operations for remaining common Oracle wording, including represented damage-dealing and target-dependent forms.
- Route damage-dealing aftermath back through the typed damage transaction without admitting recursive mutation or duplicate prevention application.
- Discover and enqueue triggers created by each represented aftermath result at the correct post-prevention boundary.
- Fail before mutation when an aftermath target, quantity, replacement choice, or nested transaction becomes stale.
- Retain exact rollback, seat projection, same-chooser event ordering, and command replay across every added producer.
- Measure generic CardProgram gains from the completed residual wording families.

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
