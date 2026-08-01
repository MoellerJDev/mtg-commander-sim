from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable, Mapping

try:
    from scripts.architecture_support import (
        decode_card_name_hash_index,
        printed_name_digest,
    )
    from scripts.update_architecture_audit import (
        CARD_BASELINE,
        ROOT,
        _engine_metrics,
        _production_metrics,
        _state_and_dispatch_metrics,
        analyze_production,
    )
except ModuleNotFoundError:  # Direct `python scripts/...` execution.
    from architecture_support import (
        decode_card_name_hash_index,
        printed_name_digest,
    )
    from update_architecture_audit import (
        CARD_BASELINE,
        ROOT,
        _engine_metrics,
        _production_metrics,
        _state_and_dispatch_metrics,
        analyze_production,
    )

from mtg_commander_sim.semantics import VALID_EFFECT_OPERATIONS


POLICY = ROOT / "platform" / "architecture-policy.json"
BASELINE = ROOT / "platform" / "architecture-guard-baseline.json"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _identity(item: Mapping[str, Any], *fields: str) -> tuple[Any, ...]:
    return tuple(item.get(field) for field in fields)


def _counter_extras(
    current: Iterable[tuple[Any, ...]], allowed: Iterable[tuple[Any, ...]]
) -> list[tuple[Any, ...]]:
    remaining = Counter(allowed)
    extras: list[tuple[Any, ...]] = []
    for item in current:
        if remaining[item]:
            remaining[item] -= 1
        else:
            extras.append(item)
    return sorted(extras, key=repr)


def _matches_prefix(value: str, prefixes: Iterable[str]) -> bool:
    return any(value == prefix or value.startswith(prefix + ".") for prefix in prefixes)


def _protected(relative: str, policy: Mapping[str, Any]) -> bool:
    return relative in set(policy["protected_rules_modules"]) or any(
        relative.startswith(prefix) for prefix in policy["protected_future_prefixes"]
    )


def _game_state_imports(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and any(alias.name == "GameState" for alias in node.names)
        for node in ast.walk(tree)
    )


def forbidden_import_violations(
    analyses: Mapping[str, Any], policy: Mapping[str, Any]
) -> list[dict[str, str]]:
    global_forbidden = policy["forbidden_import_prefixes"]

    def forbidden_for(relative: str) -> list[str]:
        result = list(global_forbidden)
        for scope in policy.get("scoped_forbidden_imports", []):
            if relative.startswith(str(scope["path_prefix"])):
                result.extend(scope["import_prefixes"])
        return result

    return sorted(
        (
            {"file": relative, "import": imported}
            for relative, analysis in analyses.items()
            if _protected(relative, policy)
            for imported in analysis.imports
            if _matches_prefix(imported, forbidden_for(relative))
        ),
        key=lambda item: (item["file"], item["import"]),
    )


def mutation_ownership_violations(
    locations: Iterable[Mapping[str, Any]], mutable_owners: Iterable[str]
) -> list[Mapping[str, Any]]:
    owners = set(mutable_owners)
    return [item for item in locations if item["file"] not in owners]


def printed_name_literal_identities(
    analyses: Mapping[str, Any], scope: Iterable[str], digest_index: frozenset[bytes]
) -> list[tuple[Any, ...]]:
    matches = []
    for relative in scope:
        for item in analyses[relative].string_literals:
            if printed_name_digest(str(item["value"])) in digest_index:
                matches.append(
                    _identity(item, "file", "symbol", "value", "in_condition")
                )
    return matches


