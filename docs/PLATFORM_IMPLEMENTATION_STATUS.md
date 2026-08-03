---
title: "Platform implementation status"
status: "generated"
authoritative_source: "platform/readiness-source.json"
verified: "9cf0d5625c5ad8f31367a5ae5831e70fbf369bfa672060eacf5558f14fb8fca8"
audience: "maintainers, operators, and contributors"
maintenance: "generated"
---

# Platform implementation status

This is the durable program ledger. It is generated from `platform/readiness-source.json`; generated metrics are read from the repository rather than copied by hand.

## Repository and integration

- Repository: public `MoellerJDev/mtg-commander-sim`
- Default branch: `main`
- Evaluated source tree: `9cf0d5625c5ad8f31367a5ae5831e70fbf369bfa672060eacf5558f14fb8fca8` (`tracked-git-clean-blobs-sha256-v3`)
- Feature checkpoint: `dbe8beb455d186590d66790fe835841fc6c829e7`
- Last certified head: `68ad8b221d3b41ddaf09365fd34d2718c0a73a37`
- Generation timestamp: `2026-08-03T20:50:37Z`
- Runtime Git SHA: resolved dynamically and intentionally not persisted in this tracked report
- Active phase: `None`
- Package version: `0.8.0`

Historical integration chronology belongs in `CHANGELOG.md`; this current report intentionally does not reproduce a pull-request ledger.

## Pinned snapshots and coverage

- Comprehensive Rules: pinned_corpus_on_main
- Oracle: pinned_partial_corpus_coverage (2026-08-02T09:02:31.886+00:00)
- Rulings: pinned_partial_corpus_coverage (2026-08-02T09:00:36.367+00:00)
- Rules manifest present on this branch: yes
- Rules effective date: 2026-06-19
- Rules source SHA-256: e99cd70eb64ca854acb6420ebbf06e369e3f258e0cfba4f03f70bd881386f79b
- Rules cases: blocked=350, definition_only=92, passing=159, total=3300, unreviewed=2699
- Mechanics: status_counts={'partial': 61, 'tested': 1, 'unclassified': 363}, total=425, trusted=0
- Oracle coverage: material_residuals=69371, status_counts={'exact': 3057, 'partial': 16113, 'unresolved': 19315}, total=38485
- Commander-legal Oracle coverage: material_residuals=60748, status_counts={'exact': 417, 'partial': 14692, 'unresolved': 16514}, total=31623
- Current rules/Oracle snapshot complete: no

## Platform milestone status

