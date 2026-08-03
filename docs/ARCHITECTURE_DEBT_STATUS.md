---
title: "Architecture debt status"
status: "generated"
authoritative_source: "coverage/architecture-audit.json"
verified: "7d45ca8ffd4aa6ec611b0f0f1220025c6ecc3cab"
audience: "maintainers and rules contributors"
maintenance: "generated"
---

# Architecture debt status

This generated migration dashboard is anchored to the Phase 0 baseline. It measures the current tree and does not claim architectural completion, rules completeness, or universal card support.

## Baseline coordinates

- Main commit: `7d45ca8ffd4aa6ec611b0f0f1220025c6ecc3cab`
- Package: `0.8.0`
- CI run: [30770356732](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30770356732) — `pass`
- Production scope: 153 files, 80,084 physical lines, 74,107 logical lines

## Central engine debt

- `engine.py`: 18,042 physical / 17,197 logical lines
- Methods: 28 public, 296 private, 1 dunder
- Cross-subsystem responsibility groups: 7
- Direct GameState-write heuristic: 159 locations
- Semantic-operation branches: 130
- Registered typed semantic handlers: 83 across 83 operations
- Registered typed runtime components: 10
- Remaining legacy `apply_effect` branches: 0
- Registered operations still intercepted by engine string dispatch: 0
- Exact printed-name literals in configured core files: 707 (106 conditional)
- Oracle-ID literals in Python production code: 7
- Card-named helpers: 1
- Modules above the 1,500-logical-line review threshold: 6
- Functions/methods above the 150-logical-line review threshold: 46
- Printed-name matching is deliberately over-inclusive: ordinary words that are also printed card names remain baseline candidates for Phase 1 review.

## Enforced debt trend

Baseline: `7d45ca8ffd4aa6ec611b0f0f1220025c6ecc3cab`. Guard: `python scripts/validate_architecture.py --check`.

| Dimension | Baseline | Current | Delta |
|---|---:|---:|---:|
| `engine_logical_lines` | 17,197 | 17,197 | +0 |
| `direct_game_state_writes` | 159 | 159 | +0 |
| `printed_name_literals` | 707 | 707 | +0 |
| `oracle_id_literals` | 7 | 7 | +0 |
| `legacy_card_specific_operations` | 6 | 6 | +0 |
| `card_named_helpers` | 1 | 1 | +0 |
| `oversized_modules` | 6 | 6 | +0 |
| `oversized_functions_and_methods` | 46 | 46 | +0 |

## Largest production modules

| File | Language | Physical | Logical |
|---|---:|---:|---:|
| `mtg_commander_sim/engine.py` | python | 18,042 | 17,197 |
| `web/src/App.tsx` | web | 1,886 | 1,825 |
| `mtg_commander_sim/report.py` | python | 1,853 | 1,813 |
| `mtg_commander_sim/oracle_ir.py` | python | 1,781 | 1,713 |
| `mtg_commander_sim/declaration_restrictions.py` | python | 1,833 | 1,679 |
| `mtg_commander_sim/record.py` | python | 1,706 | 1,605 |
| `mtg_commander_sim/rules_corpus.py` | python | 1,561 | 1,464 |
| `mtg_commander_sim/cli.py` | python | 1,408 | 1,350 |
| `mtg_commander_sim/damage.py` | python | 1,455 | 1,318 |
| `mtg_commander_sim/damage_results.py` | python | 1,308 | 1,202 |
| `server/app.py` | python | 1,304 | 1,171 |
| `mtg_commander_sim/codex_cli.py` | python | 1,214 | 1,154 |
| `mtg_commander_sim/session.py` | python | 1,146 | 1,103 |
| `mtg_commander_sim/arena.py` | python | 1,106 | 1,033 |
| `mtg_commander_sim/effect_runtime/damage_life_and_turns.py` | python | 1,109 | 1,022 |

## Largest functions and methods

| Symbol | File:line | Logical | Physical |
|---|---|---:|---:|
| `derive_review` | `mtg_commander_sim/report.py:565` | 1085 | 1089 |
| `parse_declaration_restriction_line` | `mtg_commander_sim/declaration_restrictions.py:892` | 881 | 942 |
| `create_app` | `server/app.py:536` | 724 | 769 |
| `CommanderEngine._cast` | `mtg_commander_sim/engine.py:6128` | 622 | 625 |
| `_compile_face` | `mtg_commander_sim/oracle_ir.py:1038` | 609 | 618 |
| `main` | `mtg_commander_sim/cli.py:801` | 594 | 604 |
| `CommanderEngine._priority_action_hints` | `mtg_commander_sim/engine.py:9248` | 577 | 579 |
| `_effect_template` | `mtg_commander_sim/oracle_ir.py:333` | 526 | 527 |
| `CommanderEngine._cast_cost_options` | `mtg_commander_sim/engine.py:8823` | 418 | 424 |
| `build_parser` | `mtg_commander_sim/cli.py:406` | 369 | 393 |
| `CommanderSession.act` | `mtg_commander_sim/session.py:537` | 362 | 366 |
| `CommanderEngine.move_card` | `mtg_commander_sim/engine.py:1895` | 343 | 349 |
| `CommanderEngine._stabilize` | `mtg_commander_sim/engine.py:17325` | 342 | 354 |
| `CommanderEngine._activate` | `mtg_commander_sim/engine.py:7364` | 339 | 347 |
| `CommanderEngine._prepare_stack_resolution` | `mtg_commander_sim/engine.py:12014` | 333 | 336 |

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

- Python discovered: 4,406
- Conventional Python cases: 1,106
- Generated CR conformance cases: 3,300
- Playwright journeys: 7
- Browser unit cases: 18
- Dedicated property suite: false
- Mutation score: None
- Focused executable mutation suite: true
- Capability mutation declarations: 23
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