def _git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
    ).stdout.strip()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_baseline(baseline_commit: str) -> dict[str, Any]:
    source, paths, analyses = analyze_production()
    production = _production_metrics(paths, analyses, source)
    engine = _engine_metrics(analyses, source)
    state = _state_and_dispatch_metrics(analyses, source)
    methods = [
        {
            "name": item["name"],
            "kind": item["kind"],
            "visibility": item["visibility"],
        }
        for item in analyses["mtg_commander_sim/engine.py"].functions
        if item["kind"] == "method"
    ]
    return {
        "schema_version": 1,
        "baseline_commit": baseline_commit,
        "purpose": "Phase 1 non-growth allowances; removals remain allowed.",
        "engine": {
            "physical_lines": engine["physical_lines"],
            "logical_lines": engine["logical_lines"],
            "methods": sorted(methods, key=lambda item: item["name"]),
        },
        "direct_game_state_writes_by_file": dict(
            sorted(
                Counter(
                    item["file"]
                    for item in state["direct_game_state_write_heuristic"][
                        "locations"
                    ]
                ).items()
            )
        ),
        "oracle_id_literals": state["oracle_id_literals"]["locations"],
        "registered_effect_operations": sorted(VALID_EFFECT_OPERATIONS),
        "legacy_card_specific_operations": sorted(
            source["card_specific_semantic_operations"]
        ),
        "card_named_helpers": source["card_named_helpers"],
        "oversized_modules": sorted(
            item["file"] for item in production["oversized_modules"]
        ),
        "oversized_functions_and_methods": sorted(
            {
                f"{item['file']}::{item['symbol']}"
                for item in production["oversized_functions_and_methods"]
            }
        ),
        "source_fingerprints": {
            "printed_name_allowances_sha256": _file_sha256(CARD_BASELINE),
        },
    }


def _failure(guard: str, detail: str, evidence: Any) -> dict[str, Any]:
    return {"guard": guard, "detail": detail, "evidence": evidence}


