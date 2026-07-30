from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


RULE_CONFORMANCE_SCHEMA_VERSION = 1
RULE_CONFORMANCE_GENERATOR_VERSION = "cr-conformance-v1"

CASE_STATUSES = {
    "unreviewed",
    "passing",
    "failing",
    "blocked",
    "skipped",
    "definition_only",
}
CASE_CLASSIFICATIONS = {
    "unclassified",
    "behavioral",
    "definition_only",
    "structural",
    "example",
    "dependency",
}
ASSERTION_KINDS = {
    "inventory_only",
    "executable_engine",
    "static_traceability",
    "unsupported_fail_closed",
}
SCENARIO_KINDS = {
    "positive",
    "negative",
    "interaction",
    "multiplayer",
    "replay",
    "hidden_information",
}

_REVIEW_FIELDS = (
    "classification",
    "status",
    "assertion_kind",
    "reviewed",
    "implementation_components",
    "executable_test_ids",
    "required_scenarios",
    "covered_scenarios",
    "blockers",
    "notes",
)


def _case_id(rule_id: str) -> str:
    return f"cr-{rule_id}"


def _new_case(
    rule: Mapping[str, Any],
    *,
    effective_date: str,
    source_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": RULE_CONFORMANCE_SCHEMA_VERSION,
        "case_version": 1,
        "case_id": _case_id(str(rule["rule_id"])),
        "rule_id": str(rule["rule_id"]),
        "effective_date": effective_date,
        "source_sha256": source_sha256,
        "rule_text_sha256": str(rule["text_sha256"]),
        "source_span": dict(rule["source_span"]),
        "classification": "unclassified",
        "status": "unreviewed",
        "assertion_kind": "inventory_only",
        "reviewed": False,
        "implementation_components": [],
        "executable_test_ids": [],
        "required_scenarios": [],
        "covered_scenarios": [],
        "dependency_rule_ids": list(rule.get("dependency_ids") or []),
        "blockers": ["semantic_review_not_completed"],
        "notes": [],
    }


