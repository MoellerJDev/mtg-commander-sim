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
- Queued rules: 3,057
- Reviewed behavioral blockers: 358
- Behavioral classification/review required: 2,699
- Passing behavioral rules: 130
- Subsystems: 21
- Queue fingerprint: `a0a5544b3864f10c1aada6a4bc65c9c4b1bdd596df989643785436402de602d1`

## Selected next batch

- Batch: `damage-prevention-shields-and-redirection`
- Subsystem: `replacement-prevention`
- Rules: `614.9`, `615.1`, `615.2`, `615.3`, `615.4`, `615.5`, `615.7`, `615.8`, `615.9`, `615.11`, `615.12`, `615.13`, `616.1`
- Target capabilities: `damage.prevention.static_fixed`, `damage.replacement.static_quantity`, `replacement.order.choice`
- Rationale: The typed immutable replacement tree and canonical damage-result boundary are now integrated. The next dependency-ready family is persistent damage prevention and redirection: it closes shield lifetime and consumption, source/LKI selection, simultaneous allocation, unpreventable interaction, and replayable affected-player ordering before widening into unrelated Battle rules.

Exit criteria:

- Represent persistent, next-instance, chosen-source, and divisible prevention shields with typed immutable state, explicit duration, remaining amount, and deterministic consumption.
- Route every represented damage producer, including mana-result damage, through resumable affected-player replacement and prevention choices before mutation.
- Implement typed damage redirection with source, destination, departed-player, target-legality, and recursively replaced redirected-damage handling.
- Apply damage-can't-be-prevented without consuming a shield while preserving applicable nonprevention replacement effects.
- Snapshot or derive chosen-source characteristics with exact last-known-information behavior when the source leaves.
- Collect simultaneous divisible allocations and replacement order in APNAP order through seat-scoped replayable continuations.
- Dispatch represented additional prevention results and prevention-applied events exactly once at the correct post-prevention boundary.
- Widen generic Oracle/CardProgram lowering for the closed shield and redirection wording family, measure Commander-card gains, and leave unsupported dynamic grammar fail-closed.
- Extract shield registry, consumption, and redirection ownership from CommanderEngine into bounded typed modules with independent rollback, replay, privacy, property, and mutation tests.

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
