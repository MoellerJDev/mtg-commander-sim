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

from mtg_commander_sim.util import stable_json
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
        "mtg_commander_sim/ability_fragments.py",
        "mtg_commander_sim/damage_source.py",
        "mtg_commander_sim/damage_modifier_state.py",
        "mtg_commander_sim/continuous_effect_model.py",
        "mtg_commander_sim/enchant_spec.py",
        "mtg_commander_sim/model.py",
        "mtg_commander_sim/object_predicate.py",
        "mtg_commander_sim/prevention_triggers.py",
        "mtg_commander_sim/replacement/immutable.py",
        "mtg_commander_sim/trigger_batches.py",
    }:
        return "domain"
    if relative in {
        "mtg_commander_sim/python_runtime.py",
        "mtg_commander_sim/util.py",
        "mtg_commander_sim/version.py",
    }:
        return "domain"
    if relative.startswith(
        (
            "mtg_commander_sim/card_programs/",
            "mtg_commander_sim/compiler/",
            "mtg_commander_sim/semantic_runtime/",
            "mtg_commander_sim/semantic_choices/",
            "mtg_commander_sim/effect_runtime/",
            "mtg_commander_sim/reusable_pieces/",
            "mtg_commander_sim/card_overrides/",
        )
    ) or relative in {
        "mtg_commander_sim/carddb_characteristics.py",
        "mtg_commander_sim/effect_contracts.py",
        "mtg_commander_sim/oracle_ir.py",
        "mtg_commander_sim/semantics.py",
        "mtg_commander_sim/ability_fragment_host.py",
        "mtg_commander_sim/compiled_ability_fragments.py",
        "mtg_commander_sim/compiled_cast_timing.py",
        "mtg_commander_sim/compiled_mana_abilities.py",
    }:
        return "semantics"
    if relative in {
        "mtg_commander_sim/carddb.py",
        "mtg_commander_sim/deck.py",
        "mtg_commander_sim/moxfield.py",
        "mtg_commander_sim/profiles.py",
    }:
        return "adapter"
    if relative in protected_rules_modules:
        return "rules"
    if relative.startswith(
        (
            "mtg_commander_sim/aura/",
            "mtg_commander_sim/drawing/",
            "mtg_commander_sim/replacement/",
            "mtg_commander_sim/rules/",
        )
    ) or relative in {
        "mtg_commander_sim/abilities.py",
        "mtg_commander_sim/ability_fragments.py",
        "mtg_commander_sim/attachments.py",
        "mtg_commander_sim/choice_forms.py",
        "mtg_commander_sim/combat.py",
        "mtg_commander_sim/combat_damage_assignment.py",
        "mtg_commander_sim/combat_damage_engine_adapter.py",
        "mtg_commander_sim/combat_damage_events.py",
        "mtg_commander_sim/combat_damage_projection.py",
        "mtg_commander_sim/combat_damage_sequence.py",
        "mtg_commander_sim/combat_damage_snapshot.py",
        "mtg_commander_sim/combat_damage_trample.py",
        "mtg_commander_sim/combat_damage_values.py",
        "mtg_commander_sim/combat_relationship_state.py",
        "mtg_commander_sim/combat_constraints.py",
        "mtg_commander_sim/combat_evasion.py",
        "mtg_commander_sim/combat_evasion_engine_adapter.py",
        "mtg_commander_sim/commander.py",
        "mtg_commander_sim/cast_timing.py",
        "mtg_commander_sim/continuous_effects.py",
        "mtg_commander_sim/counter_placement.py",
        "mtg_commander_sim/counter_state.py",
        "mtg_commander_sim/damage.py",
        "mtg_commander_sim/damage_prevention.py",
        "mtg_commander_sim/damage_transaction.py",
        "mtg_commander_sim/damage_values.py",
        "mtg_commander_sim/damage_results.py",
        "mtg_commander_sim/deathtouch.py",
        "mtg_commander_sim/defender.py",
        "mtg_commander_sim/declaration_costs.py",
        "mtg_commander_sim/declaration_restrictions.py",
        "mtg_commander_sim/delayed_triggers.py",
        "mtg_commander_sim/engine.py",
        "mtg_commander_sim/errors.py",
        "mtg_commander_sim/enchant_spec.py",
        "mtg_commander_sim/life_change.py",
        "mtg_commander_sim/life_state.py",
        "mtg_commander_sim/landwalk.py",
        "mtg_commander_sim/mana.py",
        "mtg_commander_sim/mana_activation.py",
        "mtg_commander_sim/fixed_mana_abilities.py",
        "mtg_commander_sim/mana_ability_runtime.py",
        "mtg_commander_sim/mana_undo.py",
        "mtg_commander_sim/mechanic_contracts.py",
        "mtg_commander_sim/menace.py",
        "mtg_commander_sim/permissions.py",
        "mtg_commander_sim/protection.py",
        "mtg_commander_sim/replacement_decisions.py",
        "mtg_commander_sim/replacement_effects.py",
        "mtg_commander_sim/rule_conformance.py",
        "mtg_commander_sim/rules_corpus.py",
        "mtg_commander_sim/rules_scheduler.py",
        "mtg_commander_sim/shortcuts.py",
        "mtg_commander_sim/state_based_actions.py",
        "mtg_commander_sim/state_planner.py",
        "mtg_commander_sim/tap_state.py",
        "mtg_commander_sim/targets.py",
        "mtg_commander_sim/token_creation.py",
        "mtg_commander_sim/trigger_targeting.py",
        "mtg_commander_sim/trigger_processing.py",
        "mtg_commander_sim/object_query.py",
    }:
        return "rules"
    return "application"


