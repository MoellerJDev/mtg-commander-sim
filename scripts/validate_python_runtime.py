from __future__ import annotations

import argparse
import json
from pathlib import Path
import runpy
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
_RUNTIME_POLICY = runpy.run_path(
    str(ROOT / "mtg_commander_sim" / "python_runtime.py")
)
REQUIRES_PYTHON = _RUNTIME_POLICY["REQUIRES_PYTHON"]
SUPPORTED_PYTHON_TEXT = _RUNTIME_POLICY["SUPPORTED_PYTHON_TEXT"]
require_supported_python = _RUNTIME_POLICY["require_supported_python"]
PYTHON_CLASSIFIER = "Programming Language :: Python :: 3.12"
PYTHON_ONLY_CLASSIFIER = "Programming Language :: Python :: 3 :: Only"
CPYTHON_CLASSIFIER = "Programming Language :: Python :: Implementation :: CPython"


def project_policy_failures(root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    version_file = root / ".python-version"
    observed_version = (
        version_file.read_text(encoding="utf-8").strip()
        if version_file.is_file()
        else None
    )
    if observed_version != SUPPORTED_PYTHON_TEXT:
        failures.append(
            f".python-version must contain {SUPPORTED_PYTHON_TEXT!r}; "
            f"found {observed_version!r}"
        )

    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.is_file():
        failures.append("pyproject.toml is missing")
        return failures
    project = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))["project"]
    observed_requirement = project.get("requires-python")
    if observed_requirement != REQUIRES_PYTHON:
        failures.append(
            f"project.requires-python must be {REQUIRES_PYTHON!r}; "
            f"found {observed_requirement!r}"
        )
    classifiers = set(project.get("classifiers", ()))
    for classifier in (
        PYTHON_CLASSIFIER,
        PYTHON_ONLY_CLASSIFIER,
        CPYTHON_CLASSIFIER,
    ):
        if classifier not in classifiers:
            failures.append(f"project classifier is missing: {classifier}")
    return failures


def workflow_policy_failures(root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    workflow_root = root / ".github" / "workflows"
    required = {
        "ci.yml",
        "live-integration.yml",
        "main-smoke.yml",
        "nightly.yml",
    }
    available = {path.name for path in workflow_root.glob("*.yml")}
    for missing in sorted(required - available):
        failures.append(f".github/workflows/{missing} is missing")
    for path in sorted(workflow_root.glob("*.yml")):
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        setup_count = len(re.findall(r"uses:\s*actions/setup-python@", text))
        if setup_count == 0:
            continue
        versions = re.findall(r"python-version:\s*[\"']?([0-9.]+)", text)
        if len(versions) != setup_count or any(
            version != SUPPORTED_PYTHON_TEXT for version in versions
        ):
            failures.append(
                f"{relative} must configure exactly {SUPPORTED_PYTHON_TEXT} "
                f"for all {setup_count} Python setups; found {versions!r}"
            )
        architectures = re.findall(r"architecture:\s*[\"']?([A-Za-z0-9_-]+)", text)
        if len(architectures) != setup_count or any(
            architecture != "x64" for architecture in architectures
        ):
            failures.append(
                f"{relative} must configure x64 for all {setup_count} Python setups; "
                f"found {architectures!r}"
            )
        if "matrix.python-version" in text:
            failures.append(f"{relative} must not use a Python-version matrix")
    return failures


def validate(root: Path = ROOT) -> dict[str, object]:
    require_supported_python()
    failures = [
        *project_policy_failures(root),
        *workflow_policy_failures(root),
    ]
    if failures:
        raise ValueError("\n".join(failures))
    return {
        "ok": True,
        "python": sys.version.split()[0],
        "implementation": sys.implementation.name,
        "architecture_bits": 64 if sys.maxsize > 2**32 else 32,
        "required_minor": SUPPORTED_PYTHON_TEXT,
        "requires_python": REQUIRES_PYTHON,
        "executable": str(Path(sys.executable).resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the exact Python runtime and project metadata."
    )
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(validate(args.root.resolve()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Python runtime validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
