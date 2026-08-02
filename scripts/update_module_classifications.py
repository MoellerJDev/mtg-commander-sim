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


def _layer(relative: str) -> str:
    if relative.startswith("server/") or relative == "simctl.py":
        return "transport"
    if relative == "mtg_commander_sim/model.py":
        return "domain"
    if relative in {
        "mtg_commander_sim/util.py",
        "mtg_commander_sim/version.py",
    }:
        return "domain"
    if relative.startswith(
        (
            "mtg_commander_sim/card_programs/",
            "mtg_commander_sim/compiler/",
            "mtg_commander_sim/semantic_runtime/",
        )
    ) or relative in {
        "mtg_commander_sim/oracle_ir.py",
        "mtg_commander_sim/semantics.py",
    }:
        return "semantics"
    if relative in {
        "mtg_commander_sim/carddb.py",
        "mtg_commander_sim/deck.py",
        "mtg_commander_sim/moxfield.py",
        "mtg_commander_sim/profiles.py",
    }:
        return "adapter"
    if relative.startswith("mtg_commander_sim/rules/") or relative in {
        "mtg_commander_sim/abilities.py",
        "mtg_commander_sim/choice_forms.py",
        "mtg_commander_sim/combat.py",
        "mtg_commander_sim/combat_constraints.py",
        "mtg_commander_sim/continuous_effects.py",
        "mtg_commander_sim/damage.py",
        "mtg_commander_sim/declaration_costs.py",
        "mtg_commander_sim/declaration_restrictions.py",
        "mtg_commander_sim/engine.py",
        "mtg_commander_sim/mana.py",
        "mtg_commander_sim/mechanic_contracts.py",
        "mtg_commander_sim/permissions.py",
        "mtg_commander_sim/replacement_effects.py",
        "mtg_commander_sim/rule_conformance.py",
        "mtg_commander_sim/rules_corpus.py",
        "mtg_commander_sim/shortcuts.py",
        "mtg_commander_sim/state_based_actions.py",
        "mtg_commander_sim/tap_state.py",
        "mtg_commander_sim/targets.py",
    }:
        return "rules"
    return "application"


def _owner(relative: str, layer: str) -> str:
    if relative.startswith("server/"):
        return "server_transport"
    if relative.startswith("mtg_commander_sim/semantic_runtime/"):
        return "semantic_runtime"
    if relative.startswith("mtg_commander_sim/card_programs/"):
        return "card_programs"
    if relative.startswith("mtg_commander_sim/compiler/"):
        return "oracle_compiler"
    if relative.startswith("mtg_commander_sim/rules/"):
        return "rules_capabilities"
    if relative == "mtg_commander_sim/tap_state.py":
        return "tap_state_effects"
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
    model = policy["game_state_access"]["model_definition"]
    exemptions = tuple(source["scope"]["card_specificity_exempt_prefixes"])
    modules = []
    for relative in sorted(analyses):
        layer = _layer(relative)
        allowed_dependencies = list(ALLOWED_DEPENDENCIES[layer])
        if relative in {
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
                            "engine.py",
                            "session.py",
                            "semantics.py",
                            "card_programs/",
                            "semantic_runtime/",
                            "tap_state.py",
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
