# Platform implementation status

This is the durable program ledger. It is generated from `platform/readiness-source.json`; generated metrics are read from the repository rather than copied by hand.

## Repository and integration

- Repository: public `MoellerJDev/mtg-commander-sim`
- Default branch: `main`
- Active branch: `main`
- Current commit: the commit containing this ledger
- Active phase: `rules_combat_dependency_families`
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
| [#10](https://github.com/MoellerJDev/mtg-commander-sim/pull/10) | `agent/cr-505-main-phase` | `main` | `merged` |
| [#11](https://github.com/MoellerJDev/mtg-commander-sim/pull/11) | `agent/cr-504-draw-step` | `main` | `merged` |
| [#12](https://github.com/MoellerJDev/mtg-commander-sim/pull/12) | `agent/cr-503-upkeep-step` | `main` | `merged` |
| [#13](https://github.com/MoellerJDev/mtg-commander-sim/pull/13) | `agent/cr-502-untap-step` | `agent/cr-503-upkeep-step` | `merged` |
| [#14](https://github.com/MoellerJDev/mtg-commander-sim/pull/14) | `agent/cr-501-beginning-phase` | `agent/cr-502-untap-step` | `merged` |
| [#15](https://github.com/MoellerJDev/mtg-commander-sim/pull/15) | `agent/cr-500-turn-structure` | `agent/cr-501-beginning-phase` | `merged` |
| [#16](https://github.com/MoellerJDev/mtg-commander-sim/pull/16) | `agent/cr-405-stack` | `agent/cr-500-turn-structure` | `merged` |
| [#17](https://github.com/MoellerJDev/mtg-commander-sim/pull/17) | `agent/cr-400-general-zone-identity` | `agent/cr-405-stack` | `merged` |
| [#18](https://github.com/MoellerJDev/mtg-commander-sim/pull/18) | `agent/cr-401-library` | `agent/cr-400-general-zone-identity` | `closed_superseded_by_pr_24` |
| [#19](https://github.com/MoellerJDev/mtg-commander-sim/pull/19) | `agent/cr-402-hand` | `agent/cr-401-library` | `closed_superseded_by_pr_24` |
| [#20](https://github.com/MoellerJDev/mtg-commander-sim/pull/20) | `agent/cr-403-battlefield` | `agent/cr-402-hand` | `closed_superseded_by_pr_24` |
| [#21](https://github.com/MoellerJDev/mtg-commander-sim/pull/21) | `agent/cr-404-graveyard` | `agent/cr-403-battlefield` | `closed_superseded_by_pr_24` |
| [#22](https://github.com/MoellerJDev/mtg-commander-sim/pull/22) | `agent/cr-406-exile` | `agent/cr-404-graveyard` | `closed_superseded_by_pr_24` |
| [#23](https://github.com/MoellerJDev/mtg-commander-sim/pull/23) | `agent/cr-407-ante` | `agent/cr-406-exile` | `closed_superseded_by_pr_24` |
| [#24](https://github.com/MoellerJDev/mtg-commander-sim/pull/24) | `agent/cr-408-command` | `main` | `merged` |
| [#25](https://github.com/MoellerJDev/mtg-commander-sim/pull/25) | `agent/integration-checkpoint` | `main` | `merged` |
| [#26](https://github.com/MoellerJDev/mtg-commander-sim/pull/26) | `agent/finalize-integration-docs` | `main` | `merged` |
| [#27](https://github.com/MoellerJDev/mtg-commander-sim/pull/27) | `agent/server-browser-vertical-slice` | `main` | `merged` |
| [#28](https://github.com/MoellerJDev/mtg-commander-sim/pull/28) | `agent/reconcile-platform-docs` | `main` | `merged` |
| [#29](https://github.com/MoellerJDev/mtg-commander-sim/pull/29) | `agent/browser-server-hardening` | `main` | `merged` |
| [#30](https://github.com/MoellerJDev/mtg-commander-sim/pull/30) | `agent/browser-server-operations` | `main` | `merged` |
| [#31](https://github.com/MoellerJDev/mtg-commander-sim/pull/31) | `agent/browser-ui-polish` | `main` | `merged` |
| [#32](https://github.com/MoellerJDev/mtg-commander-sim/pull/32) | `agent/reconcile-browser-handoff` | `main` | `merged` |
| [#33](https://github.com/MoellerJDev/mtg-commander-sim/pull/33) | `agent/spectator-public-log` | `main` | `merged` |
| [#34](https://github.com/MoellerJDev/mtg-commander-sim/pull/34) | `agent/browser-rules-boundary` | `main` | `merged` |
| [#35](https://github.com/MoellerJDev/mtg-commander-sim/pull/35) | `agent/browser-trigger-stabilization` | `main` | `merged` |
| [#36](https://github.com/MoellerJDev/mtg-commander-sim/pull/36) | `agent/browser-lifecycle-journey` | `main` | `merged` |
| [#37](https://github.com/MoellerJDev/mtg-commander-sim/pull/37) | `agent/rules-combat-damage` | `main` | `merged` |
| [#38](https://github.com/MoellerJDev/mtg-commander-sim/pull/38) | `agent/rules-combat-tba-triggers` | `main` | `merged` |
| [#39](https://github.com/MoellerJDev/mtg-commander-sim/pull/39) | `agent/rules-combat-constraints` | `main` | `merged` |
| [#40](https://github.com/MoellerJDev/mtg-commander-sim/pull/40) | `feat/rules-goad-requirements` | `main` | `merged` |
| [#41](https://github.com/MoellerJDev/mtg-commander-sim/pull/41) | `feat/rules-attack-declaration-costs` | `main` | `merged` |
| [#42](https://github.com/MoellerJDev/mtg-commander-sim/pull/42) | `feat/rules-combat-restrictions` | `main` | `merged` |
| [#43](https://github.com/MoellerJDev/mtg-commander-sim/pull/43) | `feat/rules-combat-evasion-restrictions` | `main` | `merged` |

## Pinned snapshots and coverage

- Comprehensive Rules: pinned_corpus_on_main
- Oracle: pinned_partial_corpus_coverage (2026-07-31)
- Rulings: pinned_partial_corpus_coverage (2026-07-31)
- Rules manifest present on this branch: yes
- Rules effective date: 2026-06-19
- Rules source SHA-256: e99cd70eb64ca854acb6420ebbf06e369e3f258e0cfba4f03f70bd881386f79b
- Rules cases: blocked=367, definition_only=81, passing=115, total=3300, unreviewed=2737
- Mechanics: status_counts={'partial': 57, 'unclassified': 368}, total=425, trusted=0
- Oracle coverage: material_residuals=69890, status_counts={'exact': 2959, 'partial': 16027, 'unresolved': 19498}, total=38484
- Commander-legal Oracle coverage: material_residuals=61213, status_counts={'exact': 338, 'partial': 14603, 'unresolved': 16682}, total=31623
- Current rules/Oracle snapshot complete: no

## Platform milestone status

| Milestone | Status | Evidence |
|---|---|---|
| Integrated deterministic foundation | `complete` | Integration PRs #1-17 and #24-43 are on main. PR #24 incorporated every ancestry-proven CR 400-408 head; GitHub auto-recorded PR #17 as merged and PRs #18-23 were closed as superseded only after their exact heads became reachable from main. |
| Browser Commander MVP | `development_local_runtime_hardened` | The browser/server line has a strict protocol 3.0 boundary, serialized game actors, SQLite plus Game Record durability, per-tab seat isolation and seven two/four-player Chromium journeys, current generic choice schemas, process-restart recovery, durable lifecycle operations, a responsive local-art UI with hover/focus card inspection, public-zone browsing, Chromium-verified card-scoped click/drag actions, optional manual mana activation, explicit active-player main-phase advancement, confirmed concession, public commander-damage tracking, terminal winner/draw rendering, exact command retry, invited read-only spectators, a durable complete public-log dialog, fail-closed handling for legacy arbiter-only records, and one-command managed Scryfall/browser startup. Compact trusted-only coverage includes modal land faces, targeted Sunscorched Desert ETB damage, a stack response, rules-created Treasure payment, Orcish Bowmasters/Amass, explicit attack and block declarations, combat damage, and a natural commander-damage winner. The 49-command natural-winner record replayed to its exact state hash with zero suppressed meaningful windows and a clean seat-projection audit; completed games also survive process restart. The inspected full-database failure remains a pinned pre-fix record, and a fresh post-restart full-database manual journey is still required as broader current-snapshot evidence. Future schemas, full accounts, expiry/rate limits, and production deployment remain open. |
| Active Comprehensive Rules snapshot | `active_on_main` | The versioned 2026-06-19 corpus and reviewed CR 400-408 and CR 500-512 slices are on main. Broader rules and Oracle completeness remain explicitly unclaimed. |
| Current Oracle snapshot | `partial` | Two exact 100-card regression lists preflight trusted-only; corpus-wide coverage is not claimed. |

## Runtime and product boundaries

- `authoritative_kernel`: `implemented_partial`
- `transport_neutral_service`: `implemented_strict_protocol_3`
- `single_writer_game_actor`: `implemented_single_process`
- `durable_database`: `implemented_sqlite_control_plane_plus_game_record_v3`
- `http_websocket_server`: `implemented_single_process_managed_data_static_browser_restart_terminal_lifecycle_spectator_public_log_and_rules_boundary_recovery`
- `browser_client`: `implemented_card_inspector_public_zone_browser_card_scoped_click_drag_manual_mana_explicit_main_phase_current_choice_forms_local_art_combat_concession_commander_damage_terminal_result_exact_retry_spectator_public_log_and_rules_boundary_pause`
- `guest_or_account_identity`: `implemented_expiring_per_tab_guest_sessions`
- `rooms_and_lobbies`: `implemented_invite_only_two_or_four_seat_remove_leave_replace_and_watch`
- `replay`: `implemented_command_replay`
- `hidden_information`: `implemented_projected_protocol`
- `security`: `guest_hash_csrf_origin_capability_and_projection_baseline`
- `ai_dependency`: `none_for_core_tests_or_runtime`

## Deterministic validation

- Tests discovered: 4085
- Python matrix: Python 3.11 and 3.12 on Ubuntu and Windows
- Baseline CI: [30694515443](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30694515443) — `pass`
- Compile: `pass`
- Deterministic tests: `pass_full_exact_commit_gate`
- Deterministic four-player full game: `pass_micro_pool_natural_winner_exact_replay`
- Four-player protocol demo: `pass`
- Repository/history/security audit: `pass`
- Wheel build and clean install: `pass`
- Replay: `pass_for_seed_20260730_native_v3_and_49_command_browser_natural_winner`
- Privacy: `pass_for_principal_projection_command_objects_sanitized_fixtures_and_browser_natural_winner`
- Semantic preflight: `trusted_only_for_two_pinned_exact_lists`

AI/Codex pilot runs are optional client experiments. They are not product, rules, CI, merge, or release gates.

## Current blockers

- a fresh full-database manual/browser journey created after a clean current-server restart is still required as broader current-snapshot evidence; compact trusted-only browser evidence now covers target/response handling, combat, concession, natural completion, exact replay, and restart persistence
- future engine choice schemas and complete screen-reader audits remain incomplete
- production accounts, PostgreSQL, multi-process actor ownership, expiry/rate limits, containers, and deployment hardening are incomplete
- full Comprehensive Rules, Commander-legal Oracle, and rulings trust gates remain incomplete

## Exact next task

Extend the shared finite combat declaration solver beyond exact public battlefield conditions and typed goad witnesses to history-, monarch-, poison-, declaration-history-, shared-subtype-, non-goad requirement-, other effect-granted-, optional-cost-, and multi-block grammar, then route declaration triggers through the same boundary; keep the universal CR 120.4 damage transformation pipeline as the next deeper dependency.

## Regeneration

```bash
python scripts/update_platform_status.py --write
python scripts/update_platform_status.py --check
```
