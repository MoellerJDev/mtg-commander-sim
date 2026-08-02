---
title: "Platform implementation status"
status: "generated"
authoritative_source: "platform/readiness-source.json"
verified: "7cc9ea1702c67519b14d2f177d82dcc8fab5458f"
audience: "maintainers, operators, and contributors"
maintenance: "generated"
---

# Platform implementation status

This is the durable program ledger. It is generated from `platform/readiness-source.json`; generated metrics are read from the repository rather than copied by hand.

## Repository and integration

- Repository: public `MoellerJDev/mtg-commander-sim`
- Default branch: `main`
- Current commit: PR #58 merge commit 7cc9ea1702c67519b14d2f177d82dcc8fab5458f plus the reconciliation commit containing this ledger
- Active phase: `phase_0_post_pr58_reconciliation`
- Package version: `0.8.0`

Historical integration chronology belongs in `CHANGELOG.md`; this current report intentionally does not reproduce a pull-request ledger.

## Pinned snapshots and coverage

- Comprehensive Rules: pinned_corpus_on_main
- Oracle: pinned_partial_corpus_coverage (2026-07-31T21:03:00.228+00:00)
- Rulings: pinned_partial_corpus_coverage (2026-07-31T21:00:39.181+00:00)
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
| Integrated deterministic foundation | `complete` | The deterministic foundation, browser/server vertical slice, reviewed combat/rules slices, generated architecture baseline, ratcheted guards, documentation enforcement, fine-grained capability closure, CardProgram V2, the typed-handler boundary, and the first bounded token-replacement and continuous-effect runtime components are integrated on verified main. Registered draw, table-wide draw, and monarch handlers use immutable rules queries, typed intents, canonical stack resolution, and a measured legacy fallback for unmigrated operations. Stridehangar Automaton and Worldwalker Helm token replacement behavior and Stridehangar Automaton's fixed Thopter anthem no longer depend on printed-name engine dispatch. |
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
- `replay`: `implemented_command_replay_with_additive_card_program_v2_fingerprints`
- `card_programs`: `implemented_schema_v2_generated_and_semantic_pack_adapters_registry_validation_cli_and_replay_pinning`
- `semantic_handlers`: `implemented_registered_read_only_typed_intent_boundary_for_draw_table_draw_and_monarch_plus_versioned_token_replacement_and_continuous_effect_runtime_component_registries_with_legacy_fallback`
- `hidden_information`: `implemented_projected_protocol`
- `security`: `guest_hash_csrf_origin_capability_and_projection_baseline`
- `ai_dependency`: `none_for_core_tests_or_runtime`

## Deterministic validation

- Tests discovered: 4183
- Python matrix: Python 3.11 and 3.12 on Ubuntu and Windows
- Baseline CI: [30723562495](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30723562495) — `pass`
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

- trusted capabilities do not yet require an explicit generated evidence declaration, killed implementation mutation, and separate dependency fail-closed status
- CardProgram trust basis and intrinsic, format, match, and dynamic closure are not yet represented or enforced as separate authoritative concepts
- runtime handler and component execution validates registered capability IDs but is not yet bound to a trusted applicable closure at strict preflight and execution
- the architecture policy does not yet default-deny unclassified production modules, use stable structural mutation identities, cover the complete generic specificity scope, or bind each exception to its exact ADR
- continuous-effect runtime collection has boundary tests but no dedicated deterministic characteristic-query and component-collection performance baseline
- a fresh full-database manual/browser journey created after a clean current-server restart is still required as broader current-snapshot evidence; compact trusted-only browser evidence now covers target/response handling, combat, concession, natural completion, exact replay, and restart persistence
- saved customizable board tabs and denser public-zone dashboard preferences remain incomplete; this is recorded product work, not part of the current architecture audit
- the authoritative engine remains a measured oversized legacy module with interleaved turn, mutation, casting, effect, and variant responsibilities; ratcheted guards prevent new debt while later phases extract it
- future engine choice schemas and complete screen-reader audits remain incomplete
- production accounts, PostgreSQL, multi-process actor ownership, expiry/rate limits, containers, and deployment hardening are incomplete
- full Comprehensive Rules, Commander-legal Oracle, and rulings trust gates remain incomplete

## Exact next task

Create feat/runtime-trust-hardening from reconciled main and implement explicit capability evidence and mutation status, CardProgram trust basis and closure layers, strict handler/component capability binding and compatibility provenance, measured continuous-effect performance, and default-deny architecture governance without adding a new card family.

## Regeneration

```bash
python scripts/update_platform_status.py --write
python scripts/update_platform_status.py --check
```
