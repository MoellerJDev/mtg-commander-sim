---
title: "Architecture debt status"
status: "generated"
authoritative_source: "coverage/architecture-audit.json"
verified: "ff5973728476d66406179a2bc6b5113bd8483aaf"
audience: "maintainers and rules contributors"
maintenance: "generated"
---

# Architecture debt status

This generated migration dashboard is anchored to the Phase 0 baseline. It measures the current tree and does not claim architectural completion, rules completeness, or universal card support.

## Baseline coordinates

- Main commit: `ff5973728476d66406179a2bc6b5113bd8483aaf`
- Package: `0.8.0`
- CI run: [31076588097](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/31076588097) — `pass`
- Production scope: 265 files, 110,641 physical lines, 101,432 logical lines

## Central engine debt

- `engine.py`: 13,375 physical / 12,638 logical lines
- Methods: 28 public, 279 private, 1 dunder
- Cross-subsystem responsibility groups: 7
- Direct GameState-write heuristic: 133 locations
- Semantic-operation branches: 179
- Registered typed semantic handlers: 85 across 85 operations
- Registered typed runtime components: 22
- Remaining legacy `apply_effect` branches: 0
- Registered operations still intercepted by engine string dispatch: 0
- Exact printed-name literals in configured core files: 693 (98 conditional)
- Oracle-ID literals in Python production code: 5
- Card-named helpers: 1
- Modules above the 1,500-logical-line review threshold: 5
- Functions/methods above the 150-logical-line review threshold: 34
- Printed-name matching is deliberately over-inclusive: ordinary words that are also printed card names remain baseline candidates for Phase 1 review.

## Enforced debt trend

Baseline: `ff5973728476d66406179a2bc6b5113bd8483aaf`. Guard: `python scripts/validate_architecture.py --check`.

| Dimension | Baseline | Current | Delta |
|---|---:|---:|---:|
| `engine_logical_lines` | 13,017 | 12,638 | -379 |
| `direct_game_state_writes` | 135 | 133 | -2 |
| `printed_name_literals` | 693 | 693 | +0 |
| `oracle_id_literals` | 5 | 5 | +0 |
| `legacy_card_specific_operations` | 5 | 5 | +0 |
| `card_named_helpers` | 1 | 1 | +0 |
| `oversized_modules` | 5 | 5 | +0 |
| `oversized_functions_and_methods` | 35 | 34 | -1 |

## Largest production modules

| File | Language | Physical | Logical |
|---|---:|---:|---:|
| `mtg_commander_sim/engine.py` | python | 13,375 | 12,638 |
| `mtg_commander_sim/report.py` | python | 1,818 | 1,782 |
| `web/src/App.tsx` | web | 1,784 | 1,728 |
| `mtg_commander_sim/declaration_restrictions.py` | python | 1,833 | 1,679 |
| `mtg_commander_sim/record.py` | python | 1,706 | 1,605 |
| `mtg_commander_sim/damage.py` | python | 1,629 | 1,498 |
| `mtg_commander_sim/rules_corpus.py` | python | 1,561 | 1,464 |
| `mtg_commander_sim/oracle_ir.py` | python | 1,501 | 1,452 |
| `mtg_commander_sim/reusable_pieces/generation.py` | python | 1,525 | 1,430 |
| `mtg_commander_sim/cli.py` | python | 1,473 | 1,408 |
| `mtg_commander_sim/damage_results.py` | python | 1,346 | 1,235 |
| `server/app.py` | python | 1,348 | 1,206 |
| `mtg_commander_sim/damage_modifier_state.py` | python | 1,241 | 1,160 |
| `mtg_commander_sim/codex_cli.py` | python | 1,214 | 1,154 |
| `mtg_commander_sim/session.py` | python | 1,194 | 1,148 |

## Largest functions and methods

| Symbol | File:line | Logical | Physical |
|---|---|---:|---:|
| `derive_review` | `mtg_commander_sim/report.py:557` | 1085 | 1089 |
| `parse_declaration_restriction_line` | `mtg_commander_sim/declaration_restrictions.py:892` | 881 | 942 |
| `create_app` | `server/app.py:585` | 718 | 764 |
| `main` | `mtg_commander_sim/cli.py:877` | 583 | 593 |
| `_compile_face` | `mtg_commander_sim/oracle_ir.py:916` | 441 | 450 |
| `_effect_template` | `mtg_commander_sim/oracle_ir.py:125` | 429 | 430 |
| `CommanderSession.act` | `mtg_commander_sim/session.py:549` | 362 | 366 |
| `CommanderEngine._stabilize` | `mtg_commander_sim/engine.py:12616` | 342 | 354 |
| `CommanderEngine.move_card` | `mtg_commander_sim/engine.py:1541` | 341 | 347 |
| `build_parser` | `mtg_commander_sim/cli.py:514` | 337 | 361 |
| `card_semantic_status` | `mtg_commander_sim/preflight.py:447` | 302 | 302 |
| `CommanderEngine._prepare_stack_resolution` | `mtg_commander_sim/engine.py:7779` | 301 | 304 |
| `CommanderEngine._enter_step` | `mtg_commander_sim/engine.py:2935` | 282 | 312 |
| `_scripted_choice` | `mtg_commander_sim/cli.py:74` | 266 | 268 |
| `parse_declaration_cost_line` | `mtg_commander_sim/declaration_costs.py:219` | 249 | 258 |

## Engine responsibility spread

| Responsibility | Matched methods |
|---|---:|
| `turn_priority_decisions` | 39 |
| `casting_activation_and_costs` | 47 |
| `semantics_resolution_and_choices` | 74 |
| `combat_and_damage` | 29 |
| `zones_objects_and_state` | 17 |
| `commander_and_multiplayer` | 8 |
| `persistence_logging_and_invariants` | 6 |

## Missing dedicated ownership

- `turn_priority_and_decisions`
- `zones_and_object_identity`
- `search_target_and_choice`
- `trigger_processing`

These are review classifications from the machine-readable source, not automatic proof that an extraction boundary is correct.

## Test classes

- Python discovered: 4,899
- Conventional Python cases: 1,687
- Generated CR conformance cases: 3,300
- Playwright journeys: 9
- Browser unit cases: 22
- Dedicated property suite: false
- Mutation score: None
- Focused executable mutation suite: true
- Capability mutation declarations: 58
- Performance baseline: `platform/continuous-effect-performance-baseline.json` (5 scenarios; latency observational)

## Documentation drift

- Required: 33
- Present after generated Phase 0 outputs: 33
- Missing: 0
- Metadata complete: 33

The authoritative index, metadata, internal-link, stale-claim, and ADR policies are enforced by `scripts/validate_documentation.py`. Detailed document records remain in `coverage/architecture-audit.json`.

## Regeneration

```bash
python scripts/update_architecture_audit.py --write --card-db data/scryfall-current.sqlite3
python scripts/update_architecture_audit.py --check
```
