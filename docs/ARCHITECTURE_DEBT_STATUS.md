---
title: "Architecture debt status"
status: "generated"
authoritative_source: "coverage/architecture-audit.json"
verified: "40241e6a7a4e77a3dab3df93c6a726b0f82186fb"
audience: "maintainers and rules contributors"
maintenance: "generated"
---

# Architecture debt status

This generated migration dashboard is anchored to the Phase 0 baseline. It measures the current tree and does not claim architectural completion, rules completeness, or universal card support.

## Baseline coordinates

- Main commit: `40241e6a7a4e77a3dab3df93c6a726b0f82186fb`
- Package: `0.8.0`
- CI run: [30732155279](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30732155279) — `pass`
- Production scope: 97 files, 69,049 physical lines, 64,386 logical lines

## Central engine debt

- `engine.py`: 23,482 physical / 22,651 logical lines
- Methods: 28 public, 301 private, 1 dunder
- Cross-subsystem responsibility groups: 7
- Direct GameState-write heuristic: 179 locations
- Semantic-operation branches: 216
- Registered typed semantic handlers: 6 across 6 operations
- Registered typed runtime components: 8
- Remaining legacy `apply_effect` branches: 70
- Registered operations still intercepted by engine string dispatch: 0
- Exact printed-name literals in configured core files: 729 (114 conditional)
- Oracle-ID literals in Python production code: 7
- Card-named helpers: 1
- Modules above the 1,500-logical-line review threshold: 6
- Functions/methods above the 150-logical-line review threshold: 52
- Printed-name matching is deliberately over-inclusive: ordinary words that are also printed card names remain baseline candidates for Phase 1 review.

## Enforced debt trend

Baseline: `b29cc7ce3b048b94eb6483b10bbbc3e7f9364f16`. Guard: `python scripts/validate_architecture.py --check`.

| Dimension | Baseline | Current | Delta |
|---|---:|---:|---:|
| `engine_logical_lines` | 22,651 | 22,651 | +0 |
| `direct_game_state_writes` | 179 | 179 | +0 |
| `printed_name_literals` | 729 | 729 | +0 |
| `oracle_id_literals` | 7 | 7 | +0 |
| `legacy_card_specific_operations` | 15 | 15 | +0 |
| `card_named_helpers` | 1 | 1 | +0 |
| `oversized_modules` | 6 | 6 | +0 |
| `oversized_functions_and_methods` | 52 | 52 | +0 |

## Largest production modules

| File | Language | Physical | Logical |
|---|---:|---:|---:|
| `mtg_commander_sim/engine.py` | python | 23,482 | 22,651 |
| `web/src/App.tsx` | web | 1,889 | 1,828 |
| `mtg_commander_sim/report.py` | python | 1,853 | 1,813 |
| `mtg_commander_sim/oracle_ir.py` | python | 1,830 | 1,761 |
| `mtg_commander_sim/declaration_restrictions.py` | python | 1,833 | 1,679 |
| `mtg_commander_sim/record.py` | python | 1,726 | 1,620 |
| `mtg_commander_sim/rules_corpus.py` | python | 1,561 | 1,464 |
| `mtg_commander_sim/cli.py` | python | 1,388 | 1,336 |
| `mtg_commander_sim/replacement_effects.py` | python | 1,403 | 1,268 |
| `server/app.py` | python | 1,304 | 1,171 |
| `mtg_commander_sim/codex_cli.py` | python | 1,214 | 1,154 |
| `mtg_commander_sim/damage_results.py` | python | 1,230 | 1,126 |
| `mtg_commander_sim/session.py` | python | 1,142 | 1,099 |
| `mtg_commander_sim/damage.py` | python | 1,196 | 1,074 |
| `mtg_commander_sim/arena.py` | python | 1,106 | 1,033 |

## Largest functions and methods

| Symbol | File:line | Logical | Physical |
|---|---|---:|---:|
| `CommanderEngine.apply_effect` | `mtg_commander_sim/engine.py:21197` | 2130 | 2139 |
| `CommanderEngine._begin_semantic_choice` | `mtg_commander_sim/engine.py:13391` | 1640 | 1640 |
| `CommanderEngine._complete_semantic_choice` | `mtg_commander_sim/engine.py:15032` | 1454 | 1456 |
| `derive_review` | `mtg_commander_sim/report.py:565` | 1085 | 1089 |
| `parse_declaration_restriction_line` | `mtg_commander_sim/declaration_restrictions.py:892` | 881 | 942 |
| `create_app` | `server/app.py:536` | 724 | 769 |
| `CommanderEngine._cast` | `mtg_commander_sim/engine.py:6138` | 622 | 625 |
| `main` | `mtg_commander_sim/cli.py:758` | 617 | 627 |
| `_compile_face` | `mtg_commander_sim/oracle_ir.py:917` | 615 | 623 |
| `CommanderEngine._priority_action_hints` | `mtg_commander_sim/engine.py:9258` | 579 | 581 |
| `_effect_template` | `mtg_commander_sim/oracle_ir.py:321` | 526 | 527 |
| `CommanderEngine._cast_cost_options` | `mtg_commander_sim/engine.py:8833` | 418 | 424 |
| `build_parser` | `mtg_commander_sim/cli.py:351` | 381 | 405 |
| `CommanderEngine._activate` | `mtg_commander_sim/engine.py:7338` | 375 | 383 |
| `CommanderSession.act` | `mtg_commander_sim/session.py:533` | 362 | 366 |

## Engine responsibility spread

| Responsibility | Matched methods |
|---|---:|
| `turn_priority_decisions` | 39 |
| `casting_activation_and_costs` | 52 |
| `semantics_resolution_and_choices` | 82 |
| `combat_and_damage` | 31 |
| `zones_objects_and_state` | 17 |
| `commander_and_multiplayer` | 8 |
| `persistence_logging_and_invariants` | 6 |

## Missing dedicated ownership

- `turn_priority_and_decisions`
- `zones_and_object_identity`
- `casting_activation_and_costs`
- `search_target_and_choice`
- `trigger_processing`
- `commander_variant`

These are review classifications from the machine-readable source, not automatic proof that an extraction boundary is correct.

## Test classes

- Python discovered: 4,309
- Conventional Python cases: 1,009
- Generated CR conformance cases: 3,300
- Playwright journeys: 7
- Browser unit cases: 14
- Dedicated property suite: false
- Mutation score: None
- Focused executable mutation suite: true
- Capability mutation declarations: 19
- Performance baseline: `platform/continuous-effect-performance-baseline.json` (5 scenarios; latency observational)

## Documentation drift

- Required: 31
- Present after generated Phase 0 outputs: 31
- Missing: 0
- Metadata complete: 31

The authoritative index, metadata, internal-link, stale-claim, and ADR policies are enforced by `scripts/validate_documentation.py`. Detailed document records remain in `coverage/architecture-audit.json`.

## Regeneration

```bash
python scripts/update_architecture_audit.py --write --card-db data/scryfall-current.sqlite3
python scripts/update_architecture_audit.py --check
```
