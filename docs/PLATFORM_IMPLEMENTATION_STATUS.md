# Platform implementation status

This is the durable program ledger. It is generated from `platform/readiness-source.json`; generated metrics are read from the repository rather than copied by hand.

## Repository and integration

- Repository: public `MoellerJDev/mtg-commander-sim`
- Default branch: `main`
- Active branch: `agent/cr-408-command`
- Current commit: the commit containing this ledger
- Active phase: `integrate_rules_backlog_then_server_browser_vertical_slice`
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
| [#7](https://github.com/MoellerJDev/mtg-commander-sim/pull/7) | `agent/cr-508-declare-attackers` | `main` | `merged` |
| [#8](https://github.com/MoellerJDev/mtg-commander-sim/pull/8) | `agent/cr-507-beginning-combat` | `main` | `merged` |
| [#9](https://github.com/MoellerJDev/mtg-commander-sim/pull/9) | `agent/cr-506-combat-phase` | `main` | `merged` |
| [#10](https://github.com/MoellerJDev/mtg-commander-sim/pull/10) | `agent/cr-505-main-phase` | `main` | `draft` |
| [#11](https://github.com/MoellerJDev/mtg-commander-sim/pull/11) | `agent/cr-504-draw-step` | `main` | `draft` |
| [#12](https://github.com/MoellerJDev/mtg-commander-sim/pull/12) | `agent/cr-503-upkeep-step` | `main` | `draft` |
| [#13](https://github.com/MoellerJDev/mtg-commander-sim/pull/13) | `agent/cr-502-untap-step` | `agent/cr-503-upkeep-step` | `draft` |
| [#14](https://github.com/MoellerJDev/mtg-commander-sim/pull/14) | `agent/cr-501-beginning-phase` | `agent/cr-502-untap-step` | `draft` |
| [#15](https://github.com/MoellerJDev/mtg-commander-sim/pull/15) | `agent/cr-500-turn-structure` | `agent/cr-501-beginning-phase` | `draft` |
| [#16](https://github.com/MoellerJDev/mtg-commander-sim/pull/16) | `agent/cr-405-stack` | `agent/cr-500-turn-structure` | `draft` |
| [#17](https://github.com/MoellerJDev/mtg-commander-sim/pull/17) | `agent/cr-400-general-zone-identity` | `agent/cr-405-stack` | `draft` |
| [#18](https://github.com/MoellerJDev/mtg-commander-sim/pull/18) | `agent/cr-401-library` | `agent/cr-400-general-zone-identity` | `draft` |
| [#19](https://github.com/MoellerJDev/mtg-commander-sim/pull/19) | `agent/cr-402-hand` | `agent/cr-401-library` | `draft` |
| [#20](https://github.com/MoellerJDev/mtg-commander-sim/pull/20) | `agent/cr-403-battlefield` | `agent/cr-402-hand` | `draft` |
| [#21](https://github.com/MoellerJDev/mtg-commander-sim/pull/21) | `agent/cr-404-graveyard` | `agent/cr-403-battlefield` | `draft` |
| [#22](https://github.com/MoellerJDev/mtg-commander-sim/pull/22) | `agent/cr-406-exile` | `agent/cr-404-graveyard` | `draft` |
| [#23](https://github.com/MoellerJDev/mtg-commander-sim/pull/23) | `agent/cr-407-ante` | `agent/cr-406-exile` | `draft` |
| [#24](https://github.com/MoellerJDev/mtg-commander-sim/pull/24) | `agent/cr-408-command` | `agent/cr-407-ante` | `draft` |

## Pinned snapshots and coverage

- Comprehensive Rules: pinned_corpus_on_main
- Oracle: pinned_partial_corpus_coverage (2026-07-28)
- Rulings: pinned_partial_corpus_coverage (2026-07-28)
- Rules manifest present on this branch: yes
- Rules effective date: 2026-06-19
- Rules source SHA-256: e99cd70eb64ca854acb6420ebbf06e369e3f258e0cfba4f03f70bd881386f79b
- Rules cases: blocked=365, definition_only=78, passing=100, total=3300, unreviewed=2757
- Mechanics: status_counts={'partial': 47, 'unclassified': 378}, total=425, trusted=0
- Oracle coverage: material_residuals=69664, status_counts={'exact': 2957, 'partial': 15691, 'unresolved': 19725}, total=38373
- Commander-legal Oracle coverage: material_residuals=61212, status_counts={'exact': 338, 'partial': 14354, 'unresolved': 16930}, total=31622
- Current rules/Oracle snapshot complete: no

## Platform milestone status

| Milestone | Status | Evidence |
|---|---|---|
| Integrated deterministic foundation | `integration_checkpoint` | Integration PRs #1-2 and CR 506-512 PRs #3-9 are on main. Completed CR 400-408 and CR 500-505 work remains in draft PRs #10-24 and is frozen pending ordered integration. |
| Browser Commander MVP | `not_started` | No server/, web/, or migrations/ subsystem is present on this branch. |
| Active Comprehensive Rules snapshot | `active_with_integration_backlog` | The 2026-06-19 corpus and CR 506-512 reviews are on main. The current CR 408 tip reports 543 reviewed records; independent CR 504/505 and the CR 503-to-408 chain will be merged in dependency order before server/browser work. |
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

- Tests discovered: 3911
- Python matrix: Python 3.11 and 3.12 on Ubuntu and Windows
- Baseline CI: [30633146886](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30633146886) — `pass`
- Compile: `pass`
- Deterministic tests: `pass_3908`
- Deterministic four-player full game: `pass_micro_pool_natural_winner_exact_replay`
- Four-player protocol demo: `pass`
- Repository/history/security audit: `pass`
- Wheel build and clean install: `pass`
- Replay: `pass_for_seed_20260730_and_native_v3_regressions`
- Privacy: `pass_for_principal_projection_command_objects_and_sanitized_fixtures`
- Semantic preflight: `trusted_only_for_two_pinned_exact_lists`

AI/Codex pilot runs are optional client experiments. They are not product, rules, CI, merge, or release gates.

## Current blockers

- no authoritative ASGI server, single-writer GameActor, durable persistence, or browser client exists
- full Comprehensive Rules, Commander-legal Oracle, and rulings trust gates remain incomplete
- completed rule-family work is distributed across draft PRs 10-24 and must be integrated before the platform pivot

## Exact next task

Freeze rule-family expansion at CR 408, run the reproducible merge gate, integrate PRs 11, 10, and 12-24 into main with ordinary green CI, then begin the single server/browser vertical-slice branch.

## Regeneration

```bash
python scripts/update_platform_status.py --write
python scripts/update_platform_status.py --check
```
