from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quorune.util import stable_json
from scripts.update_architecture_audit import analyze_production


OUTPUT = ROOT / "platform" / "module-classifications.json"
POLICY = ROOT / "platform" / "architecture-policy.json"
ALLOWED_DEPENDENCIES = {
    "domain": ["domain"],
    "rules": ["domain", "rules", "semantics"],
    "semantics": ["adapter", "domain", "rules", "semantics"],
    "adapter": ["adapter", "application", "domain", "rules", "semantics"],
    "application": [
        "adapter",
        "application",
        "domain",
        "rules",
        "semantics",
    ],
    "transport": [
        "adapter",
        "application",
        "domain",
        "rules",
        "semantics",
        "transport",
    ],
}


def _hash(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def _layer(relative: str, protected_rules_modules: set[str]) -> str:
    if relative.startswith("server/") or relative == "simctl.py":
        return "transport"
    if relative in {
        "quorune/ability_fragments.py",
        "quorune/damage_source.py",
        "quorune/damage_modifier_state.py",
        "quorune/continuous_effect_model.py",
        "quorune/enchant_spec.py",
        "quorune/model.py",
        "quorune/object_predicate.py",
        "quorune/prevention_triggers.py",
        "quorune/replacement/immutable.py",
        "quorune/trigger_batches.py",
    }:
        return "domain"
    if relative in {
        "quorune/python_runtime.py",
        "quorune/util.py",
        "quorune/version.py",
    }:
        return "domain"
    if relative.startswith(
        (
            "quorune/card_programs/",
            "quorune/compiler/",
            "quorune/semantic_runtime/",
            "quorune/semantic_choices/",
            "quorune/effect_runtime/",
            "quorune/reusable_pieces/",
            "quorune/card_overrides/",
        )
    ) or relative in {
        "quorune/carddb_characteristics.py",
        "quorune/effect_contracts.py",
        "quorune/oracle_ir.py",
        "quorune/semantics.py",
        "quorune/ability_fragment_host.py",
        "quorune/compiled_ability_fragments.py",
        "quorune/compiled_activated_abilities.py",
        "quorune/compiled_cast_timing.py",
        "quorune/compiled_cycling_abilities.py",
        "quorune/compiled_mana_abilities.py",
    }:
        return "semantics"
    if relative in {
        "quorune/carddb.py",
        "quorune/deck.py",
        "quorune/moxfield.py",
        "quorune/profiles.py",
    }:
        return "adapter"
    if relative in protected_rules_modules:
        return "rules"
    if relative.startswith(
        (
            "quorune/aura/",
            "quorune/drawing/",
            "quorune/replacement/",
            "quorune/rules/",
        )
    ) or relative in {
        "quorune/abilities.py",
        "quorune/affected_permanents.py",
        "quorune/ability_fragments.py",
        "quorune/attachments.py",
        "quorune/attack_transition_engine_adapter.py",
        "quorune/attack_transition_model.py",
        "quorune/attack_transition_resolution.py",
        "quorune/choice_forms.py",
        "quorune/combat.py",
        "quorune/block_transition_engine_adapter.py",
        "quorune/block_transitions.py",
        "quorune/combat_damage_assignment.py",
        "quorune/combat_damage_engine_adapter.py",
        "quorune/combat_damage_events.py",
        "quorune/combat_damage_projection.py",
        "quorune/combat_damage_sequence.py",
        "quorune/combat_damage_snapshot.py",
        "quorune/combat_damage_trample.py",
        "quorune/combat_damage_values.py",
        "quorune/combat_relationship_state.py",
        "quorune/combat_constraints.py",
        "quorune/combat_evasion.py",
        "quorune/combat_evasion_engine_adapter.py",
        "quorune/commander.py",
        "quorune/cast_timing.py",
        "quorune/continuous_effects.py",
        "quorune/counter_placement.py",
        "quorune/counter_state.py",
        "quorune/damage.py",
        "quorune/damage_prevention.py",
        "quorune/damage_transaction.py",
        "quorune/damage_values.py",
        "quorune/damage_results.py",
        "quorune/deathtouch.py",
        "quorune/defender.py",
        "quorune/declaration_costs.py",
        "quorune/declaration_restrictions.py",
        "quorune/delayed_triggers.py",
        "quorune/destruction.py",
        "quorune/destruction_sets.py",
        "quorune/engine.py",
        "quorune/errors.py",
        "quorune/enchant_spec.py",
        "quorune/life_change.py",
        "quorune/life_state.py",
        "quorune/landwalk.py",
        "quorune/mana.py",
        "quorune/mana_activation.py",
        "quorune/color_set_mana_abilities.py",
        "quorune/fixed_mana_abilities.py",
        "quorune/mana_ability_runtime.py",
        "quorune/mana_source_discovery.py",
        "quorune/mana_undo.py",
        "quorune/mechanic_contracts.py",
        "quorune/menace.py",
        "quorune/permanent_exile.py",
        "quorune/permissions.py",
        "quorune/protection.py",
        "quorune/replacement_decisions.py",
        "quorune/replacement_effects.py",
        "quorune/return_to_hand.py",
        "quorune/rule_conformance.py",
        "quorune/rules_corpus.py",
        "quorune/rules_scheduler.py",
        "quorune/shortcuts.py",
        "quorune/stack_counter.py",
        "quorune/stack_resolution.py",
        "quorune/state_based_actions.py",
        "quorune/state_based_execution.py",
        "quorune/state_planner.py",
        "quorune/tap_state.py",
        "quorune/targets.py",
        "quorune/token_creation.py",
        "quorune/trigger_targeting.py",
        "quorune/trigger_processing.py",
        "quorune/object_query.py",
    }:
        return "rules"
    return "application"


def _owner(relative: str, layer: str) -> str:
    if relative.startswith("server/"):
        return "server_transport"
    if relative.startswith("quorune/semantic_runtime/"):
        return "semantic_runtime"
    if relative.startswith("quorune/semantic_choices/"):
        return "semantic_choices"
    if relative.startswith("quorune/effect_runtime/"):
        return "effect_runtime"
    if relative.startswith("quorune/card_overrides/"):
        return "game_record_compatibility"
    if relative == "quorune/effect_contracts.py":
        return "effect_runtime"
    if relative.startswith("quorune/card_programs/"):
        return "card_programs"
    if relative.startswith("quorune/reusable_pieces/"):
        return "reusable_piece_inventory"
    if relative.startswith("quorune/compiler/"):
        return "oracle_compiler"
    if relative.startswith("quorune/rules/"):
        return "rules_capabilities"
    if relative.startswith("quorune/aura/"):
        return "aura_rules"
    if relative in {
        "quorune/ability_fragment_host.py",
        "quorune/ability_fragments.py",
        "quorune/compiled_ability_fragments.py",
    }:
        return "ability_fragments"
    if relative in {
        "quorune/compiled_activated_abilities.py",
        "quorune/compiled_cycling_abilities.py",
        "quorune/cycling_abilities.py",
    }:
        return "activated_abilities"
    if relative in {
        "quorune/cast_timing.py",
        "quorune/compiled_cast_timing.py",
    }:
        return "cast_timing"
    if relative == "quorune/enchant_spec.py":
        return "aura_rules"
    if relative == "quorune/protection.py":
        return "protection"
    if relative.startswith("quorune/drawing/"):
        return "drawing"
    if relative.startswith("quorune/replacement/"):
        return "replacement_effects"
    if relative == "quorune/commander.py":
        return "commander_variant"
    if relative in {
        "quorune/attack_transition_engine_adapter.py",
        "quorune/attack_transition_model.py",
        "quorune/attack_transition_resolution.py",
        "quorune/block_transition_engine_adapter.py",
        "quorune/block_transitions.py",
    }:
        return "combat_transitions"
    if relative in {
        "quorune/damage_modifier_state.py",
        "quorune/damage_source.py",
        "quorune/prevention_triggers.py",
        "quorune/replacement/immutable.py",
    }:
        return "damage"
    if relative == "quorune/counter_state.py":
        return "counter_state"
    if relative == "quorune/attachments.py":
        return "attachments"
    if relative in {
        "quorune/life_change.py",
        "quorune/life_state.py",
    }:
        return "life_state"
    if relative == "quorune/delayed_triggers.py":
        return "delayed_triggers"
    if relative in {
        "quorune/trigger_batches.py",
        "quorune/trigger_processing.py",
        "quorune/trigger_targeting.py",
    }:
        return "trigger_processing"
    if relative == "quorune/tap_state.py":
        return "tap_state_effects"
    if relative in {
        "quorune/mana.py",
        "quorune/mana_activation.py",
        "quorune/color_set_mana_abilities.py",
        "quorune/fixed_mana_abilities.py",
        "quorune/mana_ability_runtime.py",
        "quorune/mana_source_discovery.py",
        "quorune/compiled_mana_abilities.py",
        "quorune/mana_mode_effects.py",
        "quorune/mana_payment_continuations.py",
        "quorune/mana_undo.py",
        "quorune/semantic_runtime/color_set_mana_abilities.py",
    }:
        return "mana_rules"
    if relative in {
        "quorune/affected_permanents.py",
        "quorune/object_predicate.py",
        "quorune/object_query.py",
    }:
        return "object_query"
    if relative == "quorune/state_planner.py":
        return "state_change_planning"
    if relative == "quorune/counter_placement.py":
        return "counter_placement"
    if relative in {
        "quorune/destruction.py",
        "quorune/destruction_sets.py",
        "quorune/state_based_execution.py",
    }:
        return "destruction"
    if relative in {
        "quorune/damage.py",
        "quorune/damage_prevention.py",
        "quorune/damage_prevention_aftermath.py",
        "quorune/damage_prevention_creation.py",
        "quorune/damage_transaction.py",
        "quorune/damage_values.py",
        "quorune/damage_results.py",
        "quorune/deathtouch.py",
    }:
        return "damage"
    if relative.startswith("quorune/combat_damage_") or relative in {
        "quorune/combat_relationship_state.py",
    }:
        return "combat_damage"
    if relative == "quorune/token_creation.py":
        return "token_creation"
    if relative == "quorune/return_to_hand.py":
        return "return_to_hand"
    if relative == "quorune/permanent_exile.py":
        return "permanent_exile"
    if relative in {
        "quorune/stack_counter.py",
        "quorune/stack_resolution.py",
    }:
        return "stack_counter"
    if relative == "quorune/replacement_decisions.py":
        return "replacement_effects"
    if relative == "quorune/rules_scheduler.py":
        return "rules_governance"
    if relative in {
        "quorune/record.py",
        "quorune/record_trust.py",
    }:
        return "game_record"
    return f"legacy_{layer}"


def build_classifications() -> dict[str, Any]:
    source, _paths, analyses = analyze_production()
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    mutable = set(policy["game_state_access"]["mutable_owners"])
    readers = set(policy["game_state_access"]["read_only_consumers"])
    protected_rules_modules = set(policy["protected_rules_modules"])
    model = policy["game_state_access"]["model_definition"]
    exemptions = tuple(source["scope"]["card_specificity_exempt_prefixes"])
    modules = []
    for relative in sorted(analyses):
        layer = _layer(relative, protected_rules_modules)
        allowed_dependencies = list(ALLOWED_DEPENDENCIES[layer])
        if relative in {
            "quorune/commander.py",
            "quorune/engine.py",
            "quorune/mana.py",
            "quorune/rules_corpus.py",
        } and "adapter" not in allowed_dependencies:
            allowed_dependencies.append("adapter")
            allowed_dependencies.sort()
        access = (
            "mutable_owner"
            if relative in mutable
            else "read_only"
            if relative in readers
            else "model_definition"
            if relative == model
            else "none"
        )
        modules.append(
            {
                "file": relative,
                "layer": layer,
                "owning_subsystem": _owner(relative, layer),
                "allowed_dependency_layers": allowed_dependencies,
                "game_state_access": access,
                "card_specificity_policy": (
                    "explicit_card_override"
                    if any(relative.startswith(prefix) for prefix in exemptions)
                    else "generic_no_growth"
                ),
                "visibility_sensitivity": (
                    "principal_scoped"
                    if any(
                        marker in relative
                        for marker in (
                            "projection",
                            "pilot",
                            "session",
                            "action_explanations",
                            "server/",
                        )
                    )
                    else "authoritative_internal"
                ),
                "replay_participation": (
                    "authoritative"
                    if any(
                        marker in relative
                        for marker in (
                            "attachments.py",
                            "attack_transition",
                            "block_transition",
                            "ability_fragment_host.py",
                            "ability_fragments.py",
                            "aura/",
                            "engine.py",
                            "enchant_spec.py",
                            "session.py",
                            "semantics.py",
                            "card_programs/",
                            "semantic_runtime/",
                            "semantic_choices/",
                            "effect_runtime/",
                            "card_overrides/",
                            "effect_contracts.py",
                            "counter_placement.py",
                            "counter_state.py",
                            "commander.py",
                            "combat_damage_",
                            "combat_relationship_state.py",
                            "damage.py",
                            "damage_modifier_state.py",
                            "damage_prevention",
                            "damage_transaction.py",
                            "damage_results.py",
                            "delayed_triggers.py",
                            "drawing/",
                            "life_change.py",
                            "life_state.py",
                            "mana_activation.py",
                            "mana_mode_effects.py",
                            "mana_payment_continuations.py",
                            "mana_undo.py",
                            "object_predicate.py",
                            "object_query.py",
                            "permanent_exile.py",
                            "replacement/",
                            "return_to_hand.py",
                            "stack_counter.py",
                            "stack_resolution.py",
                            "state_planner.py",
                            "tap_state.py",
                            "token_creation.py",
                            "replacement_decisions.py",
                            "prevention_triggers.py",
                            "protection.py",
                            "compiled_ability_fragments.py",
                            "compiled_activated_abilities.py",
                            "compiled_cycling_abilities.py",
                            "cycling_abilities.py",
                            "compiled_mana_abilities.py",
                            "fixed_mana_abilities.py",
                            "mana_ability_runtime.py",
                            "trigger_targeting.py",
                        )
                    )
                    or relative in {
                        "quorune/record.py",
                        "quorune/record_trust.py",
                    }
                    else "none"
                ),
            }
        )
    payload = {
        "schema_version": 1,
        "classification_policy": "default_deny_exact_production_python_v1",
        "modules": modules,
    }
    payload["fingerprint"] = _hash(payload)
    return payload


def _text(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = _text(build_classifications())
    if args.write:
        OUTPUT.write_text(expected, encoding="utf-8", newline="\n")
        return 0
    actual = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
    if actual != expected:
        print(
            "platform/module-classifications.json is stale; run "
            "python scripts/update_module_classifications.py --write",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
