from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
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


def run_modules(modules: Sequence[str], *, verbosity: int = 2) -> bool:
    suite = load_suite(modules)
    return unittest.TextTestRunner(verbosity=verbosity).run(suite).wasSuccessful()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate, describe, or run deterministic Python test shards"
    )
    subparsers = parser.add_subparsers(dest="operation", required=True)
    subparsers.add_parser("validate")
    subparsers.add_parser("describe")
    run = subparsers.add_parser("run")
    run.add_argument("suite")
    modules = subparsers.add_parser("run-modules")
    modules.add_argument("module", nargs="+")
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
        return 0 if run_modules(selected) else 1
    except TestShardError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
