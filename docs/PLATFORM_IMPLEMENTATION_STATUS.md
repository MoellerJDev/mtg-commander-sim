---
title: "Platform implementation status"
status: "generated"
authoritative_source: "platform/readiness-source.json"
verified: "4a26f0f18ac83f705c22a405acdb1bd3ddb42e9f183e404fcad24be952b422af"
audience: "maintainers, operators, and contributors"
maintenance: "generated"
generated_source: "coverage/platform-readiness.json"
generation_command: ".\.venv\Scripts\python.exe scripts\update_platform_status.py --write"
---

# Platform implementation status

Source fingerprint: `4a26f0f18ac83f705c22a405acdb1bd3ddb42e9f183e404fcad24be952b422af`

## Current top-level state

- Package version: `0.8.0`
- Authoritative kernel: `implemented_partial`
- Server runtime: `implemented_single_process_managed_data_static_browser_restart_terminal_lifecycle_spectator_public_log_and_rules_boundary_recovery`
- Browser client: `implemented_card_inspector_public_zone_browser_resilient_card_scoped_click_drag_saved_manual_auto_mana_saved_auto_pass_full_control_tapped_orientation_explicit_main_phase_current_choice_forms_local_art_combat_concession_commander_damage_terminal_result_exact_retry_spectator_public_log_and_rules_boundary_pause`
- Durable persistence: `implemented_sqlite_control_plane_plus_game_record_v3`
- Exact replay: `implemented_command_replay_with_additive_card_program_trust_and_exact_runtime_binding_provenance`
- Hidden-information projection: `implemented_projected_protocol`
- Core AI dependency: `none_for_core_tests_or_runtime`
- Rules snapshot integrated: yes
- Rules snapshot complete: no

## Top blockers

- ordinary Trample combat-damage assignment now consumes the immutable canonical combat-damage snapshot and typed APNAP assignment sequence with exact current recipients, lethal-before-spill, marked damage, simultaneous attacker, deathtouch, indestructible, protection/prevention, double-strike, and player/planeswalker/Battle boundaries; explicit interaction declarations replace incidental test co-citation, while Trample over planeswalkers, banding assignment control, and unsupported effective-characteristic producers remain blocked
- ordinary Deathtouch now has separate typed positive-assignment and final-damage-result capabilities with immutable source snapshots, one-check marker consumption even when the permanent ceases to be a creature, phases out, or survives because it is Indestructible, canonical rollback, multiplayer replay, and generic CardProgram lowering; regeneration, unsupported ability-changing/copy/face-down characteristic producers, and broader damage-assignment modifiers remain blocked, so the aggregate mechanic is not trusted
- ordinary Defender now has one typed current-characteristic attack restriction shared by advertised candidates and accepted declarations plus generic CardProgram lowering; permissions that allow Defender creatures to attack, put-attacking effects, unsupported ability-changing/copy/face-down producers, and the broader CR 508 restrictions-and-requirements solver remain blocked, so the aggregate mechanic is not trusted
- ordinary Menace now has one typed current-characteristic conditional blocker minimum shared by projected constraints and accepted declarations plus generic CardProgram lowering; additional-block permissions, unsupported ability-changing/copy/face-down producers, and the broader CR 509 restrictions-and-requirements solver remain blocked, so the aggregate mechanic is not trusted
- ordinary Basic Landwalk, Fear, Horsemanship, Intimidate, Shadow, and Skulk now consume one shared typed current-characteristics block-legality boundary, while nonbasic or qualified landwalk, conditional or rules-text-equivalent evasion, unresolved variable power, additional-block permissions, and unsupported characteristic producers remain explicit blockers

Complete platform, validation, milestone, and provenance data is in the [machine-readable platform report](../coverage/platform-readiness.json).

Exact generation command:

```powershell
.\.venv\Scripts\python.exe scripts\update_platform_status.py --write
```
