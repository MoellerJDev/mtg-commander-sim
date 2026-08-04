from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.change_impact import changed_files, classify_changes
from scripts.test_shards import load_manifest, suite_modules, validate_partition
from scripts.validate_python_runtime import require_supported_python


@dataclass(frozen=True)
class QuickStep:
    name: str
    command: tuple[str, ...]


def _python() -> str:
    return str(Path(sys.executable).resolve())


def build_plan(paths: Sequence[str]) -> dict:
    impact = classify_changes(paths)
    manifest = load_manifest()
    validate_partition(manifest)
    modules = list(impact.test_modules)
    for suite in impact.test_suites:
        modules.extend(suite_modules(manifest, suite))
    selected_modules = tuple(dict.fromkeys(modules))
    python = _python()
    database = ROOT / "local" / "quick-gate" / "test-ci.sqlite3"
    steps = [
        QuickStep("python-runtime", (python, "scripts/validate_python_runtime.py")),
        QuickStep(
            "compile",
            (
                python,
                "-m",
                "compileall",
                "-q",
                "mtg_commander_sim",
                "server",
                "tests",
                "scripts",
                "simctl.py",
            ),
        ),
    ]
    if selected_modules:
        steps.extend(
            (
                QuickStep(
                    "build-test-database",
                    (
                        python,
                        "scripts/build_test_database.py",
                        "build",
                        "--fixture",
                        "tests/fixtures/scryfall-exact-lists.json",
                        "--fixture",
                        "tests/fixtures/browser-lifecycle-cards.json",
                        "--fixture",
                        "tests/fixtures/damage-result-cards.json",
                        "--fixture",
                        "tests/fixtures/draw-rules-cards.json",
                        "--output",
                        str(database),
                    ),
                ),
                QuickStep(
                    "affected-tests",
                    (
                        python,
                        "scripts/test_shards.py",
                        "run-modules",
                        *selected_modules,
                    ),
                ),
            )
        )
    check_commands = {
        "architecture": (python, "scripts/validate_architecture.py", "--check"),
        "capability-evidence": (
            python,
            "scripts/update_capability_evidence.py",
            "--check",
        ),
        "documentation": (python, "scripts/validate_documentation.py", "--check"),
        "module-classifications": (
            python,
            "scripts/update_module_classifications.py",
            "--check",
        ),
        "platform-status": (
            python,
            "scripts/update_platform_status.py",
            "--check",
        ),
        "repository": (python, "scripts/validate_repository.py"),
        "rules": (python, "simctl.py", "rules", "verify", "--root", "."),
        "rules-scheduler": (
            python,
            "scripts/update_rules_scheduler.py",
            "--check",
        ),
        "test-shards": (python, "scripts/test_shards.py", "validate"),
    }
    for check in impact.checks:
        command = check_commands.get(check)
        if command is not None:
            steps.append(QuickStep(check, command))
    if "browser-build" in impact.checks:
        npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
        if npm is None:
            raise RuntimeError("npm is required for the affected browser build")
        steps.extend(
            (
                QuickStep("browser-dependencies", (npm, "ci", "--prefix", "web")),
                QuickStep(
                    "browser-generated-types",
                    (npm, "run", "generate:types", "--prefix", "web"),
                ),
                QuickStep(
                    "browser-generated-types-clean",
                    ("git", "diff", "--exit-code", "--", "web/src/generated"),
                ),
                QuickStep("browser-build", (npm, "run", "build", "--prefix", "web")),
            )
        )
    return {
        "impact": impact.to_dict(),
        "test_modules": selected_modules,
        "database": str(database),
        "steps": tuple(steps),
    }


def _run(plan: dict) -> int:
    database = Path(plan["database"])
    database.parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["MTG_CARD_DB"] = str(database)
    environment["MTG_PYTHON_EXECUTABLE"] = _python()
    tests = str(ROOT / "tests")
    environment["PYTHONPATH"] = tests + os.pathsep + environment.get("PYTHONPATH", "")
    started = time.monotonic()
    for step in plan["steps"]:
        step_started = time.monotonic()
        print(f"[{step.name}] {' '.join(step.command)}", flush=True)
        result = subprocess.run(step.command, cwd=ROOT, env=environment)
        if result.returncode:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "failed_step": step.name,
                        "returncode": result.returncode,
                    },
                    sort_keys=True,
                )
            )
            return result.returncode
        print(f"  pass {time.monotonic() - step_started:.3f}s", flush=True)
    print(
        json.dumps(
            {
                "ok": True,
                "duration_seconds": round(time.monotonic() - started, 3),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "test_modules": len(plan["test_modules"]),
                "full_pr_ci_remains_required": True,
            },
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    require_supported_python()
    parser = argparse.ArgumentParser(
        description="Run deterministic changed-file local validation"
    )
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    paths = (
        tuple(args.changed_file)
        if args.changed_file
        else changed_files(args.base, include_worktree=True)
    )
    plan = build_plan(paths)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "impact": plan["impact"],
                    "test_modules": plan["test_modules"],
                    "steps": [asdict(step) for step in plan["steps"]],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    return _run(plan)


if __name__ == "__main__":
    raise SystemExit(main())
