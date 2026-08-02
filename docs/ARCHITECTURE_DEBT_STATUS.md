---
title: "Architecture debt status"
status: "generated"
authoritative_source: "coverage/architecture-audit.json"
verified: "6c09dab765e615610f697a7a850bb6502093f0a0"
audience: "maintainers and rules contributors"
maintenance: "generated"
---

# Architecture debt status

This generated migration dashboard is anchored to the Phase 0 baseline. It measures the current tree and does not claim architectural completion, rules completeness, or universal card support.

## Baseline coordinates

- Main commit: `6c09dab765e615610f697a7a850bb6502093f0a0`
- Package: `0.8.0`
- CI run: [30753764851](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30753764851) — `pass`
- Production scope: 148 files, 77,830 physical lines, 72,012 logical lines

## Central engine debt

- `engine.py`: 18,112 physical / 17,265 logical lines
- Methods: 28 public, 296 private, 1 dunder
- Cross-subsystem responsibility groups: 7
- Direct GameState-write heuristic: 159 locations
- Semantic-operation branches: 123
- Registered typed semantic handlers: 81 across 81 operations
- Registered typed runtime components: 9
- Remaining legacy `apply_effect` branches: 0
- Registered operations still intercepted by engine string dispatch: 0
- Exact printed-name literals in configured core files: 707 (106 conditional)
- Oracle-ID literals in Python production code: 7
- Card-named helpers: 1
- Modules above the 1,500-logical-line review threshold: 6
- Functions/methods above the 150-logical-line review threshold: 47
- Printed-name matching is deliberately over-inclusive: ordinary words that are also printed card names remain baseline candidates for Phase 1 review.

## Enforced debt trend

Baseline: `b29cc7ce3b048b94eb6483b10bbbc3e7f9364f16`. Guard: `python scripts/validate_architecture.py --check`.

| Dimension | Baseline | Current | Delta |
|---|---:|---:|---:|
| `engine_logical_lines` | 22,651 | 17,265 | -5,386 |
| `direct_game_state_writes` | 179 | 159 | -20 |
| `printed_name_literals` | 707 | 707 | +0 |
| `oracle_id_literals` | 7 | 7 | +0 |
| `legacy_card_specific_operations` | 6 | 6 | +0 |
| `card_named_helpers` | 1 | 1 | +0 |
| `oversized_modules` | 6 | 6 | +0 |
| `oversized_functions_and_methods` | 52 | 47 | -5 |

## Largest production modules

| File | Language | Physical | Logical |
|---|---:|---:|---:|
| `mtg_commander_sim/engine.py` | python | 18,112 | 17,265 |
| `web/src/App.tsx` | web | 1,880 | 1,819 |
| `mtg_commander_sim/report.py` | python | 1,853 | 1,813 |
| `mtg_commander_sim/oracle_ir.py` | python | 1,760 | 1,694 |
| `mtg_commander_sim/declaration_restrictions.py` | python | 1,833 | 1,679 |
| `mtg_commander_sim/record.py` | python | 1,706 | 1,605 |
| `mtg_commander_sim/rules_corpus.py` | python | 1,561 | 1,464 |
| `mtg_commander_sim/cli.py` | python | 1,408 | 1,350 |
| `mtg_commander_sim/damage_results.py` | python | 1,308 | 1,202 |
| `server/app.py` | python | 1,304 | 1,171 |
| `mtg_commander_sim/codex_cli.py` | python | 1,214 | 1,154 |
| `mtg_commander_sim/damage.py` | python | 1,267 | 1,145 |
| `mtg_commander_sim/session.py` | python | 1,146 | 1,103 |
| `mtg_commander_sim/arena.py` | python | 1,106 | 1,033 |
| `mtg_commander_sim/effect_runtime/zones_and_attachments.py` | python | 1,045 | 982 |

## Largest functions and methods

| Symbol | File:line | Logical | Physical |
|---|---|---:|---:|
| `derive_review` | `mtg_commander_sim/report.py:565` | 1085 | 1089 |
| `parse_declaration_restriction_line` | `mtg_commander_sim/declaration_restrictions.py:892` | 881 | 942 |
| `create_app` | `server/app.py:536` | 724 | 769 |
| `CommanderEngine._cast` | `mtg_commander_sim/engine.py:6126` | 622 | 625 |
| `_compile_face` | `mtg_commander_sim/oracle_ir.py:1023` | 603 | 612 |
| `main` | `mtg_commander_sim/cli.py:801` | 594 | 604 |
| `CommanderEngine._priority_action_hints` | `mtg_commander_sim/engine.py:9246` | 577 | 579 |
| `_effect_template` | `mtg_commander_sim/oracle_ir.py:332` | 526 | 527 |
| `CommanderEngine._cast_cost_options` | `mtg_commander_sim/engine.py:8821` | 418 | 424 |
| `build_parser` | `mtg_commander_sim/cli.py:406` | 369 | 393 |
| `CommanderSession.act` | `mtg_commander_sim/session.py:537` | 362 | 366 |
| `CommanderEngine.move_card` | `mtg_commander_sim/engine.py:1894` | 343 | 349 |
| `CommanderEngine._stabilize` | `mtg_commander_sim/engine.py:17395` | 342 | 354 |
| `CommanderEngine._activate` | `mtg_commander_sim/engine.py:7362` | 339 | 347 |
| `CommanderEngine._prepare_stack_resolution` | `mtg_commander_sim/engine.py:12012` | 333 | 336 |

## Engine responsibility spread

| Responsibility | Matched methods |
|---|---:|
| `turn_priority_decisions` | 39 |
| `casting_activation_and_costs` | 52 |
| `semantics_resolution_and_choices` | 80 |
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

These are review classifications from the machine-readable source, not automatic proof that an extraction boundary is correct.

## Test classes

- Python discovered: 4,378
- Conventional Python cases: 1,078
- Generated CR conformance cases: 3,300
- Playwright journeys: 7
- Browser unit cases: 14
- Dedicated property suite: false
- Mutation score: None
- Focused executable mutation suite: true
- Capability mutation declarations: 21
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