def _owner(relative: str, layer: str) -> str:
    if relative.startswith("server/"):
        return "server_transport"
    if relative.startswith("mtg_commander_sim/semantic_runtime/"):
        return "semantic_runtime"
    if relative.startswith("mtg_commander_sim/semantic_choices/"):
        return "semantic_choices"
    if relative.startswith("mtg_commander_sim/effect_runtime/"):
        return "effect_runtime"
    if relative.startswith("mtg_commander_sim/card_overrides/"):
        return "game_record_compatibility"
    if relative == "mtg_commander_sim/effect_contracts.py":
        return "effect_runtime"
    if relative.startswith("mtg_commander_sim/card_programs/"):
        return "card_programs"
    if relative.startswith("mtg_commander_sim/reusable_pieces/"):
        return "reusable_piece_inventory"
    if relative.startswith("mtg_commander_sim/compiler/"):
        return "oracle_compiler"
    if relative.startswith("mtg_commander_sim/rules/"):
        return "rules_capabilities"
    if relative.startswith("mtg_commander_sim/aura/"):
        return "aura_rules"
    if relative in {
        "mtg_commander_sim/ability_fragment_host.py",
        "mtg_commander_sim/ability_fragments.py",
        "mtg_commander_sim/compiled_ability_fragments.py",
    }:
        return "ability_fragments"
    if relative in {
        "mtg_commander_sim/cast_timing.py",
        "mtg_commander_sim/compiled_cast_timing.py",
    }:
        return "cast_timing"
    if relative == "mtg_commander_sim/enchant_spec.py":
        return "aura_rules"
    if relative == "mtg_commander_sim/protection.py":
        return "protection"
    if relative.startswith("mtg_commander_sim/drawing/"):
        return "drawing"
    if relative.startswith("mtg_commander_sim/replacement/"):
        return "replacement_effects"
    if relative == "mtg_commander_sim/commander.py":
        return "commander_variant"
    if relative in {
        "mtg_commander_sim/damage_modifier_state.py",
        "mtg_commander_sim/damage_source.py",
        "mtg_commander_sim/prevention_triggers.py",
        "mtg_commander_sim/replacement/immutable.py",
    }:
        return "damage"
    if relative == "mtg_commander_sim/counter_state.py":
        return "counter_state"
    if relative == "mtg_commander_sim/attachments.py":
        return "attachments"
    if relative in {
        "mtg_commander_sim/life_change.py",
        "mtg_commander_sim/life_state.py",
    }:
        return "life_state"
    if relative == "mtg_commander_sim/delayed_triggers.py":
        return "delayed_triggers"
    if relative in {
        "mtg_commander_sim/trigger_batches.py",
        "mtg_commander_sim/trigger_processing.py",
        "mtg_commander_sim/trigger_targeting.py",
    }:
        return "trigger_processing"
    if relative == "mtg_commander_sim/tap_state.py":
        return "tap_state_effects"
    if relative in {
        "mtg_commander_sim/mana.py",
        "mtg_commander_sim/mana_activation.py",
        "mtg_commander_sim/fixed_mana_abilities.py",
        "mtg_commander_sim/mana_ability_runtime.py",
        "mtg_commander_sim/compiled_mana_abilities.py",
        "mtg_commander_sim/mana_mode_effects.py",
        "mtg_commander_sim/mana_payment_continuations.py",
        "mtg_commander_sim/mana_undo.py",
    }:
        return "mana_rules"
    if relative in {
        "mtg_commander_sim/object_predicate.py",
        "mtg_commander_sim/object_query.py",
    }:
        return "object_query"
    if relative == "mtg_commander_sim/state_planner.py":
        return "state_change_planning"
    if relative == "mtg_commander_sim/counter_placement.py":
        return "counter_placement"
    if relative in {
        "mtg_commander_sim/damage.py",
        "mtg_commander_sim/damage_prevention.py",
        "mtg_commander_sim/damage_prevention_aftermath.py",
        "mtg_commander_sim/damage_prevention_creation.py",
        "mtg_commander_sim/damage_transaction.py",
        "mtg_commander_sim/damage_values.py",
        "mtg_commander_sim/damage_results.py",
        "mtg_commander_sim/deathtouch.py",
    }:
        return "damage"
    if relative.startswith("mtg_commander_sim/combat_damage_") or relative in {
        "mtg_commander_sim/combat_relationship_state.py",
    }:
        return "combat_damage"
    if relative == "mtg_commander_sim/token_creation.py":
        return "token_creation"
    if relative == "mtg_commander_sim/replacement_decisions.py":
        return "replacement_effects"
    if relative == "mtg_commander_sim/rules_scheduler.py":
        return "rules_governance"
    if relative in {
        "mtg_commander_sim/record.py",
        "mtg_commander_sim/record_trust.py",
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
            "mtg_commander_sim/commander.py",
            "mtg_commander_sim/engine.py",
            "mtg_commander_sim/mana.py",
            "mtg_commander_sim/rules_corpus.py",
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
                            "replacement/",
                            "state_planner.py",
                            "tap_state.py",
                            "token_creation.py",
                            "replacement_decisions.py",
                            "prevention_triggers.py",
                            "protection.py",
                            "compiled_ability_fragments.py",
                            "compiled_mana_abilities.py",
                            "fixed_mana_abilities.py",
                            "mana_ability_runtime.py",
                            "trigger_targeting.py",
                        )
                    )
                    or relative in {
                        "mtg_commander_sim/record.py",
                        "mtg_commander_sim/record_trust.py",
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
