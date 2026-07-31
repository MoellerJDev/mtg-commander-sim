# Platform implementation status

This is the durable program ledger. It is generated from `platform/readiness-source.json`; generated metrics are read from the repository rather than copied by hand.

## Repository and integration

- Repository: private `MoellerJDev/mtg-commander-sim`
- Default branch: `main`
- Active branch: `agent/cr-508-declare-attackers`
- Current commit: the commit containing this ledger
- Active phase: `rules_family_cr_508_declare_attackers`
- Package version: `0.8.0`

### Pull requests

| PR | Head | Base | State |
|---|---|---|---|
| [#2](https://github.com/MoellerJDev/mtg-commander-sim/pull/2) | `agent/review-mvp` | `main` | `merged` |
| [#1](https://github.com/MoellerJDev/mtg-commander-sim/pull/1) | `agent/rules-completeness` | `main` | `merged` |
| [#3](https://github.com/MoellerJDev/mtg-commander-sim/pull/3) | `agent/cr-512-ending-phase` | `main` | `merged` |
| [#4](https://github.com/MoellerJDev/mtg-commander-sim/pull/4) | `agent/cr-511-end-of-combat` | `main` | `merged` |
| [#5](https://github.com/MoellerJDev/mtg-commander-sim/pull/5) | `agent/cr-510-combat-damage` | `main` | `merged` |
| [#6](https://github.com/MoellerJDev/mtg-commander-sim/pull/6) | `agent/cr-509-declare-blockers` | `main` | `merged` |

## Pinned snapshots and coverage

- Comprehensive Rules: pinned_corpus_on_main
- Oracle: pinned_partial_corpus_coverage (2026-07-28)
- Rulings: pinned_partial_corpus_coverage (2026-07-28)
- Rules manifest present on this branch: yes
- Rules effective date: 2026-06-19
- Rules source SHA-256: e99cd70eb64ca854acb6420ebbf06e369e3f258e0cfba4f03f70bd881386f79b
- Rules cases: blocked=281, definition_only=57, passing=58, total=3300, unreviewed=2904
- Mechanics: status_counts={'partial': 33, 'unclassified': 392}, total=425, trusted=0
- Oracle coverage: material_residuals=69664, status_counts={'exact': 2957, 'partial': 15691, 'unresolved': 19725}, total=38373
- Commander-legal Oracle coverage: material_residuals=61212, status_counts={'exact': 338, 'partial': 14354, 'unresolved': 16930}, total=31622
- Current rules/Oracle snapshot complete: no

## Platform milestone status

| Milestone | Status | Evidence |
|---|---|---|
| Integrated deterministic foundation | `complete` | Both integration PRs and focused CR 512-509 slices merged through ordinary merge commits; main passed the exact-SHA CR 509 matrix. |
| Browser Commander MVP | `not_started` | No server/, web/, or migrations/ subsystem is present on this branch. |
| Active Comprehensive Rules snapshot | `active_on_main` | The versioned 2026-06-19 rules corpus and reviewed CR 509-512 slices are on main; CR 508 is the current focused family. |
| Current Oracle snapshot | `partial` | Two exact 100-card regression lists preflight trusted-only; corpus-wide coverage is not claimed. |

## Runtime and product boundaries

- `authoritative_kernel`: `implemented_partial`
- `transport_neutral_service`: `implemented_in_process`
- `single_writer_game_actor`: `not_implemented`
- `durable_database`: `not_implemented`
- `http_websocket_server`: `not_implemented`
- `browser_client`: `not_implemented`
- `guest_or_account_identity`: `not_implemented`
- `rooms_and_lobbies`: `not_implemented`
- `replay`: `implemented_command_replay`
- `hidden_information`: `implemented_projected_protocol`
- `security`: `repository_and_capability_baseline_only`
- `ai_dependency`: `none_for_core_tests_or_runtime`

## Deterministic validation

- Tests discovered: 3818
- Python matrix: Python 3.11 and 3.12 on Ubuntu and Windows
- Baseline CI: [30609935545](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30609935545) — `pass`
- Compile: `pass`
- Deterministic tests: `pass_3818`
- Deterministic four-player full game: `pass_micro_pool_natural_winner_exact_replay`
- Four-player protocol demo: `pass`
- Repository/history/security audit: `pass`
- Wheel build and clean install: `pass`
- Replay: `pass_for_seed_20260730_and_native_v3_regressions`
- Privacy: `pass_for_projected_protocol_and_sanitized_fixtures`
- Semantic preflight: `trusted_only_for_two_pinned_exact_lists`

AI/Codex pilot runs are optional client experiments. They are not product, rules, CI, merge, or release gates.

## Current blockers

- no authoritative ASGI server, single-writer GameActor, durable persistence, or browser client exists
- full Comprehensive Rules, Commander-legal Oracle, and rulings trust gates remain incomplete

## Exact next task

Finish the CR 508 full gate and publish ordinary attacker declaration without promoting blocked planeswalker, restriction, requirement, cost, trigger, entry-attacking, or reselection families.

## Regeneration

```bash
python scripts/update_platform_status.py --write
python scripts/update_platform_status.py --check
```
