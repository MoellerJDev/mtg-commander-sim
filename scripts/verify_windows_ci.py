from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.test_shards import load_manifest, suite_modules, validate_partition


class WindowsCertificationError(ValueError):
    pass


def expected_suites(*, full: bool) -> tuple[str, ...]:
    manifest = load_manifest()
    validate_partition(manifest)
    if full:
        return tuple(manifest["primary_shards"])
    return ("windows-compat",)


def validate_dependencies(needs: Mapping, *, full: bool) -> None:
    expected = {
        "plan": "success",
        "windows_compatibility": "skipped" if full else "success",
        "windows_full": "success" if full else "skipped",
        "windows_package": "success",
    }
    failures = {}
    for name, result in expected.items():
        details = needs.get(name)
        actual = details.get("result") if isinstance(details, Mapping) else None
        if actual != result:
            failures[name] = {"expected": result, "actual": actual}
    unexpected = sorted(set(needs) - set(expected))
    if failures or unexpected:
        raise WindowsCertificationError(
            json.dumps(
                {"dependency_failures": failures, "unexpected": unexpected},
                sort_keys=True,
            )
        )


def _result_documents(directory: Path) -> list[dict]:
    documents = []
    for path in sorted(directory.rglob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise WindowsCertificationError(f"{path} must contain an object")
        documents.append(value)
    return documents


def validate_results(directory: Path, *, full: bool) -> dict:
    expected = expected_suites(full=full)
    manifest = load_manifest()
    documents = _result_documents(directory)
    observed: dict[str, dict] = {}
    for document in documents:
        if set(document) != {
            "schema_version",
            "type",
            "suite",
            "modules",
            "configured_test_count",
            "tests_run",
            "duration_seconds",
            "successful",
            "failures",
            "errors",
            "skipped",
            "expected_failures",
            "unexpected_successes",
        }:
            raise WindowsCertificationError("Windows shard result has invalid fields")
        if document["schema_version"] != 1 or document["type"] != "unittest-shard-result":
            raise WindowsCertificationError("Windows shard result has invalid schema")
        suite = document["suite"]
        if not isinstance(suite, str) or suite in observed:
            raise WindowsCertificationError("Windows shard result suite is invalid or duplicated")
        modules = document["modules"]
        if (
            not isinstance(modules, Sequence)
            or isinstance(modules, (str, bytes))
            or not modules
            or any(not isinstance(module, str) for module in modules)
        ):
            raise WindowsCertificationError(f"Windows shard {suite!r} has no modules")
        if tuple(modules) != suite_modules(manifest, suite):
            raise WindowsCertificationError(
                f"Windows shard {suite!r} modules do not match the manifest"
            )
        if (
            not isinstance(document["configured_test_count"], int)
            or not isinstance(document["tests_run"], int)
            or document["configured_test_count"] <= 0
            or document["tests_run"] <= 0
        ):
            raise WindowsCertificationError(f"Windows shard {suite!r} ran zero tests")
        if document["tests_run"] != document["configured_test_count"]:
            raise WindowsCertificationError(
                f"Windows shard {suite!r} did not execute every configured test"
            )
        if document["successful"] is not True:
            raise WindowsCertificationError(f"Windows shard {suite!r} did not pass")
        observed[suite] = document
    missing = sorted(set(expected) - set(observed))
    extra = sorted(set(observed) - set(expected))
    if missing or extra:
        raise WindowsCertificationError(
            json.dumps({"missing_results": missing, "extra_results": extra}, sort_keys=True)
        )
    return {
        "mode": "full" if full else "focused",
        "suites": len(observed),
        "tests_run": sum(document["tests_run"] for document in observed.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed Windows CI certification")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--full", choices=("true", "false"), required=True)
    args = parser.parse_args()
    raw = os.environ.get("CI_WINDOWS_NEEDS_JSON")
    if not raw:
        print("CI_WINDOWS_NEEDS_JSON is required")
        return 1
    try:
        needs = json.loads(raw)
        if not isinstance(needs, dict):
            raise WindowsCertificationError("CI_WINDOWS_NEEDS_JSON must contain an object")
        full = args.full == "true"
        validate_dependencies(needs, full=full)
        summary = validate_results(Path(args.results_dir), full=full)
    except (json.JSONDecodeError, OSError, WindowsCertificationError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"ok": True, **summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
