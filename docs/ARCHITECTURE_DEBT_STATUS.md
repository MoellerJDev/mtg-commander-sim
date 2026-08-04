---
title: "Architecture debt status"
status: "generated"
authoritative_source: "coverage/architecture-audit.json"
verified: "b5e5caa77f0420759e4aad2088c14fe73e7bb1f9"
audience: "maintainers and rules contributors"
maintenance: "generated"
---

# Architecture debt status

This generated migration dashboard is anchored to the Phase 0 baseline. It measures the current tree and does not claim architectural completion, rules completeness, or universal card support.

## Baseline coordinates

- Main commit: `b5e5caa77f0420759e4aad2088c14fe73e7bb1f9`
- Package: `0.8.0`
- CI run: [30892105590](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30892105590) — `pass`
- Production scope: 217 files, 97,446 physical lines, 89,547 logical lines

## Central engine debt

- `engine.py`: 14,078 physical / 13,308 logical lines
- Methods: 28 public, 284 private, 1 dunder
- Cross-subsystem responsibility groups: 7
- Direct GameState-write heuristic: 135 locations
- Semantic-operation branches: 154
- Registered typed semantic handlers: 84 across 84 operations
- Registered typed runtime components: 15
- Remaining legacy `apply_effect` branches: 0
- Registered operations still intercepted by engine string dispatch: 0
- Exact printed-name literals in configured core files: 659 (97 conditional)
- Oracle-ID literals in Python production code: 6
- Card-named helpers: 1
- Modules above the 1,500-logical-line review threshold: 6
- Functions/methods above the 150-logical-line review threshold: 37
- Printed-name matching is deliberately over-inclusive: ordinary words that are also printed card names remain baseline candidates for Phase 1 review.

## Enforced debt trend

Baseline: `5029c62c98bdad72549625af9a7c3dde5e333ef9`. Guard: `python scripts/validate_architecture.py --check`.

| Dimension | Baseline | Current | Delta |
|---|---:|---:|---:|
| `engine_logical_lines` | 13,308 | 13,308 | +0 |
| `direct_game_state_writes` | 135 | 135 | +0 |
| `printed_name_literals` | 693 | 659 | -34 |
| `oracle_id_literals` | 6 | 6 | +0 |
| `legacy_card_specific_operations` | 5 | 5 | +0 |
| `card_named_helpers` | 1 | 1 | +0 |
| `oversized_modules` | 6 | 6 | +0 |
| `oversized_functions_and_methods` | 37 | 37 | +0 |

## Largest production modules

| File | Language | Physical | Logical |
|---|---:|---:|---:|
| `mtg_commander_sim/engine.py` | python | 14,078 | 13,308 |
| `web/src/App.tsx` | web | 1,886 | 1,825 |
| `mtg_commander_sim/report.py` | python | 1,853 | 1,813 |
| `mtg_commander_sim/declaration_restrictions.py` | python | 1,833 | 1,679 |
| `mtg_commander_sim/record.py` | python | 1,706 | 1,605 |
| `mtg_commander_sim/oracle_ir.py` | python | 1,589 | 1,541 |
| `mtg_commander_sim/rules_corpus.py` | python | 1,561 | 1,464 |
| `mtg_commander_sim/damage.py` | python | 1,573 | 1,442 |
| `mtg_commander_sim/cli.py` | python | 1,408 | 1,350 |
| `mtg_commander_sim/damage_results.py` | python | 1,308 | 1,202 |
| `server/app.py` | python | 1,305 | 1,171 |
| `mtg_commander_sim/damage_modifier_state.py` | python | 1,241 | 1,160 |
| `mtg_commander_sim/codex_cli.py` | python | 1,214 | 1,154 |
| `mtg_commander_sim/session.py` | python | 1,164 | 1,121 |
| `mtg_commander_sim/effect_runtime/zones_and_attachments.py` | python | 1,123 | 1,060 |

## Largest functions and methods

| Symbol | File:line | Logical | Physical |
|---|---|---:|---:|
| `derive_review` | `mtg_commander_sim/report.py:565` | 1085 | 1089 |
| `parse_declaration_restriction_line` | `mtg_commander_sim/declaration_restrictions.py:892` | 881 | 942 |
| `create_app` | `server/app.py:537` | 724 | 769 |
| `main` | `mtg_commander_sim/cli.py:801` | 594 | 604 |
| `_compile_face` | `mtg_commander_sim/oracle_ir.py:926` | 523 | 532 |
| `_effect_template` | `mtg_commander_sim/oracle_ir.py:121` | 459 | 460 |
| `build_parser` | `mtg_commander_sim/cli.py:406` | 369 | 393 |
| `CommanderSession.act` | `mtg_commander_sim/session.py:543` | 362 | 366 |
| `CommanderEngine.move_card` | `mtg_commander_sim/engine.py:1530` | 343 | 349 |
| `CommanderEngine._stabilize` | `mtg_commander_sim/engine.py:13320` | 342 | 354 |
| `CommanderEngine._prepare_stack_resolution` | `mtg_commander_sim/engine.py:8127` | 315 | 318 |
| `card_semantic_status` | `mtg_commander_sim/preflight.py:426` | 304 | 304 |
| `CommanderEngine._enter_step` | `mtg_commander_sim/engine.py:2954` | 285 | 319 |
| `_scripted_choice` | `mtg_commander_sim/cli.py:72` | 266 | 268 |
| `parse_declaration_cost_line` | `mtg_commander_sim/declaration_costs.py:219` | 249 | 258 |

## Engine responsibility spread

| Responsibility | Matched methods |
|---|---:|
| `turn_priority_decisions` | 39 |
| `casting_activation_and_costs` | 47 |
| `semantics_resolution_and_choices` | 74 |
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

- Python discovered: 4,705
- Conventional Python cases: 1,405
- Generated CR conformance cases: 3,300
- Playwright journeys: 7
- Browser unit cases: 18
- Dedicated property suite: false
- Mutation score: None
- Focused executable mutation suite: true
- Capability mutation declarations: 38
- Performance baseline: `platform/continuous-effect-performance-baseline.json` (5 scenarios; latency observational)

## Documentation drift

- Required: 32
- Present after generated Phase 0 outputs: 32
- Missing: 0
- Metadata complete: 32

The authoritative index, metadata, internal-link, stale-claim, and ADR policies are enforced by `scripts/validate_documentation.py`. Detailed document records remain in `coverage/architecture-audit.json`.

## Regeneration

```bash
python scripts/update_architecture_audit.py --write --card-db data/scryfall-current.sqlite3
python scripts/update_architecture_audit.py --check
```
