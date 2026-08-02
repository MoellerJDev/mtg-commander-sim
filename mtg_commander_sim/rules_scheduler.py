from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from .util import stable_json


RULES_SCHEDULER_SCHEMA_VERSION = 1
_RULE_KEY = re.compile(r"^(?P<number>\d+)(?P<suffix>[a-z]*)$")


class RulesSchedulerError(ValueError):
    pass


def _hash(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RulesSchedulerError(f"Missing rules scheduler input: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RulesSchedulerError(
            f"Rules scheduler input must be an object: {path}"
        )
    return value


def _natural_rule_key(rule_id: str) -> tuple[tuple[int, str], ...]:
    parts = []
    for component in str(rule_id).split("."):
        match = _RULE_KEY.fullmatch(component)
        if match is None:
            raise RulesSchedulerError(f"Invalid rule id {rule_id!r}")
        parts.append(
            (
                int(match.group("number")),
                str(match.group("suffix") or ""),
            )
        )
    return tuple(parts)


def _ordered_unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _topological_subsystems(
    subsystems: Sequence[Mapping[str, Any]],
) -> list[str]:
    by_id = {str(row.get("id") or ""): row for row in subsystems}
    if "" in by_id or len(by_id) != len(subsystems):
        raise RulesSchedulerError(
            "Subsystem ids must be present and unique"
        )
    dependencies: dict[str, set[str]] = {}
    dependents: dict[str, set[str]] = defaultdict(set)
    for subsystem_id, row in by_id.items():
        declared = {
            str(value) for value in row.get("depends_on", [])
        }
        unknown = declared - set(by_id)
        if unknown:
            raise RulesSchedulerError(
                f"Subsystem {subsystem_id} has unknown dependencies: "
                f"{sorted(unknown)}"
            )
        if subsystem_id in declared:
            raise RulesSchedulerError(
                f"Subsystem {subsystem_id} depends on itself"
            )
        dependencies[subsystem_id] = declared
        for dependency in declared:
            dependents[dependency].add(subsystem_id)

    def order_key(subsystem_id: str) -> tuple[int, str]:
        return (
            int(by_id[subsystem_id].get("order") or 0),
            subsystem_id,
        )

    ready = sorted(
        (
            subsystem_id
            for subsystem_id, declared in dependencies.items()
            if not declared
        ),
        key=order_key,
    )
    ordered: list[str] = []
    while ready:
        subsystem_id = ready.pop(0)
        ordered.append(subsystem_id)
        for dependent in sorted(
            dependents.get(subsystem_id, set()), key=order_key
        ):
            dependencies[dependent].discard(subsystem_id)
            if not dependencies[dependent] and dependent not in ready:
                ready.append(dependent)
        ready.sort(key=order_key)
    if len(ordered) != len(by_id):
        cycle = sorted(
            subsystem_id
            for subsystem_id, declared in dependencies.items()
            if declared
        )
        raise RulesSchedulerError(
            f"Subsystem dependencies contain a cycle: {cycle}"
        )
    return ordered


def _active_profiles(
    values: Sequence[str],
    profile_priority: Sequence[str],
) -> list[str]:
    declared = {str(value) for value in values}
    if "all" in declared:
        declared = set(profile_priority)
    ordered = [
        profile for profile in profile_priority if profile in declared
    ]
    ordered.extend(sorted(declared - set(ordered)))
    return ordered


def _rules_related(first: str, second: str) -> bool:
    return (
        first == second
        or first.startswith(second + ".")
        or second.startswith(first + ".")
    )


def _capability_ids_by_rule(
    rule_ids: Sequence[str],
    capability_registry: Mapping[str, Any],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    capabilities = list(capability_registry.get("capabilities", []))
    for rule_id in rule_ids:
        result[rule_id] = sorted(
            str(capability.get("id"))
            for capability in capabilities
            if capability.get("id")
            and any(
                _rules_related(rule_id, str(official_rule))
                for official_rule in capability.get("official_rules", [])
            )
        )
    return result


def _scheduler_context(
    rule_index: Mapping[str, Any],
    conformance: Mapping[str, Any],
    catalog: Mapping[str, Any],
) -> dict[str, Any]:
    if int(catalog.get("schema_version") or 0) != 1:
        raise RulesSchedulerError("Unsupported rules subsystem catalog")
    rules = list(rule_index.get("rules", []))
    cases = list(conformance.get("cases", []))
    rules_by_id = {str(row.get("rule_id")): row for row in rules}
    cases_by_id = {str(row.get("rule_id")): row for row in cases}
    if len(rules_by_id) != len(rules):
        raise RulesSchedulerError("Rule index contains duplicate ids")
    if len(cases_by_id) != len(cases):
        raise RulesSchedulerError("Conformance corpus contains duplicate ids")
    if set(rules_by_id) != set(cases_by_id):
        raise RulesSchedulerError(
            "Rule index and conformance corpus cover different rule ids"
        )
    subsystems = list(catalog.get("subsystems", []))
    ordered_subsystem_ids = _topological_subsystems(subsystems)
    subsystem_by_id = {str(row["id"]): row for row in subsystems}
    section_to_subsystem: dict[str, str] = {}
    for subsystem in subsystems:
        for value in subsystem.get("section_ids", []):
            section_id = str(value)
            if section_id in section_to_subsystem:
                raise RulesSchedulerError(
                    f"Section {section_id} is assigned more than once"
                )
            section_to_subsystem[section_id] = str(subsystem["id"])
    indexed_sections = {
        str(rule.get("section", {}).get("id") or "")
        for rule in rules
    }
    missing = indexed_sections - set(section_to_subsystem)
    extra = set(section_to_subsystem) - indexed_sections
    if missing or extra:
        raise RulesSchedulerError(
            "Subsystem catalog section coverage mismatch: "
            f"missing={sorted(missing)}, extra={sorted(extra)}"
        )
    queue_statuses = {
        str(value) for value in catalog.get("queue_statuses", [])
    }
    queue_classifications = {
        str(value)
        for value in catalog.get("queue_classifications", [])
    }
    queued_rule_ids = {
        rule_id
        for rule_id, case in cases_by_id.items()
        if str(case.get("status")) in queue_statuses
        and str(case.get("classification")) in queue_classifications
    }
    selected_source = dict(catalog.get("selected_batch") or {})
    selected_rule_ids = {
        str(value) for value in selected_source.get("rule_ids", [])
    }
    selected_subsystem_id = str(
        selected_source.get("subsystem_id") or ""
    )
    if selected_subsystem_id not in subsystem_by_id:
        raise RulesSchedulerError(
            "Selected batch must name a known subsystem"
        )
    if not selected_rule_ids:
        raise RulesSchedulerError(
            "Selected batch must contain at least one rule"
        )
    if not selected_rule_ids <= queued_rule_ids:
        raise RulesSchedulerError(
            "Selected batch includes a trusted, definition-only, or "
            "unknown rule: "
            f"{sorted(selected_rule_ids - queued_rule_ids)}"
        )
    return {
        "rules": rules,
        "cases": cases,
        "rules_by_id": rules_by_id,
        "cases_by_id": cases_by_id,
        "subsystems": subsystems,
        "ordered_subsystem_ids": ordered_subsystem_ids,
        "subsystem_by_id": subsystem_by_id,
        "section_to_subsystem": section_to_subsystem,
        "queued_rule_ids": queued_rule_ids,
        "profile_priority": [
            str(value)
            for value in catalog.get("active_profile_priority", [])
        ],
        "selected_source": selected_source,
        "selected_rule_ids": selected_rule_ids,
        "selected_subsystem_id": selected_subsystem_id,
    }


def _queue_items(
    context: Mapping[str, Any],
    capability_registry: Mapping[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    rules = context["rules"]
    rules_by_id = context["rules_by_id"]
    cases_by_id = context["cases_by_id"]
    queued_rule_ids = context["queued_rule_ids"]
    selected_rule_ids = context["selected_rule_ids"]
    selected_subsystem_id = context["selected_subsystem_id"]
    capability_ids = _capability_ids_by_rule(
        list(rules_by_id), capability_registry
    )
    dependent_counts: Counter[str] = Counter()
    for rule in rules:
        for dependency in rule.get("dependency_ids", []):
            dependent_counts[str(dependency)] += 1
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rule_id in sorted(queued_rule_ids, key=_natural_rule_key):
        rule = rules_by_id[rule_id]
        case = cases_by_id[rule_id]
        section_id = str(rule.get("section", {}).get("id") or "")
        subsystem_id = context["section_to_subsystem"][section_id]
        if rule_id in selected_rule_ids and (
            subsystem_id != selected_subsystem_id
        ):
            raise RulesSchedulerError(
                f"Selected rule {rule_id} is outside "
                f"{selected_subsystem_id}"
            )
        dependencies = _ordered_unique(
            [
                str(value)
                for value in (
                    case.get("dependency_rule_ids")
                    or rule.get("dependency_ids", [])
                )
            ]
        )
        queued_dependencies = [
            value for value in dependencies if value in queued_rule_ids
        ]
        classification = str(case.get("classification") or "")
        work_state = (
            "behavioral_review_required"
            if classification == "unclassified"
            else "blocked_by_queued_rule"
            if queued_dependencies
            else "reviewed_behavioral_blocked"
        )
        result[subsystem_id].append(
            {
                "rule_id": rule_id,
                "section_id": section_id,
                "section_title": str(
                    rule.get("section", {}).get("title") or ""
                ),
                "classification": classification,
                "conformance_status": str(case.get("status") or ""),
                "assertion_kind": str(
                    case.get("assertion_kind") or ""
                ),
                "reviewed": bool(case.get("reviewed")),
                "work_state": work_state,
                "selected_batch": rule_id in selected_rule_ids,
                "dependency_rule_ids": dependencies,
                "queued_dependency_rule_ids": queued_dependencies,
                "dependent_rule_count": dependent_counts[rule_id],
                "implementation_components": _ordered_unique(
                    case.get("implementation_components", [])
                ),
                "executable_test_ids": _ordered_unique(
                    case.get("executable_test_ids", [])
                ),
                "active_profiles": _active_profiles(
                    rule.get("applicability_profiles", []),
                    context["profile_priority"],
                ),
                "compiler_impact": list(
                    context["subsystem_by_id"][subsystem_id].get(
                        "compiler_impact", []
                    )
                ),
                "capability_ids": capability_ids[rule_id],
                "blockers": _ordered_unique(case.get("blockers", [])),
                "source_span": rule.get("source_span"),
            }
        )
    return result


def _subsystem_rows(
    context: Mapping[str, Any],
    queued_by_subsystem: Mapping[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows = []
    for index, subsystem_id in enumerate(
        context["ordered_subsystem_ids"], start=1
    ):
        source = context["subsystem_by_id"][subsystem_id]
        queue_items = queued_by_subsystem.get(subsystem_id, [])
        conformance_counts = Counter(
            item["conformance_status"] for item in queue_items
        )
        classification_counts = Counter(
            item["classification"] for item in queue_items
        )
        sections = set(source.get("section_ids", []))
        rows.append(
            {
                "schedule_order": index,
                "subsystem_id": subsystem_id,
                "title": str(source.get("title") or ""),
                "depends_on_subsystems": list(
                    source.get("depends_on", [])
                ),
                "section_ids": list(source.get("section_ids", [])),
                "compiler_impact": list(
                    source.get("compiler_impact", [])
                ),
                "active_profiles": list(context["profile_priority"]),
                "total_indexed_rules": sum(
                    str(rule.get("section", {}).get("id") or "")
                    in sections
                    for rule in context["rules"]
                ),
                "queued_rule_count": len(queue_items),
                "conformance_status_counts": dict(
                    sorted(conformance_counts.items())
                ),
                "classification_counts": dict(
                    sorted(classification_counts.items())
                ),
                "implementation_components": sorted(
                    {
                        value
                        for item in queue_items
                        for value in item["implementation_components"]
                    }
                ),
                "executable_test_ids": sorted(
                    {
                        value
                        for item in queue_items
                        for value in item["executable_test_ids"]
                    }
                ),
                "capability_ids": sorted(
                    {
                        value
                        for item in queue_items
                        for value in item["capability_ids"]
                    }
                ),
                "work_state": (
                    "selected_batch"
                    if subsystem_id == context["selected_subsystem_id"]
                    else "reviewed_blockers_present"
                    if conformance_counts.get("blocked", 0)
                    else "behavioral_review_required"
                    if queue_items
                    else "no_queued_rules"
                ),
                "rules": queue_items,
            }
        )
    return rows


def _selected_batch(
    context: Mapping[str, Any],
    queued_by_subsystem: Mapping[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    items = [
        item
        for item in queued_by_subsystem[
            context["selected_subsystem_id"]
        ]
        if item["rule_id"] in context["selected_rule_ids"]
    ]
    return {
        **context["selected_source"],
        "rule_ids": sorted(
            context["selected_rule_ids"], key=_natural_rule_key
        ),
        "implementation_components": sorted(
            {
                value
                for item in items
                for value in item["implementation_components"]
            }
        ),
        "executable_test_ids": sorted(
            {
                value
                for item in items
                for value in item["executable_test_ids"]
            }
        ),
        "rules": items,
    }


def _queue_summary(context: Mapping[str, Any]) -> dict[str, Any]:
    cases = context["cases"]
    status_counts = Counter(str(case.get("status") or "") for case in cases)
    classification_counts = Counter(
        str(case.get("classification") or "") for case in cases
    )
    return {
        "total_rules": len(context["rules"]),
        "queued_rules": len(context["queued_rule_ids"]),
        "reviewed_behavioral_blocked": sum(
            case.get("classification") == "behavioral"
            and case.get("status") == "blocked"
            for case in cases
        ),
        "behavioral_review_required": sum(
            case.get("classification") == "unclassified"
            and case.get("status") == "unreviewed"
            for case in cases
        ),
        "passing_behavioral": sum(
            case.get("classification") == "behavioral"
            and case.get("status") == "passing"
            for case in cases
        ),
        "status_counts": dict(sorted(status_counts.items())),
        "classification_counts": dict(
            sorted(classification_counts.items())
        ),
        "subsystem_count": len(context["subsystems"]),
    }


def build_rules_dependency_queue(
    rule_index: Mapping[str, Any],
    conformance: Mapping[str, Any],
    catalog: Mapping[str, Any],
    capability_registry: Mapping[str, Any],
) -> dict[str, Any]:
    context = _scheduler_context(rule_index, conformance, catalog)
    queue_items = _queue_items(context, capability_registry)
    payload: dict[str, Any] = {
        "schema_version": RULES_SCHEDULER_SCHEMA_VERSION,
        "scheduler_version": int(catalog.get("scheduler_version") or 0),
        "policy": str(catalog.get("policy") or ""),
        "effective_date": rule_index.get("effective_date"),
        "source_sha256": rule_index.get("source_sha256"),
        "source_fingerprints": {
            "rule_index": _hash(rule_index),
            "conformance": _hash(conformance),
            "subsystem_catalog": _hash(catalog),
            "capability_registry": _hash(capability_registry),
        },
        "active_profile_priority": context["profile_priority"],
        "unclassified_policy": str(
            catalog.get("unclassified_policy") or ""
        ),
        "summary": _queue_summary(context),
        "selected_batch": _selected_batch(context, queue_items),
        "subsystems": _subsystem_rows(context, queue_items),
    }
    payload["fingerprint"] = _hash(payload)
    return payload


def build_rules_dependency_queue_from_root(
    root: str | Path,
) -> dict[str, Any]:
    repository = Path(root)
    return build_rules_dependency_queue(
        _load(repository / "rules" / "rule-index.json"),
        _load(repository / "rules" / "conformance-cases.json"),
        _load(repository / "platform" / "rules-subsystems.json"),
        _load(
            repository
            / "mtg_commander_sim"
            / "rules"
            / "capability-registry.json"
        ),
    )


def load_rules_dependency_queue(root: str | Path) -> dict[str, Any]:
    path = Path(root) / "coverage" / "rules-dependency-queue.json"
    value = _load(path)
    fingerprint = str(value.get("fingerprint") or "")
    unsigned = dict(value)
    unsigned.pop("fingerprint", None)
    if fingerprint != _hash(unsigned):
        raise RulesSchedulerError(
            "Rules dependency queue fingerprint does not match"
        )
    return value


def rules_next_work(
    root: str | Path,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    repository = Path(root)
    queue_path = repository / "coverage" / "rules-dependency-queue.json"
    if queue_path.is_file():
        queue = load_rules_dependency_queue(repository)
        selected = dict(queue["selected_batch"])
        next_rules = list(selected.pop("rules", []))
        return {
            "schema_version": RULES_SCHEDULER_SCHEMA_VERSION,
            "effective_date": queue.get("effective_date"),
            "scheduler_fingerprint": queue.get("fingerprint"),
            "selected_batch": selected,
            "next": next_rules[: max(1, int(limit))],
        }

    rule_index = _load(repository / "rules" / "rule-index.json")
    conformance = _load(
        repository / "rules" / "conformance-cases.json"
    )
    cases_by_rule = {
        str(case["rule_id"]): case
        for case in conformance.get("cases", [])
    }
    rules = list(rule_index.get("rules", []))
    children: Counter[str] = Counter()
    for rule in rules:
        for dependency in rule.get("dependency_ids", []):
            children[str(dependency)] += 1
    rank = {
        "failing": 0,
        "blocked": 1,
        "unreviewed": 2,
        "skipped": 3,
        "passing": 4,
        "definition_only": 5,
    }
    candidates = sorted(
        (
            {
                "rule_id": rule["rule_id"],
                "section": rule.get("section"),
                "coverage_status": rule.get("coverage_status"),
                "conformance_status": cases_by_rule.get(
                    str(rule["rule_id"]), {}
                ).get("status"),
                "classification": cases_by_rule.get(
                    str(rule["rule_id"]), {}
                ).get("classification"),
                "assertion_kind": cases_by_rule.get(
                    str(rule["rule_id"]), {}
                ).get("assertion_kind"),
                "dependent_rule_count": children[str(rule["rule_id"])],
                "source_span": rule.get("source_span"),
            }
            for rule in rules
            if cases_by_rule.get(str(rule["rule_id"]), {}).get("status")
            not in {"passing", "definition_only"}
        ),
        key=lambda row: (
            rank.get(str(row["conformance_status"]), 99),
            -int(row["dependent_rule_count"]),
            str(row["rule_id"]),
        ),
    )
    return {
        "schema_version": RULES_SCHEDULER_SCHEMA_VERSION,
        "effective_date": rule_index.get("effective_date"),
        "next": candidates[: max(1, int(limit))],
    }


def rules_dependency_queue_errors(root: str | Path) -> list[str]:
    try:
        expected = build_rules_dependency_queue_from_root(root)
        actual = load_rules_dependency_queue(root)
    except (OSError, json.JSONDecodeError, RulesSchedulerError) as exc:
        return [str(exc)]
    if stable_json(actual) != stable_json(expected):
        return [
            "coverage/rules-dependency-queue.json is stale; run "
            "python scripts/update_rules_scheduler.py --write"
        ]
    return []
