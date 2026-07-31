# Platform implementation status

This is the durable program ledger. It is generated from `platform/readiness-source.json`; generated metrics are read from the repository rather than copied by hand.

## Repository and integration

- Repository: private `MoellerJDev/mtg-commander-sim`
- Default branch: `main`
- Active branch: `agent/review-mvp`
- Current commit: the commit containing this ledger
- Active phase: `stage_a_integrate_review_mvp`
- Package version: `0.8.0`

### Pull requests

| PR | Head | Base | State |
|---|---|---|---|
| [#2](https://github.com/MoellerJDev/mtg-commander-sim/pull/2) | `agent/review-mvp` | `main` | `draft` |
| [#1](https://github.com/MoellerJDev/mtg-commander-sim/pull/1) | `agent/rules-completeness` | `agent/review-mvp` | `draft_stacked` |

## Pinned snapshots and coverage

- Comprehensive Rules: not_present_until_rules_completeness_integration
- Oracle: pinned_by_card_and_semantic_source_hashes (2026-07-28)
- Rulings: pinned_by_semantic_source_hashes (2026-07-28)
- Rules manifest present on this branch: no
- Rules effective date: not available
- Rules source SHA-256: not available
- Generated rules/mechanics/Oracle metrics: pending integration from `agent/rules-completeness`

## Platform milestone status

| Milestone | Status | Evidence |
|---|---|---|
| Integrated deterministic foundation | `in_progress` | Review MVP is green on its feature branch; rules completeness remains stacked and unmerged. |
| Browser Commander MVP | `not_started` | No server/, web/, or migrations/ subsystem is present on this branch. |
| Active Comprehensive Rules snapshot | `pending_integration` | The versioned rules corpus exists on agent/rules-completeness and is not yet in main. |
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

- Tests discovered: 288
- Python matrix: Python 3.11 and 3.12 on Ubuntu and Windows
- Baseline CI: [30560259007](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30560259007) — `pass`
- Compile: `pass`
- Deterministic tests: `pass`
- Deterministic four-player full game: `pass_micro_pool_natural_winner`
- Four-player protocol demo: `pass`
- Repository/history/security audit: `pass`
- Wheel build and clean install: `pass`
- Replay: `pass_for_seed_20260730_and_native_v3_regressions`
- Privacy: `pass_for_projected_protocol_and_sanitized_fixtures`
- Semantic preflight: `trusted_only_for_two_pinned_exact_lists`

AI/Codex pilot runs are optional client experiments. They are not product, rules, CI, merge, or release gates.

## Current blockers

- agent/review-mvp has not yet been merged into main
- agent/rules-completeness has not yet been rebased by merge from updated main or retargeted to main
- no authoritative ASGI server, single-writer GameActor, durable persistence, or browser client exists
- full Comprehensive Rules, Commander-legal Oracle, and rulings trust gates remain incomplete

## Exact next task

Finish deterministic Stage A evidence, merge PR #2 into main, then merge updated main into agent/rules-completeness and retarget PR #1.

## Regeneration

```bash
python scripts/update_platform_status.py --write
python scripts/update_platform_status.py --check
```
