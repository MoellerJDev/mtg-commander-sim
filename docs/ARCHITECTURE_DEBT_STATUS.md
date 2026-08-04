---
title: "Architecture debt status"
status: "generated"
authoritative_source: "coverage/architecture-audit.json"
verified: "797a7157bec6f7509ab68d946aee1c3efac2b32c"
audience: "maintainers and rules contributors"
maintenance: "generated"
---

# Architecture debt status

This generated migration dashboard is anchored to the Phase 0 baseline. It measures the current tree and does not claim architectural completion, rules completeness, or universal card support.

## Baseline coordinates

- Main commit: `797a7157bec6f7509ab68d946aee1c3efac2b32c`
- Package: `0.8.0`
- CI run: [30868127255](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30868127255) — `pass`
- Production scope: 196 files, 92,024 physical lines, 84,707 logical lines

## Central engine debt

- `engine.py`: 14,459 physical / 13,685 logical lines
- Methods: 28 public, 286 private, 1 dunder
- Cross-subsystem responsibility groups: 7
- Direct GameState-write heuristic: 136 locations
- Semantic-operation branches: 145
- Registered typed semantic handlers: 83 across 83 operations
- Registered typed runtime components: 11
- Remaining legacy `apply_effect` branches: 0
- Registered operations still intercepted by engine string dispatch: 0
- Exact printed-name literals in configured core files: 680 (100 conditional)
- Oracle-ID literals in Python production code: 6
- Card-named helpers: 1
- Modules above the 1,500-logical-line review threshold: 6
- Functions/methods above the 150-logical-line review threshold: 37
- Printed-name matching is deliberately over-inclusive: ordinary words that are also printed card names remain baseline candidates for Phase 1 review.

## Enforced debt trend

Baseline: `cda213c987cb8c5aef94af74bc74146f29bba0fb`. Guard: `python scripts/validate_architecture.py --check`.

| Dimension | Baseline | Current | Delta |
|---|---:|---:|---:|
| `engine_logical_lines` | 14,761 | 13,685 | -1,076 |
| `direct_game_state_writes` | 143 | 136 | -7 |
| `printed_name_literals` | 693 | 680 | -13 |
| `oracle_id_literals` | 6 | 6 | +0 |
| `legacy_card_specific_operations` | 6 | 6 | +0 |
| `card_named_helpers` | 1 | 1 | +0 |
| `oversized_modules` | 6 | 6 | +0 |
| `oversized_functions_and_methods` | 40 | 37 | -3 |

## Largest production modules

| File | Language | Physical | Logical |
|---|---:|---:|---:|
| `mtg_commander_sim/engine.py` | python | 14,459 | 13,685 |
| `web/src/App.tsx` | web | 1,886 | 1,825 |
| `mtg_commander_sim/report.py` | python | 1,853 | 1,813 |
| `mtg_commander_sim/oracle_ir.py` | python | 1,767 | 1,704 |
| `mtg_commander_sim/declaration_restrictions.py` | python | 1,833 | 1,679 |
| `mtg_commander_sim/record.py` | python | 1,706 | 1,605 |
| `mtg_commander_sim/rules_corpus.py` | python | 1,561 | 1,464 |
| `mtg_commander_sim/damage.py` | python | 1,573 | 1,442 |
| `mtg_commander_sim/cli.py` | python | 1,408 | 1,350 |
| `mtg_commander_sim/damage_results.py` | python | 1,308 | 1,202 |
| `server/app.py` | python | 1,305 | 1,171 |
| `mtg_commander_sim/damage_modifier_state.py` | python | 1,241 | 1,160 |
| `mtg_commander_sim/codex_cli.py` | python | 1,214 | 1,154 |
| `mtg_commander_sim/session.py` | python | 1,163 | 1,120 |
| `mtg_commander_sim/effect_runtime/zones_and_attachments.py` | python | 1,106 | 1,043 |

## Largest functions and methods

| Symbol | File:line | Logical | Physical |
|---|---|---:|---:|
| `derive_review` | `mtg_commander_sim/report.py:565` | 1085 | 1089 |
| `parse_declaration_restriction_line` | `mtg_commander_sim/declaration_restrictions.py:892` | 881 | 942 |
| `create_app` | `server/app.py:537` | 724 | 769 |
| `main` | `mtg_commander_sim/cli.py:801` | 594 | 604 |
| `_compile_face` | `mtg_commander_sim/oracle_ir.py:1104` | 527 | 536 |
| `_effect_template` | `mtg_commander_sim/oracle_ir.py:272` | 526 | 527 |
| `build_parser` | `mtg_commander_sim/cli.py:406` | 369 | 393 |
| `CommanderSession.act` | `mtg_commander_sim/session.py:542` | 362 | 366 |
| `CommanderEngine.move_card` | `mtg_commander_sim/engine.py:1593` | 343 | 349 |
| `CommanderEngine._stabilize` | `mtg_commander_sim/engine.py:13742` | 342 | 354 |
| `CommanderEngine._prepare_stack_resolution` | `mtg_commander_sim/engine.py:8445` | 315 | 318 |
| `card_semantic_status` | `mtg_commander_sim/preflight.py:426` | 304 | 304 |
| `CommanderEngine._enter_step` | `mtg_commander_sim/engine.py:3272` | 285 | 319 |
| `CommanderEngine._effective_card_data` | `mtg_commander_sim/engine.py:827` | 274 | 278 |
| `_scripted_choice` | `mtg_commander_sim/cli.py:72` | 266 | 268 |

## Engine responsibility spread

| Responsibility | Matched methods |
|---|---:|
| `turn_priority_decisions` | 39 |
| `casting_activation_and_costs` | 47 |
| `semantics_resolution_and_choices` | 75 |
| `combat_and_damage` | 31 |
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

- Python discovered: 4,611
- Conventional Python cases: 1,311
- Generated CR conformance cases: 3,300
- Playwright journeys: 7
- Browser unit cases: 18
- Dedicated property suite: false
- Mutation score: None
- Focused executable mutation suite: true
- Capability mutation declarations: 33
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