def build_rule_conformance(
    rule_index: Mapping[str, Any],
    *,
    previous: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one source-pinned conformance case for every indexed CR rule."""

    effective_date = str(rule_index.get("effective_date") or "")
    source_sha256 = str(rule_index.get("source_sha256") or "")
    previous_by_id = {
        str(case.get("rule_id")): case
        for case in (previous or {}).get("cases", [])
    }
    cases: list[dict[str, Any]] = []
    for rule in rule_index.get("rules", []):
        case = _new_case(
            rule,
            effective_date=effective_date,
            source_sha256=source_sha256,
        )
        prior = previous_by_id.get(str(rule["rule_id"]))
        if (
            prior is not None
            and prior.get("source_sha256") == source_sha256
            and prior.get("rule_text_sha256") == rule.get("text_sha256")
        ):
            for field in _REVIEW_FIELDS:
                if field in prior:
                    value = prior[field]
                    case[field] = list(value) if isinstance(value, list) else value
            case["case_version"] = int(prior.get("case_version") or 1)
        cases.append(case)
    return {
        "schema_version": RULE_CONFORMANCE_SCHEMA_VERSION,
        "generator_version": RULE_CONFORMANCE_GENERATOR_VERSION,
        "effective_date": effective_date,
        "source_sha256": source_sha256,
        "case_count": len(cases),
        "cases": cases,
    }


def validate_rule_conformance(
    corpus: Mapping[str, Any],
    rule_index: Mapping[str, Any],
    *,
    known_test_ids: set[str] | None = None,
) -> list[str]:
    """Return structural and honesty-policy errors for a conformance corpus."""

    errors: list[str] = []
    if corpus.get("schema_version") != RULE_CONFORMANCE_SCHEMA_VERSION:
        errors.append("conformance corpus has an unsupported schema version")
    if corpus.get("generator_version") != RULE_CONFORMANCE_GENERATOR_VERSION:
        errors.append("conformance corpus has an unsupported generator version")
    for field in ("effective_date", "source_sha256"):
        if corpus.get(field) != rule_index.get(field):
            errors.append(f"conformance corpus {field} does not match rule index")

    rules = {
        str(rule["rule_id"]): rule
        for rule in rule_index.get("rules", [])
    }
    cases = list(corpus.get("cases", []))
    case_ids = [str(case.get("case_id")) for case in cases]
    rule_ids = [str(case.get("rule_id")) for case in cases]
    if len(case_ids) != len(set(case_ids)):
        errors.append("conformance corpus contains duplicate case IDs")
    if len(rule_ids) != len(set(rule_ids)):
        errors.append("conformance corpus contains duplicate rule IDs")
    if int(corpus.get("case_count", -1)) != len(cases):
        errors.append("conformance case_count does not match cases")
    missing = sorted(set(rules) - set(rule_ids))
    extra = sorted(set(rule_ids) - set(rules))
    if missing:
        errors.append(
            "conformance corpus is missing rule IDs: " + ", ".join(missing[:10])
        )
    if extra:
        errors.append(
            "conformance corpus has unknown rule IDs: " + ", ".join(extra[:10])
        )

    for case in cases:
        rule_id = str(case.get("rule_id"))
        prefix = f"Conformance case {rule_id}"
        rule = rules.get(rule_id)
        if rule is None:
            continue
        if case.get("schema_version") != RULE_CONFORMANCE_SCHEMA_VERSION:
            errors.append(f"{prefix} has an unsupported schema version")
        if (
            not isinstance(case.get("case_version"), int)
            or int(case["case_version"]) < 1
        ):
            errors.append(f"{prefix} has an invalid case version")
        if case.get("case_id") != _case_id(rule_id):
            errors.append(f"{prefix} has a noncanonical case ID")
        if case.get("effective_date") != rule_index.get("effective_date"):
            errors.append(f"{prefix} points to a different effective date")
        if case.get("source_sha256") != rule_index.get("source_sha256"):
            errors.append(f"{prefix} points to a different source snapshot")
        if case.get("rule_text_sha256") != rule.get("text_sha256"):
            errors.append(f"{prefix} points to changed rule text")
        if case.get("source_span") != rule.get("source_span"):
            errors.append(f"{prefix} has a stale source span")
        if case.get("dependency_rule_ids") != list(
            rule.get("dependency_ids") or []
        ):
            errors.append(f"{prefix} has stale rule dependencies")

        status = str(case.get("status"))
        classification = str(case.get("classification"))
        assertion_kind = str(case.get("assertion_kind"))
        reviewed = case.get("reviewed") is True
        components = case.get("implementation_components")
        test_ids = case.get("executable_test_ids")
        required = case.get("required_scenarios")
        covered = case.get("covered_scenarios")
        blockers = case.get("blockers")
        notes = case.get("notes")
        if status not in CASE_STATUSES:
            errors.append(f"{prefix} has unknown status {status!r}")
        if classification not in CASE_CLASSIFICATIONS:
            errors.append(
                f"{prefix} has unknown classification {classification!r}"
            )
        if assertion_kind not in ASSERTION_KINDS:
            errors.append(
                f"{prefix} has unknown assertion kind {assertion_kind!r}"
            )
        for field, value in (
            ("implementation_components", components),
            ("executable_test_ids", test_ids),
            ("required_scenarios", required),
            ("covered_scenarios", covered),
            ("blockers", blockers),
            ("notes", notes),
        ):
            if not isinstance(value, list) or any(
                not isinstance(item, str) or not item
                for item in (value if isinstance(value, list) else [])
            ):
                errors.append(f"{prefix} has invalid {field}")
            elif field != "notes" and len(value) != len(set(value)):
                errors.append(f"{prefix} has duplicate {field}")
        if isinstance(required, list) and (
            set(required) - SCENARIO_KINDS
        ):
            errors.append(f"{prefix} has unknown required scenarios")
        if isinstance(covered, list) and (
            set(covered) - SCENARIO_KINDS
        ):
            errors.append(f"{prefix} has unknown covered scenarios")
        if isinstance(required, list) and isinstance(covered, list):
            if set(covered) - set(required):
                errors.append(
                    f"{prefix} covers scenarios it did not require"
                )

        if status == "unreviewed":
            if reviewed:
                errors.append(f"{prefix} is unreviewed but marked reviewed")
            if assertion_kind != "inventory_only":
                errors.append(
                    f"{prefix} is unreviewed but is not inventory-only"
                )
            if not blockers:
                errors.append(f"{prefix} is unreviewed without a blocker")
        if status in {"passing", "failing"}:
            if not reviewed:
                errors.append(f"{prefix} has a result without review")
            if assertion_kind != "executable_engine":
                errors.append(
                    f"{prefix} has a result without executable semantics"
                )
            if not components or not test_ids or not required:
                errors.append(
                    f"{prefix} lacks implementation, tests, or scenarios"
                )
            if known_test_ids is not None:
                unknown_tests = sorted(
                    set(test_ids or []) - known_test_ids
                )
                if unknown_tests:
                    errors.append(
                        f"{prefix} references unknown executable tests: "
                        + ", ".join(unknown_tests)
                    )
        if status == "passing":
            if blockers:
                errors.append(f"{prefix} passes while blockers remain")
            if set(required or []) != set(covered or []):
                errors.append(
                    f"{prefix} passes without all required scenarios"
                )
        if status == "definition_only":
            if not reviewed or classification != "definition_only":
                errors.append(
                    f"{prefix} is definition-only without reviewed classification"
                )
            if assertion_kind != "static_traceability":
                errors.append(
                    f"{prefix} is definition-only without traceability"
                )
            if not components or not test_ids:
                errors.append(
                    f"{prefix} lacks definition traceability evidence"
                )
            if known_test_ids is not None:
                unknown_tests = sorted(
                    set(test_ids or []) - known_test_ids
                )
                if unknown_tests:
                    errors.append(
                        f"{prefix} references unknown traceability tests: "
                        + ", ".join(unknown_tests)
                    )
        if status in {"blocked", "skipped"}:
            if not reviewed:
                errors.append(
                    f"{prefix} is {status} without completed review"
                )
            if not blockers:
                errors.append(
                    f"{prefix} is {status} without a recorded reason"
                )
            if known_test_ids is not None and test_ids:
                unknown_tests = sorted(
                    set(test_ids) - known_test_ids
                )
                if unknown_tests:
                    errors.append(
                        f"{prefix} references unknown reviewed tests: "
                        + ", ".join(unknown_tests)
                    )
    return errors


def rule_conformance_coverage(
    corpus: Mapping[str, Any],
) -> dict[str, Any]:
    cases = list(corpus.get("cases", []))
    statuses = Counter(str(case.get("status")) for case in cases)
    assertions = Counter(str(case.get("assertion_kind")) for case in cases)
    classifications = Counter(
        str(case.get("classification")) for case in cases
    )
    passing = int(statuses.get("passing", 0))
    definition_only = int(statuses.get("definition_only", 0))
    complete = (
        bool(cases)
        and passing + definition_only == len(cases)
        and not any(
            statuses.get(status, 0)
            for status in (
                "unreviewed",
                "failing",
                "blocked",
                "skipped",
            )
        )
    )
    behavioral = [
        case
        for case in cases
        if case.get("classification") == "behavioral"
    ]
    behavioral_passing = sum(
        case.get("status") == "passing" for case in behavioral
    )
    return {
        "schema_version": RULE_CONFORMANCE_SCHEMA_VERSION,
        "effective_date": corpus.get("effective_date"),
        "source_sha256": corpus.get("source_sha256"),
        "total_cases": len(cases),
        "status_counts": dict(sorted(statuses.items())),
        "assertion_kind_counts": dict(sorted(assertions.items())),
        "classification_counts": dict(sorted(classifications.items())),
        "semantic_passing_cases": passing,
        "semantic_failing_cases": int(statuses.get("failing", 0)),
        "blocked_cases": int(statuses.get("blocked", 0)),
        "skipped_cases": int(statuses.get("skipped", 0)),
        "unreviewed_cases": int(statuses.get("unreviewed", 0)),
        "definition_only_cases": definition_only,
        "inventory_only_cases": int(assertions.get("inventory_only", 0)),
        "behavioral_cases": len(behavioral),
        "behavioral_passing_cases": behavioral_passing,
        "behavioral_passing_fraction": (
            round(behavioral_passing / len(behavioral), 6)
            if behavioral
            else 0.0
        ),
        "current_snapshot_complete": complete,
    }


def case_by_rule_id(
    corpus: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    return {
        str(case["rule_id"]): case
        for case in corpus.get("cases", [])
    }


def discover_unittest_ids(root: str | Path) -> set[str]:
    """Discover statically declared unittest IDs without importing tests."""

    root = Path(root)
    discovered: set[str] = set()
    for path in sorted((root / "tests").glob("test_*.py")):
        tree = ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
        )
        module = f"tests.{path.stem}"
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for child in node.body:
                if (
                    isinstance(
                        child,
                        (ast.FunctionDef, ast.AsyncFunctionDef),
                    )
                    and child.name.startswith("test_")
                ):
                    discovered.add(
                        f"{module}.{node.name}.{child.name}"
                    )
    return discovered


def inventory_case_errors(
    case: Mapping[str, Any],
    rule: Mapping[str, Any],
    *,
    effective_date: str,
    source_sha256: str,
) -> Sequence[str]:
    """Small per-rule assertion surface used by the generated test harness."""

    expected = build_rule_conformance(
        {
            "effective_date": effective_date,
            "source_sha256": source_sha256,
            "rules": [rule],
        }
    )["cases"][0]
    errors: list[str] = []
    for field in (
        "case_id",
        "rule_id",
        "effective_date",
        "source_sha256",
        "rule_text_sha256",
        "source_span",
        "dependency_rule_ids",
    ):
        if case.get(field) != expected.get(field):
            errors.append(f"{field} does not match the pinned rule")
    return errors