def _dependency_and_mutation_failures(
    policy: Mapping[str, Any],
    baseline: Mapping[str, Any],
    analyses: Mapping[str, Any],
    state: Mapping[str, Any],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    import_violations = forbidden_import_violations(analyses, policy)
    if import_violations:
        failures.append(
            _failure(
                "forbidden_imports",
                "Rules/domain code imports a transport, application, persistence, or AI layer.",
                import_violations,
            )
        )
    state_policy = policy["game_state_access"]
    allowed_state_access = {
        *state_policy["mutable_owners"],
        *state_policy["read_only_consumers"],
        state_policy["model_definition"],
    }
    access_violations = sorted(
        relative
        for relative, analysis in analyses.items()
        if _game_state_imports(analysis.tree) and relative not in allowed_state_access
    )
    if access_violations:
        failures.append(
            _failure(
                "game_state_access",
                "A module outside the declared owners/readers imports GameState.",
                access_violations,
            )
        )
    state_locations = state["direct_game_state_write_heuristic"]["locations"]
    write_counts = Counter(item["file"] for item in state_locations)
    owner_modules = set(state_policy["mutable_owners"])
    nonowner_writes = mutation_ownership_violations(
        state_locations, owner_modules
    )
    if nonowner_writes:
        failures.append(
            _failure(
                "mutation_ownership",
                "A direct GameState write is outside a declared mutable owner.",
                nonowner_writes,
            )
        )
    write_growth = {
        file: {"baseline": allowed, "current": write_counts[file]}
        for file, allowed in baseline["direct_game_state_writes_by_file"].items()
        if write_counts[file] > int(allowed)
    }
    if write_growth:
        failures.append(
            _failure(
                "mutation_non_growth",
                "Direct GameState write sites grew beyond the Phase 1 baseline.",
                write_growth,
            )
        )
    return failures


def _specificity_failures(
    policy: Mapping[str, Any],
    baseline: Mapping[str, Any],
    source: Mapping[str, Any],
    analyses: Mapping[str, Any],
    state: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    failures: list[dict[str, Any]] = []
    digest_index = decode_card_name_hash_index(
        _load_json(ROOT / str(policy["card_name_hash_index"]))
    )
    current_card_literals = printed_name_literal_identities(
        analyses, policy["specificity_scope"], digest_index
    )
    allowances = _load_json(ROOT / str(policy["printed_name_allowances"]))
    allowed_card_literals = [
        _identity(item, "file", "symbol", "value", "in_condition")
        for item in allowances["exact_printed_name_literals"]
    ]
    new_card_literals = _counter_extras(
        current_card_literals, allowed_card_literals
    )
    if new_card_literals:
        failures.append(
            _failure(
                "printed_card_names",
                "A new exact printed-card-name literal appeared in core code.",
                new_card_literals,
            )
        )
    current_oracle_ids = [
        _identity(
            item,
            "file",
            "symbol",
            "value",
            "oracle_id",
            "in_condition",
        )
        for item in state["oracle_id_literals"]["locations"]
    ]
    allowed_oracle_ids = [
        _identity(
            item,
            "file",
            "symbol",
            "value",
            "oracle_id",
            "in_condition",
        )
        for item in baseline["oracle_id_literals"]
    ]
    new_oracle_ids = _counter_extras(current_oracle_ids, allowed_oracle_ids)
    if new_oracle_ids:
        failures.append(
            _failure(
                "oracle_id_literals",
                "A new Oracle-ID literal appeared in production code.",
                new_oracle_ids,
            )
        )
    current_methods = {
        (item["name"], item["kind"], item["visibility"])
        for item in analyses["mtg_commander_sim/engine.py"].functions
        if item["kind"] == "method"
    }
    baseline_methods = {
        (item["name"], item["kind"], item["visibility"])
        for item in baseline["engine"]["methods"]
    }
    new_methods = sorted(current_methods - baseline_methods)
    if new_methods:
        failures.append(
            _failure(
                "commander_engine_methods",
                "CommanderEngine gained a method instead of extracting responsibility.",
                new_methods,
            )
        )
    new_effect_operations = sorted(
        set(VALID_EFFECT_OPERATIONS) - set(baseline["registered_effect_operations"])
    )
    if new_effect_operations:
        failures.append(
            _failure(
                "semantic_operations",
                "A new universal semantic operation lacks Phase 1 architecture review.",
                new_effect_operations,
            )
        )
    new_card_operations = sorted(
        set(source["card_specific_semantic_operations"])
        - set(baseline["legacy_card_specific_operations"])
    )
    if new_card_operations:
        failures.append(
            _failure(
                "card_named_operations",
                "A new card-specific operation was classified in the universal executor.",
                new_card_operations,
            )
        )
    new_card_helpers = [
        item
        for item in source["card_named_helpers"]
        if item not in baseline["card_named_helpers"]
    ]
    if new_card_helpers:
        failures.append(
            _failure(
                "card_named_helpers",
                "A new card-specific helper was added to the kernel baseline.",
                new_card_helpers,
            )
        )
    fingerprints = baseline["source_fingerprints"]
    current_fingerprint = _file_sha256(CARD_BASELINE)
    if current_fingerprint != fingerprints["printed_name_allowances_sha256"]:
        failures.append(
            _failure(
                "specificity_source_fingerprints",
                "Printed-name allowances changed without refreshing the reviewed guard baseline.",
                {
                    "baseline": fingerprints["printed_name_allowances_sha256"],
                    "current": current_fingerprint,
                },
            )
        )
    return failures, {
        "current_card_literals": len(current_card_literals),
        "allowed_card_literals": len(allowed_card_literals),
        "current_oracle_ids": len(current_oracle_ids),
        "allowed_oracle_ids": len(allowed_oracle_ids),
    }


def _size_debt_failures(
    policy: Mapping[str, Any],
    baseline: Mapping[str, Any],
    production: Mapping[str, Any],
    engine: Mapping[str, Any],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    threshold = policy["review_thresholds"]
    engine_growth = engine["logical_lines"] - int(baseline["engine"]["logical_lines"])
    if engine_growth > int(threshold["engine_net_logical_growth"]):
        failures.append(
            _failure(
                "engine_growth",
                "CommanderEngine exceeded the reviewed net-growth allowance.",
                {"logical_line_delta": engine_growth},
            )
        )
    new_oversized_modules = sorted(
        {item["file"] for item in production["oversized_modules"]}
        - set(baseline["oversized_modules"])
    )
    if new_oversized_modules:
        failures.append(
            _failure(
                "oversized_modules",
                "A new production module exceeds the review threshold without a baseline ADR.",
                new_oversized_modules,
            )
        )
    current_oversized_functions = {
        f"{item['file']}::{item['symbol']}"
        for item in production["oversized_functions_and_methods"]
    }
    new_oversized_functions = sorted(
        current_oversized_functions
        - set(baseline["oversized_functions_and_methods"])
    )
    if new_oversized_functions:
        failures.append(
            _failure(
                "oversized_functions",
                "A new function exceeds the review threshold without a baseline ADR.",
                new_oversized_functions,
            )
        )
    return failures


def _guard_metrics(
    baseline: Mapping[str, Any],
    engine: Mapping[str, Any],
    state: Mapping[str, Any],
    specificity: Mapping[str, int],
) -> dict[str, Any]:
    state_locations = state["direct_game_state_write_heuristic"]["locations"]
    baseline_writes = sum(baseline["direct_game_state_writes_by_file"].values())
    engine_growth = engine["logical_lines"] - int(baseline["engine"]["logical_lines"])
    metrics = {
        "engine_logical_lines": {
            "baseline": baseline["engine"]["logical_lines"],
            "current": engine["logical_lines"],
            "delta": engine_growth,
        },
        "direct_game_state_writes": {
            "baseline": baseline_writes,
            "current": len(state_locations),
            "delta": len(state_locations) - baseline_writes,
        },
        "printed_name_literals": {
            "baseline": specificity["allowed_card_literals"],
            "current": specificity["current_card_literals"],
            "delta": specificity["current_card_literals"]
            - specificity["allowed_card_literals"],
        },
        "oracle_id_literals": {
            "baseline": specificity["allowed_oracle_ids"],
            "current": specificity["current_oracle_ids"],
            "delta": specificity["current_oracle_ids"]
            - specificity["allowed_oracle_ids"],
        },
        "registered_effect_operations": {
            "baseline": len(baseline["registered_effect_operations"]),
            "current": len(VALID_EFFECT_OPERATIONS),
            "delta": len(VALID_EFFECT_OPERATIONS)
            - len(baseline["registered_effect_operations"]),
        },
    }
    return metrics


def evaluate_architecture() -> dict[str, Any]:
    policy = _load_json(POLICY)
    baseline = _load_json(ROOT / str(policy["baseline"]))
    source, paths, analyses = analyze_production()
    production = _production_metrics(paths, analyses, source)
    engine = _engine_metrics(analyses, source)
    state = _state_and_dispatch_metrics(analyses, source)
    failures = _dependency_and_mutation_failures(
        policy, baseline, analyses, state
    )
    specificity_failures, specificity = _specificity_failures(
        policy, baseline, source, analyses, state
    )
    failures.extend(specificity_failures)
    failures.extend(_size_debt_failures(policy, baseline, production, engine))
    return {
        "schema_version": 1,
        "policy_version": policy["policy_version"],
        "baseline_commit": baseline["baseline_commit"],
        "evaluated_commit": _git_head(),
        "status": "pass" if not failures else "fail",
        "metrics": _guard_metrics(baseline, engine, state, specificity),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--initialize-baseline", action="store_true")
    parser.add_argument("--baseline-commit")
    args = parser.parse_args()
    if args.initialize_baseline:
        if BASELINE.exists():
            parser.error(
                "baseline already exists; reviewed updates must be made with an ADR"
            )
        if not args.baseline_commit:
            parser.error("--initialize-baseline requires --baseline-commit")
        value = build_baseline(args.baseline_commit)
        BASELINE.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(json.dumps({"ok": True, "baseline": str(BASELINE)}, indent=2))
        return 0
    if args.baseline_commit:
        parser.error("--baseline-commit is only valid with --initialize-baseline")
    result = evaluate_architecture()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
