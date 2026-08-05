from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from time import perf_counter
import unittest
from typing import Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
MANIFEST = ROOT / "platform" / "test-shards.json"

for path in (str(ROOT), str(TESTS)):
    if path not in sys.path:
        sys.path.insert(0, path)


class TestShardError(ValueError):
    pass


def load_manifest(path: Path = MANIFEST) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "primary_shards",
        "overlay_suites",
    }:
        raise TestShardError("Test-shard manifest has an invalid top-level shape")
    if value["schema_version"] != 1:
        raise TestShardError("Unsupported test-shard manifest schema")
    for field in ("primary_shards", "overlay_suites"):
        suites = value[field]
        if not isinstance(suites, dict) or not suites:
            raise TestShardError(f"{field} must be a nonempty mapping")
        for name, modules in suites.items():
            if not isinstance(name, str) or not name:
                raise TestShardError(f"{field} contains an invalid suite name")
            if not isinstance(modules, list) or not modules:
                raise TestShardError(f"Suite {name!r} must be a nonempty list")
            if any(
                not isinstance(module, str)
                or not module.startswith("test_")
                or "." in module
                for module in modules
            ):
                raise TestShardError(
                    f"Suite {name!r} contains an invalid test module"
                )
            if len(modules) != len(set(modules)):
                raise TestShardError(f"Suite {name!r} contains duplicates")
            if modules != sorted(modules):
                raise TestShardError(f"Suite {name!r} must be sorted")
    return value


def discovered_modules(root: Path = TESTS) -> tuple[str, ...]:
    return tuple(sorted(path.stem for path in root.glob("test_*.py")))


def validate_partition(manifest: Mapping) -> dict:
    primary = manifest["primary_shards"]
    assigned = [module for modules in primary.values() for module in modules]
    counts = Counter(assigned)
    duplicates = sorted(module for module, count in counts.items() if count != 1)
    actual = set(discovered_modules())
    configured = set(assigned)
    missing = sorted(actual - configured)
    unknown = sorted(configured - actual)
    overlay_unknown = sorted(
        {
            module
            for modules in manifest["overlay_suites"].values()
            for module in modules
        }
        - actual
    )
    if duplicates or missing or unknown or overlay_unknown:
        raise TestShardError(
            json.dumps(
                {
                    "duplicates": duplicates,
                    "missing": missing,
                    "unknown": unknown,
                    "overlay_unknown": overlay_unknown,
                },
                sort_keys=True,
            )
        )
    return {
        "primary_shards": len(primary),
        "test_modules": len(actual),
        "overlay_suites": len(manifest["overlay_suites"]),
    }


def suite_modules(manifest: Mapping, name: str) -> tuple[str, ...]:
    for field in ("primary_shards", "overlay_suites"):
        modules = manifest[field].get(name)
        if modules is not None:
            return tuple(modules)
    raise TestShardError(f"Unknown test suite {name!r}")


def primary_matrix(manifest: Mapping) -> dict:
    validate_partition(manifest)
    return {
        "include": [
            {"shard": name}
            for name in manifest["primary_shards"]
        ]
    }


def load_suite(modules: Iterable[str]) -> unittest.TestSuite:
    names = tuple(dict.fromkeys(modules))
    if not names:
        raise TestShardError("No test modules were selected")
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    errors = []
    for test in _iter_tests(suite):
        if isinstance(test, unittest.loader._FailedTest):
            errors.append(str(test))
    if errors:
        raise TestShardError(f"Test module import failed: {errors}")
    if suite.countTestCases() <= 0:
        raise TestShardError("Selected test modules contain zero tests")
    return suite


def _iter_tests(suite: unittest.TestSuite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from _iter_tests(test)
        else:
            yield test


def describe(manifest: Mapping) -> dict:
    validate_partition(manifest)
    result = {}
    for field in ("primary_shards", "overlay_suites"):
        for name, modules in manifest[field].items():
            suite = load_suite(modules)
            result[name] = {
                "kind": field,
                "modules": len(modules),
                "tests": suite.countTestCases(),
            }
    return dict(sorted(result.items()))


def run_modules(
    modules: Sequence[str],
    *,
    verbosity: int = 2,
    suite_name: str | None = None,
    result_json: Path | None = None,
) -> bool:
    suite = load_suite(modules)
    configured_test_count = suite.countTestCases()
    started = perf_counter()
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    duration = round(perf_counter() - started, 3)
    successful = result.wasSuccessful() and result.testsRun > 0
    if result_json is not None:
        document = {
            "schema_version": 1,
            "type": "unittest-shard-result",
            "suite": suite_name,
            "modules": list(modules),
            "configured_test_count": configured_test_count,
            "tests_run": result.testsRun,
            "duration_seconds": duration,
            "successful": successful,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
            "expected_failures": len(result.expectedFailures),
            "unexpected_successes": len(result.unexpectedSuccesses),
        }
        result_json.parent.mkdir(parents=True, exist_ok=True)
        result_json.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return successful


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate, describe, or run deterministic Python test shards"
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("describe")
    run = subparsers.add_parser("run")
    run.add_argument("suite")
    run.add_argument("--result-json")
    modules = subparsers.add_parser("run-modules")
    modules.add_argument("module", nargs="+")
    modules.add_argument("--result-json")
    args = parser.parse_args()

    try:
        manifest = load_manifest()
        summary = validate_partition(manifest)
        if args.operation == "validate":
            print(json.dumps({"ok": True, **summary}, sort_keys=True))
            return 0
        if args.operation == "describe":
            print(json.dumps(describe(manifest), indent=2, sort_keys=True))
            return 0
        selected = (
            suite_modules(manifest, args.suite)
            if args.operation == "run"
            else tuple(args.module)
        )
        suite_name = args.suite if args.operation == "run" else "run-modules"
        result_json = Path(args.result_json) if args.result_json else None
        return (
            0
            if run_modules(
                selected,
                suite_name=suite_name,
                result_json=result_json,
            )
            else 1
        )
    except TestShardError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
