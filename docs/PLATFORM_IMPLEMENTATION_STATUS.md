---
title: "Platform implementation status"
status: "generated"
authoritative_source: "platform/readiness-source.json"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "maintainers, operators, and contributors"
maintenance: "generated"
---

# Platform implementation status

This is the durable program ledger. It is generated from `platform/readiness-source.json`; generated metrics are read from the repository rather than copied by hand.

## Repository and integration

- Repository: public `MoellerJDev/mtg-commander-sim`
- Default branch: `main`
- Current commit: the commit containing this ledger
- Active phase: `phase_1_documentation_enforcement`
- Package version: `0.8.0`

Historical integration chronology belongs in `CHANGELOG.md`; this current report intentionally does not reproduce a pull-request ledger.

## Pinned snapshots and coverage

- Comprehensive Rules: pinned_corpus_on_main
- Oracle: pinned_partial_corpus_coverage (2026-07-31)
- Rulings: pinned_partial_corpus_coverage (2026-07-31)
- Rules manifest present on this branch: yes
- Rules effective date: 2026-06-19
- Rules source SHA-256: e99cd70eb64ca854acb6420ebbf06e369e3f258e0cfba4f03f70bd881386f79b
- Rules cases: blocked=362, definition_only=82, passing=125, total=3300, unreviewed=2731
- Mechanics: status_counts={'partial': 58, 'unclassified': 367}, total=425, trusted=0
- Oracle coverage: material_residuals=69890, status_counts={'exact': 2959, 'partial': 16092, 'unresolved': 19433}, total=38484
- Commander-legal Oracle coverage: material_residuals=61213, status_counts={'exact': 338, 'partial': 14663, 'unresolved': 16622}, total=31623
- Current rules/Oracle snapshot complete: no

## Platform milestone status

| Milestone | Status | Evidence |
|---|---|---|
| Integrated deterministic foundation | `complete` | The deterministic foundation, browser/server vertical slice, reviewed combat/rules slices, generated architecture baseline, and ratcheted dependency, mutation, specificity, and maintainability guards are integrated on verified main. The active documentation slice establishes authoritative current/target separation, ADR governance, link validation, and generated-only numerical status. |
| Browser Commander MVP | `development_local_runtime_hardened` | The browser/server line has a strict protocol 3.0 boundary, serialized game actors, SQLite plus Game Record durability, per-tab seat isolation and seven two/four-player Chromium journeys, current generic choice schemas, process-restart recovery, durable lifecycle operations, a responsive local-art UI with hover/focus card inspection, public-zone browsing, resilient card-scoped click/drag actions, saved Auto-mana/Manual mana and Auto-pass/Full control preferences, public tapped-card orientation, explicit active-player main-phase advancement, confirmed concession, public commander-damage tracking, terminal winner/draw rendering, exact command retry, invited read-only spectators, a durable complete public-log dialog, fail-closed handling for legacy arbiter-only records, and one-command managed Scryfall/browser startup. Compact trusted-only coverage includes modal land faces, targeted Sunscorched Desert ETB damage, a stack response, rules-created Treasure payment, Orcish Bowmasters/Amass, explicit attack and block declarations, combat damage, and a natural commander-damage winner. The 49-command natural-winner record replayed to its exact state hash with zero suppressed meaningful windows and a clean seat-projection audit; completed games also survive process restart. The inspected full-database failure remains a pinned pre-fix record, and a fresh post-restart full-database manual journey is still required as broader current-snapshot evidence. Saved board-layout customization, future schemas, full accounts, expiry/rate limits, and production deployment remain open. |
| Active Comprehensive Rules snapshot | `active_on_main` | The versioned 2026-06-19 corpus and reviewed CR 400-408, CR 500-514, focused CR 725, and focused CR 508-509/608 current-turn history slices are represented. Broader rules and Oracle completeness remain explicitly unclaimed. |
| Current Oracle snapshot | `partial` | Two exact 100-card regression lists preflight trusted-only; corpus-wide coverage is not claimed. |

## Runtime and product boundaries

- `authoritative_kernel`: `implemented_partial`
- `transport_neutral_service`: `implemented_strict_protocol_3`
- `single_writer_game_actor`: `implemented_single_process`
- `durable_database`: `implemented_sqlite_control_plane_plus_game_record_v3`
- `http_websocket_server`: `implemented_single_process_managed_data_static_browser_restart_terminal_lifecycle_spectator_public_log_and_rules_boundary_recovery`
- `browser_client`: `implemented_card_inspector_public_zone_browser_resilient_card_scoped_click_drag_saved_manual_auto_mana_saved_auto_pass_full_control_tapped_orientation_explicit_main_phase_current_choice_forms_local_art_combat_concession_commander_damage_terminal_result_exact_retry_spectator_public_log_and_rules_boundary_pause`
- `guest_or_account_identity`: `implemented_expiring_per_tab_guest_sessions`
- `rooms_and_lobbies`: `implemented_invite_only_two_or_four_seat_remove_leave_replace_and_watch`
- `replay`: `implemented_command_replay`
- `hidden_information`: `implemented_projected_protocol`
- `security`: `guest_hash_csrf_origin_capability_and_projection_baseline`
- `ai_dependency`: `none_for_core_tests_or_runtime`

## Deterministic validation

- Tests discovered: 4141
- Python matrix: Python 3.11 and 3.12 on Ubuntu and Windows
- Baseline CI: [30708805772](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30708805772) — `pass`
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
- saved customizable board tabs and denser public-zone dashboard preferences remain incomplete; this is recorded product work, not part of the current architecture audit
- the authoritative engine remains a measured oversized legacy module with interleaved turn, mutation, casting, effect, and variant responsibilities; ratcheted guards prevent new debt while later phases extract it
- future engine choice schemas and complete screen-reader audits remain incomplete
- production accounts, PostgreSQL, multi-process actor ownership, expiry/rate limits, containers, and deployment hardening are incomplete
- full Comprehensive Rules, Commander-legal Oracle, and rulings trust gates remain incomplete

## Exact next task

Merge the focused Phase 1 documentation enforcement slice; then begin Phase 2 with a versioned fine-grained capability schema and one representative compiler/runtime trust migration on a fresh branch.

## Regeneration

```bash
python scripts/update_platform_status.py --write
python scripts/update_platform_status.py --check
```
