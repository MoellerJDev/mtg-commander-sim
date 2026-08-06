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
- Queued rules: 3,008
- Reviewed behavioral blockers: 373
- Behavioral classification/review required: 2,635
- Passing behavioral rules: 166
- Subsystems: 21
- Queue fingerprint: `54a9dbaedd6903eac4af5627798f3a4592ba55349fd9c27b4fb4ccf7803ffc37`

## Selected next batch

- Batch: `typed-combat-evasion-restriction-bundle`
- Subsystem: `keyword-abilities`
- Rules: `702.13`, `702.13a`, `702.13b`, `702.13c`, `702.28`, `702.28a`, `702.28b`, `702.28c`, `702.31`, `702.31a`, `702.31b`, `702.31c`, `702.36`, `702.36a`, `702.36b`, `702.36c`, `702.118`, `702.118a`, `702.118b`, `702.118c`
- Target capabilities: `combat.block.fear`, `combat.block.horsemanship`, `combat.block.intimidate`, `combat.block.shadow`, `combat.block.skulk`
- Rationale: After the Basic Landwalk harvest, the refreshed pinned Commander frontier records 136 cards affected by Fear, Horsemanship, Intimidate, Shadow, or Skulk, 31 cards whose complete blocker set is closed by the bundle, 35 one-additional-blocker opportunities, 55 two-additional-blocker opportunities, and 136 material residuals. These five keyword families share the current typed combat-evasion boundary while retaining fine-grained capability closure.

Exit criteria:

- Introduce typed read-only Fear, Horsemanship, Intimidate, Shadow, and Skulk restriction owners composed through the same projected and accepted block-legality boundary.
- Consume current effective attacker and blocker keywords, colors, artifact/creature types, and power without runtime Oracle parsing or a second characteristic evaluator.
- Apply every represented evasion restriction cumulatively, including Fear/Intimidate artifact and color exceptions, Shadow and Horsemanship pair matching, and Skulk's current power comparison.
- Reject malformed or caller-invented characteristic and combat relationships before mutation and preserve exact replay, rollback, four-player seat projection, property, explicit interaction, and killed-mutation evidence.
- Lower all five printed keywords generically into CardProgram V2 with precise source spans and separate fine-grained capability contracts.
- Leave conditional, value-modified, rules-text-equivalent, unsupported continuous-characteristic, and broader CR 509 variants explicit residuals; do not trust an aggregate evasion family beyond its certified pieces.

## Dependency schedule

| Order | Subsystem | Dependencies | Queued | Reviewed blocked | Review required | Compiler impact |
|---:|---|---|---:|---:|---:|---|
| 1 | `core-game` | — | 100 | 0 | 100 | `none` |
| 2 | `characteristics` | `core-game` | 221 | 1 | 220 | `oracle_normalization`, `card_program_typing`, `mechanic_contracts` |
| 3 | `objects-permanents-tokens` | `core-game`, `characteristics` | 56 | 0 | 56 | `oracle_parser`, `card_program_lowering`, `mechanic_contracts` |
| 4 | `mana-costs-priority` | `core-game`, `characteristics`, `objects-permanents-tokens` | 175 | 0 | 175 | `oracle_parser`, `card_program_costs`, `card_program_targets`, `mechanic_contracts` |
| 5 | `card-types` | `characteristics`, `objects-permanents-tokens` | 168 | 17 | 151 | `oracle_normalization`, `card_program_typing`, `mechanic_contracts` |
| 6 | `zones` | `objects-permanents-tokens`, `card-types` | 39 | 39 | 0 | `card_program_zone_permissions`, `mechanic_contracts` |
| 7 | `resources` | `mana-costs-priority`, `zones` | 66 | 5 | 61 | `oracle_parser`, `card_program_lowering`, `mechanic_contracts` |
| 8 | `damage` | `characteristics`, `objects-permanents-tokens`, `resources` | 11 | 11 | 0 | `oracle_parser`, `card_program_lowering`, `mechanic_contracts` |
| 9 | `turn-structure` | `mana-costs-priority`, `zones`, `resources` | 26 | 26 | 0 | `runtime_contracts`, `mechanic_contracts` |
| 10 | `casting-activation` | `mana-costs-priority`, `zones`, `turn-structure` | 46 | 46 | 0 | `oracle_parser`, `card_program_costs`, `card_program_lowering`, `mechanic_contracts` |
| 11 | `triggered-static-linked` | `objects-permanents-tokens`, `turn-structure`, `casting-activation` | 71 | 71 | 0 | `oracle_parser`, `event_binding`, `card_program_lowering`, `mechanic_contracts` |
| 12 | `resolution-effects` | `zones`, `casting-activation`, `triggered-static-linked` | 42 | 28 | 14 | `oracle_parser`, `card_program_lowering`, `semantic_handlers` |
| 13 | `continuous-effects` | `characteristics`, `objects-permanents-tokens`, `triggered-static-linked`, `resolution-effects` | 64 | 12 | 52 | `oracle_parser`, `card_program_lowering`, `mechanic_contracts` |
| 14 | `replacement-prevention` | `resources`, `damage`, `resolution-effects`, `continuous-effects` | 33 | 33 | 0 | `oracle_parser`, `card_program_lowering`, `event_binding`, `mechanic_contracts` |
| 15 | `combat` | `damage`, `turn-structure`, `continuous-effects` | 75 | 75 | 0 | `runtime_contracts`, `mechanic_contracts` |
| 16 | `game-actions-state` | `zones`, `turn-structure`, `combat`, `resolution-effects`, `replacement-prevention` | 516 | 5 | 511 | `oracle_parser`, `card_program_lowering`, `mechanic_contracts` |
| 17 | `keyword-abilities` | `casting-activation`, `continuous-effects`, `replacement-prevention`, `combat`, `game-actions-state` | 724 | 4 | 720 | `oracle_parser`, `card_program_lowering`, `mechanic_contracts` |
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