| Milestone | Status | Evidence |
|---|---|---|
| Integrated deterministic foundation | `complete` | The deterministic foundation, browser/server vertical slice, reviewed combat/rules slices, generated architecture baseline, ratcheted guards, documentation enforcement, fine-grained capability closure, CardProgram V2, the typed-handler boundary, and the first bounded token-replacement and continuous-effect runtime components are integrated on verified main. Registered draw, table-wide draw, and monarch handlers use immutable rules queries, typed intents, canonical stack resolution, and a measured legacy fallback for unmigrated operations. Stridehangar Automaton and Worldwalker Helm token replacement behavior and Stridehangar Automaton's fixed Thopter anthem no longer depend on printed-name engine dispatch. |
| Browser Commander MVP | `development_local_runtime_hardened` | The browser/server line has a strict protocol 3.0 boundary, serialized game actors, SQLite plus Game Record durability, per-tab seat isolation and seven two/four-player Chromium journeys, current generic choice schemas, process-restart recovery, durable lifecycle operations, a responsive local-art UI with hover/focus card inspection, public-zone browsing, resilient card-scoped click/drag actions, saved Auto-mana/Manual mana and Auto-pass/Full control preferences, public tapped-card orientation, explicit active-player main-phase advancement, confirmed concession, public commander-damage tracking, terminal winner/draw rendering, exact command retry, invited read-only spectators, a durable complete public-log dialog, fail-closed handling for legacy arbiter-only records, and one-command managed Scryfall/browser startup. Compact trusted-only coverage includes modal land faces, targeted Sunscorched Desert ETB damage, a stack response, rules-created Treasure payment, Orcish Bowmasters/Amass, explicit attack and block declarations, combat damage, and a natural commander-damage winner. The 49-command natural-winner record replayed to its exact state hash with zero suppressed meaningful windows and a clean seat-projection audit; completed games also survive process restart. The inspected full-database failure remains a pinned pre-fix record, and a fresh post-restart full-database manual journey is still required as broader current-snapshot evidence. Saved board-layout customization, future schemas, full accounts, expiry/rate limits, and production deployment remain open. |
| Typed tap-state effect migration | `integrated_on_certified_main` | Certified main registers tap, untap, and all-creature untap as strict typed semantic operations, commits them through a classified tap-state mutation port, removes their legacy apply_effect branches, preserves stun replacement and effective-type/phasing behavior, and supplies rollback, replay, implementation-mutation, malformed-input, and source-linked evidence. The three capabilities remain tested and blocked rather than trusted because broader prohibitions, replacement ordering, and characteristic closure remain incomplete. |
| Dependency-ordered behavioral rules scheduler | `integrated_on_certified_main` | Certified main conservatively assigns every reviewed blocked behavioral rule and every unclassified nonpassing rule to one dependency-linked subsystem, records implementation/tests/profiles/compiler impact, rejects stale or incomplete catalogs, and selects bounded dependency-ready batches without promoting conformance or runtime trust. |
| Replayable replacement-event and token/zone boundary | `integrated_on_certified_main` | Certified main includes immutable nested replacement events, affected-object and APNAP choice ordering, optional decline, exact selection journals, seat-scoped Game Record v3 continuations, a focused token-creation mutation owner, and reviewed token-addition and zone-destination integrations. CR 616.1g containing-event ordering is behaviorally passing for this substrate; universal CR 614/616 participation and broad Oracle closure remain blocked. |
| Effect-generated counter-placement replacement boundary | `integrated_on_certified_main` | Certified main routes represented effect-generated permanent counters through one prepare/commit owner with fixed integral quantity replacement, affected-controller selection, simultaneous APNAP traversal, rollback, replay, and source-pinned witnesses. Entry counters, player counters, costs, rule actions, and continuation-sensitive legacy producers remain blocked. |
| Typed damage replacement and prevention transaction | `integrated_on_certified_main` | Certified main routes represented combat, semantic, each-opponent, and mana-result damage through one typed proposal/prepare/commit coordinator. Fixed damage quantity replacement and fixed prevention components use affected-player/controller ordering, four-player APNAP traversal, atomic rollback, replayable combat/semantic continuations, and source-pinned Furnace of Rath and Daunting Defender witnesses. |
| Typed atomic damage-result event transaction | `integrated_on_certified_main` | Certified main through PR 67 groups final simultaneous CR 120.3 outcomes by affected subject, applies containing-event replacements before contained life/counter results, validates one mutation-only commit plan, and supports represented Infect, Wither, Lifelink, fixed Toxic, fixed life-gain multiplication, and a whole-result life floor. Prevention, multitype permanents, four-player attribution/APNAP, seat-scoped privacy, exact replay, atomic failure, source hashes, and killed implementation mutants are covered. |
| Damage-result, Commander identity, and replacement hardening | `integrated_on_certified_main` | Certified main through PR 68 attributes Commander combat damage to stable physical commander designations across zone and control changes; preserves explicit historical Game Record v3 behavior; splits the replacement monolith into immutable model, applicability, typed operation, ordering, and strict replay owners; validates nested APNAP choosers; canonicalizes declines; routes represented life and counter damage results through typed precommit owners; enforces nonempty positive, negative, replay, and mutation trust evidence; and generically compiles Infect, Wither, Lifelink, fixed Toxic, closed double-damage wording, and closed fixed-prevention wording. |
| Durable damage prevention and static redirection | `integrated_on_certified_main` | Certified main includes typed finite and next-instance shield state, cleanup expiration, exact simultaneous allocation, unpreventable nonconsumption, aggregate prevention dispatch, immutable commit fingerprints, and typed full-recipient redirection with destination departure and rediscovery. Generic lowering covers fixed shield and static redirection wording without card-name dispatch. Browser regressions keep an active player's empty-stack main phase manual under auto-pass, keep the hand in a fixed resizable bottom dock, and verify projected Urborg/Citadel black mana plus named Cauldron Familiar and The Sackville-Bagginses cast actions. |
| Typed casting, activation, and action offers | `integrated_on_certified_main` | Certified main through PR 72 uses immutable canonical casting and activation proposals for both legal-action advertisement and execution, pins offers to state revisions and proposal fingerprints, rejects stale source/cost/target/payability facts before mutation, and preserves strategic yield signatures across freshness-only revision changes. Dedicated query and commit packages plus the shared action catalog reduce CommanderEngine from 17,197 to 14,788 logical lines, reduce the configured direct-write heuristic from 159 to 144, and reduce oversized functions from 46 to 40. Generic Crew, Craft, granted activated-ability, and static cast-cost descriptors replace represented card-shaped engine branches while Game Record v3 compatibility remains explicit. |
| Damage-prevention continuations and aftermath | `implemented_at_feature_head` | Certified main through PR 77 includes typed source-controller CR 615.5 damage aftermath, immutable damage source/value boundaries, projected modifier preparation, cycle rejection, exact replay, and generic Deflecting Palm lowering. The Oracle IR v20 feature head moves ordinary life replacement discovery into one focused registry, keeps life_state mutation-only, reports final replacement-adjusted life batches, and replaces parallel chosen-source filters with one strict ObjectQuerySpec shared by compiler, choice, snapshot, and damage-time recheck. Historical chosen-source snapshot versions 0 through 2 remain replay-compatible. The August 2 census remains Commander exact/trusted/capability-closed 417/417/415; this ownership consolidation does not inflate card support. CR 615.13 triggered prevention results, explicit-target or mixed aftermath, life-gain prevention, face-down source characteristics, and wider source predicates remain blocked. |
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
- `replay`: `implemented_command_replay_with_additive_card_program_trust_and_exact_runtime_binding_provenance`
- `card_programs`: `implemented_schema_v2_with_explicit_trust_basis_intrinsic_format_match_dynamic_closure_compatibility_provenance_cli_and_replay_pinning`
- `semantic_handlers`: `implemented_six_registered_read_only_typed_intent_handlers_plus_ten_bounded_runtime_components_and_six_closed_effect_runtime_families_with_strict_binding_and_focused_tap_token_counter_damage_damage_result_life_and_player_counter_mutation_ports`
- `capability_evidence`: `implemented_registry_v15_minimum_positive_negative_replay_and_mutation_evidence_with_resolvable_components_current_rules_profile_coverage_and_separate_dependency_status`
- `architecture_governance`: `implemented_default_deny_exact_module_classification_stable_write_identities_zero_engine_growth_oversized_symbol_non_growth_complete_generic_specificity_scope_and_adr_bound_exceptions`
- `continuous_effect_performance`: `implemented_deterministic_uncached_structural_component_collection_baseline_with_observational_latency`
- `hidden_information`: `implemented_projected_protocol`
- `security`: `guest_hash_csrf_origin_capability_and_projection_baseline`
- `ai_dependency`: `none_for_core_tests_or_runtime`

## Deterministic validation

- Tests discovered: 4548
- Python matrix: Python 3.12 on Ubuntu and Windows
- Baseline CI: [30850517667](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30850517667) — `pass`
- Compile: `pass`
- Deterministic tests: `certified_main_through_pr78_exact_head_sharded_public_ubuntu_windows_package_generated_and_browser_pass_plus_post_merge_main_smoke; focused_life_change_damage_result_object_predicate_chosen_source_copy_oracle_cardprogram_architecture_and_capability_shards_pass`
- Deterministic four-player full game: `pass_micro_pool_natural_winner_exact_replay`
- Four-player protocol demo: `pass`
- Repository/history/security audit: `pass`
- Wheel build and clean install: `pass`
- Replay: `pass_for_seed_20260730_native_v3_and_49_command_browser_natural_winner`
- Privacy: `pass_for_principal_projection_command_objects_sanitized_fixtures_and_browser_natural_winner`
- Semantic preflight: `reviewed_compatibility_ready_for_two_pinned_exact_lists; capability_only_strict_match_creation_blocks_on_incomplete_format_capability_inventory`

AI/Codex pilot runs are optional client experiments. They are not product, rules, CI, merge, or release gates.

## Current blockers

- damage replacement/prevention now includes typed finite and next-instance shields, dynamic/divided and independent per-object creation, explicit face-up CR 609.7a source provenance, incarnation-safe permanent-spell continuity, closed property rechecks, simultaneous allocation and same-chooser event ordering, unpreventable nonconsumption, aggregate prevention dispatch, replacement-capable life/permanent-counter/source-controller-damage aftermath, immediate independent life siblings, resumable mana-payment choices, and static full-recipient redirection; CR 615.13 prevention-trigger stack ownership, explicit-target or mixed aftermath, arbitrary opaque provenance, face-down source characteristics, wider property predicates, life-gain prevention, non-effect-runtime life producers, partial/attached redirection, non-damage transformations, remaining result-replacement families, and excess selection remain unimplemented
- typed tap-state capabilities remain tested and blocked on complete tap/untap prohibitions, universal replacement participation beyond represented stun and runtime-component events, and complete effective-characteristic closure
- traditional and Commander format-wide capabilities are not yet inventoried in the fine-grained registry, so capability-only strict match readiness fails closed
- most reviewed semantic-pack abilities remain legacy_reviewed compatibility rather than capability_closed, and many registered capabilities/components remain tested or blocked rather than trusted
- the continuous-effect baseline gates structural scan counts but records latency observationally; broader action, combat, copy, control-change, phasing, and invalidation performance scenarios remain incomplete
- a fresh full-database manual/browser journey created after a clean current-server restart is still required as broader current-snapshot evidence; compact trusted-only browser evidence now covers target/response handling, combat, concession, natural completion, exact replay, and restart persistence
- saved customizable board tabs and denser public-zone dashboard preferences remain incomplete; this is recorded product work, not part of the current architecture audit
- the authoritative engine remains a measured oversized legacy module; casting and activation now use dedicated proposal and commit owners, while turn, effect, choice, and variant responsibilities still require incremental extraction
- future engine choice schemas and complete screen-reader audits remain incomplete
- production accounts, PostgreSQL, multi-process actor ownership, expiry/rate limits, containers, and deployment hardening are incomplete
- full Comprehensive Rules, Commander-legal Oracle, and rulings trust gates remain incomplete

## Exact next task

Implement CR 615.13 prevention-trigger stack ownership and generic lowering as the next dependency-ready rules family after the life-change ownership feature head is integrated.

## Regeneration

```bash
python scripts/update_platform_status.py --write
python scripts/update_platform_status.py --check
```
