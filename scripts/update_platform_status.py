from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "platform" / "readiness-source.json"
JSON_OUTPUT = ROOT / "coverage" / "platform-readiness.json"
MARKDOWN_OUTPUT = ROOT / "coverage" / "platform-readiness.md"
STATUS_OUTPUT = ROOT / "docs" / "PLATFORM_IMPLEMENTATION_STATUS.md"
TRACKED_OUTPUTS = frozenset(
    path.relative_to(ROOT).as_posix()
    for path in (JSON_OUTPUT, MARKDOWN_OUTPUT, STATUS_OUTPUT)
)
SOURCE_TREE_FINGERPRINT_ALGORITHM = "tracked-source-tree-sha256-v2"


def _load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.decode("utf-8", errors="strict").strip()


def _current_runtime_git_sha() -> str:
    return _git("rev-parse", "HEAD")


def _git_is_ancestor(ancestor: str, descendant: str) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    return completed.returncode == 0


def _tracked_source_tree_hash() -> str:
    """Fingerprint the evaluated tracked tree without self-referential outputs."""

    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    relative_paths = sorted(
        path.decode("utf-8", errors="strict")
        for path in completed.stdout.split(b"\0")
        if path
    )
    digest = hashlib.sha256()
    digest.update((SOURCE_TREE_FINGERPRINT_ALGORITHM + "\0").encode("ascii"))
    for relative in relative_paths:
        path = ROOT / relative
        if _is_generated_report(relative, path):
            continue
        path_bytes = relative.encode("utf-8")
        content = path.read_bytes()
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _is_generated_report(relative: str, path: Path) -> bool:
    if relative in TRACKED_OUTPUTS or relative.startswith("coverage/"):
        return True
    if relative == "platform/card-name-hash-index.json":
        return True
    if path.suffix.lower() != ".md":
        return False
    try:
        prefix = path.read_text(encoding="utf-8")[:512]
    except UnicodeDecodeError:
        return False
    return bool(re.search(r"(?m)^status:\s*[\"']?generated[\"']?\s*$", prefix))


def _validate_provenance(source: dict) -> None:
    provenance = source.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("platform readiness source requires provenance")
    required = {
        "feature_head_sha",
        "certified_head_sha",
        "generation_timestamp",
    }
    missing = sorted(required.difference(provenance))
    if missing:
        raise ValueError("platform readiness provenance is missing: " + ", ".join(missing))
    for key in ("feature_head_sha", "certified_head_sha"):
        value = provenance[key]
        if not isinstance(value, str) or len(value) != 40:
            raise ValueError(f"{key} must be a full Git commit SHA")
        _git("cat-file", "-e", f"{value}^{{commit}}")
    if "baseline_commit" in source.get("validation", {}):
        raise ValueError(
            "baseline_commit cannot identify evaluated behavior; use provenance"
        )
    if "commit_reference" in source.get("integration", {}):
        raise ValueError(
            "commit_reference duplicates structured provenance and is not allowed"
        )
    serialized = json.dumps(source, sort_keys=True).lower()
    if "certification pending" in serialized:
        raise ValueError("a certified head cannot be described as certification pending")
    active_phase = source.get("integration", {}).get("active_phase")
    if active_phase and _git_is_ancestor(
        provenance["feature_head_sha"], "origin/main"
    ):
        raise ValueError(
            "active phase feature_head_sha is already merged into origin/main"
        )


def _project_metadata() -> dict:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return project["project"]


def _test_count() -> int:
    root_text = str(ROOT)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    suite = unittest.defaultTestLoader.discover(
        str(ROOT / "tests"),
        pattern="test_*.py",
    )
    return suite.countTestCases()


def _file_count(relative: str) -> int:
    directory = ROOT / relative
    if not directory.is_dir():
        return 0
    ignored_parts = {
        "__pycache__",
        "node_modules",
        "dist",
        "playwright-report",
        "test-results",
    }
    return sum(
        1
        for path in directory.rglob("*")
        if path.is_file()
        and not ignored_parts.intersection(path.relative_to(directory).parts)
        and path.suffix not in {".pyc", ".tsbuildinfo"}
    )


def _optional_json(relative: str) -> dict | None:
    path = ROOT / relative
    return _load_json(path) if path.is_file() else None


def _rules_metrics() -> dict:
    manifest = _optional_json("rules/manifest.json")
    conformance = _optional_json("coverage/rules-conformance.json")
    mechanics = _optional_json("coverage/mechanics-coverage.json")
    oracle = _optional_json("coverage/oracle-coverage.json")
    commander = _optional_json("coverage/oracle-coverage-commander.json")
    return {
        "manifest_present": manifest is not None,
        "effective_date": (manifest or {}).get("effective_date"),
        "source_sha256": (manifest or {}).get("source_sha256"),
        "rules": {
            "total": (conformance or {}).get("total_cases"),
            "passing": (conformance or {}).get("semantic_passing_cases"),
            "blocked": (conformance or {}).get("blocked_cases"),
            "definition_only": (conformance or {}).get("definition_only_cases"),
            "unreviewed": (conformance or {}).get("unreviewed_cases"),
        },
        "mechanics": {
            "total": (mechanics or {}).get("total_mechanics"),
            "trusted": (mechanics or {}).get("trusted_mechanics"),
            "status_counts": (mechanics or {}).get("status_counts"),
        },
        "oracle": {
            "total": (oracle or {}).get("total_oracle_ids"),
            "status_counts": (oracle or {}).get("status_counts"),
            "material_residuals": (oracle or {}).get("material_residuals"),
        },
        "commander_oracle": {
            "total": (commander or {}).get("total_oracle_ids"),
            "status_counts": (commander or {}).get("status_counts"),
            "material_residuals": (commander or {}).get("material_residuals"),
        },
        "current_snapshot_complete": bool(
            (conformance or {}).get("current_snapshot_complete")
            and (mechanics or {}).get("current_snapshot_complete")
            and (oracle or {}).get("current_snapshot_complete")
            and (commander or {}).get("current_snapshot_complete")
        ),
    }


def build_report() -> dict:
    source = _load_json(SOURCE)
    if source.get("schema_version") != 2:
        raise ValueError("Unsupported platform readiness source schema")
    _validate_provenance(source)
    report = copy.deepcopy(source)
    for ephemeral in ("branch", "branch_ancestry", "pull_requests"):
        report["integration"].pop(ephemeral, None)
    report["generated"] = {
        "generator": "scripts/update_platform_status.py",
        "source": "platform/readiness-source.json",
        "stale_check": "python scripts/update_platform_status.py --check",
        "evaluated_source_tree_hash": _tracked_source_tree_hash(),
        "source_tree_fingerprint_algorithm": SOURCE_TREE_FINGERPRINT_ALGORITHM,
        "current_runtime_git_sha": _current_runtime_git_sha(),
        "current_runtime_git_sha_persistence": (
            "runtime-only; tracked reports store null because a commit cannot "
            "contain its own SHA"
        ),
    }
    project = _project_metadata()
    report["package"] = {
        "name": "mtg-commander-sim",
        "version": str(project["version"]),
        "python": str(project["requires-python"]),
    }
    report["tests"] = {
        "deterministic_cases_discovered": _test_count(),
        "schema_files": _file_count("schemas")
        + _file_count("mtg_commander_sim/schemas"),
        "server_files": _file_count("server"),
        "web_files": _file_count("web"),
        "migration_files": _file_count("migrations"),
    }
    report["rules_coverage"] = _rules_metrics()
    return report


def _value(value: object) -> str:
    if value is None:
        return "not available"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, dict):
        return ", ".join(f"{key}={item}" for key, item in sorted(value.items()))
    return str(value)


def render_readiness(report: dict) -> str:
    provenance = report["provenance"]
    generated = report["generated"]
    lines = [
        "---",
        'title: "Platform readiness"',
        'status: "generated"',
        'authoritative_source: "platform/readiness-source.json"',
        f'verified: "{generated["evaluated_source_tree_hash"]}"',
        'audience: "maintainers, operators, and contributors"',
        'maintenance: "generated"',
        "---",
        "",
        "# Platform readiness",
        "",
        "Generated from `platform/readiness-source.json`. Do not edit this file "
        "directly.",
        "",
        "| Dimension | Current value |",
        "|---|---|",
        f"| Package | `{report['package']['version']}` |",
        f"| Evaluated source tree | `{generated['evaluated_source_tree_hash']}` |",
        f"| Feature checkpoint | `{provenance['feature_head_sha']}` |",
        f"| Certified head | `{provenance['certified_head_sha']}` |",
        f"| Active phase | `{report['integration']['active_phase']}` |",
        f"| Deterministic tests discovered | {report['tests']['deterministic_cases_discovered']} |",
        f"| Authoritative kernel | `{report['platform']['authoritative_kernel']}` |",
        f"| Server runtime | `{report['platform']['http_websocket_server']}` |",
        f"| Browser client | `{report['platform']['browser_client']}` |",
        f"| Durable persistence | `{report['platform']['durable_database']}` |",
        f"| Exact command replay | `{report['platform']['replay']}` |",
        f"| Hidden-information projection | `{report['platform']['hidden_information']}` |",
        f"| Core AI dependency | `{report['platform']['ai_dependency']}` |",
        f"| Rules snapshot integrated | {_value(report['rules_coverage']['manifest_present'])} |",
        f"| Rules snapshot complete | {_value(report['rules_coverage']['current_snapshot_complete'])} |",
        "",
        "## Milestones",
        "",
        "| Milestone | Status | Evidence |",
        "|---|---|---|",
    ]
    for milestone in report["milestones"]:
        lines.append(
            f"| {milestone['name']} | `{milestone['status']}` | "
            f"{milestone['evidence']} |"
        )
    lines.extend(
        [
            "",
            "## Blockers",
            "",
            *(f"- {blocker}" for blocker in report["blockers"]),
            "",
            "## Next task",
            "",
            report["next_task"],
            "",
        ]
    )
    return "\n".join(lines)


def render_status(report: dict) -> str:
    integration = report["integration"]
    provenance = report["provenance"]
    generated = report["generated"]
    validation = report["validation"]
    rules = report["rules_coverage"]
    lines = [
        "---",
        'title: "Platform implementation status"',
        'status: "generated"',
        'authoritative_source: "platform/readiness-source.json"',
        f'verified: "{generated["evaluated_source_tree_hash"]}"',
        'audience: "maintainers, operators, and contributors"',
        'maintenance: "generated"',
        "---",
        "",
        "# Platform implementation status",
        "",
        "This is the durable program ledger. It is generated from "
        "`platform/readiness-source.json`; generated metrics are read from the "
        "repository rather than copied by hand.",
        "",
        "## Repository and integration",
        "",
        f"- Repository: {report['repository']['visibility']} "
        f"`{report['repository']['name']}`",
        f"- Default branch: `{report['repository']['default_branch']}`",
        f"- Evaluated source tree: `{generated['evaluated_source_tree_hash']}` "
        f"(`{generated['source_tree_fingerprint_algorithm']}`)",
        f"- Feature checkpoint: `{provenance['feature_head_sha']}`",
        f"- Last certified head: `{provenance['certified_head_sha']}`",
        f"- Generation timestamp: `{provenance['generation_timestamp']}`",
        "- Runtime Git SHA: resolved dynamically and intentionally not persisted "
        "in this tracked report",
        f"- Active phase: `{integration['active_phase']}`",
        f"- Package version: `{report['package']['version']}`",
        "",
        "Historical integration chronology belongs in `CHANGELOG.md`; this "
        "current report intentionally does not reproduce a pull-request ledger.",
        "",
            "## Pinned snapshots and coverage",
            "",
            f"- Comprehensive Rules: {_value(report['snapshots']['comprehensive_rules']['status'])}",
            f"- Oracle: {_value(report['snapshots']['oracle']['status'])} "
            f"({report['snapshots']['oracle']['updated_at']})",
            f"- Rulings: {_value(report['snapshots']['rulings']['status'])} "
            f"({report['snapshots']['rulings']['updated_at']})",
            f"- Rules manifest present on this branch: {_value(rules['manifest_present'])}",
            f"- Rules effective date: {_value(rules['effective_date'])}",
            f"- Rules source SHA-256: {_value(rules['source_sha256'])}",
    ]
    if rules["manifest_present"]:
        lines.extend(
            [
                f"- Rules cases: {_value(rules['rules'])}",
                f"- Mechanics: {_value(rules['mechanics'])}",
                f"- Oracle coverage: {_value(rules['oracle'])}",
                f"- Commander-legal Oracle coverage: "
                f"{_value(rules['commander_oracle'])}",
                f"- Current rules/Oracle snapshot complete: "
                f"{_value(rules['current_snapshot_complete'])}",
            ]
        )
    else:
        lines.append(
            "- Generated rules/mechanics/Oracle metrics: pending integration "
            "from `agent/rules-completeness`"
        )
    lines.extend(
        [
            "",
            "## Platform milestone status",
            "",
            "| Milestone | Status | Evidence |",
            "|---|---|---|",
        ]
    )
    for milestone in report["milestones"]:
        lines.append(
            f"| {milestone['name']} | `{milestone['status']}` | "
            f"{milestone['evidence']} |"
        )
    lines.extend(
        [
            "",
            "## Runtime and product boundaries",
            "",
            *(f"- `{key}`: `{value}`" for key, value in report["platform"].items()),
            "",
            "## Deterministic validation",
            "",
            f"- Tests discovered: {report['tests']['deterministic_cases_discovered']}",
            f"- Python matrix: {validation['ci']['matrix']}",
            f"- Baseline CI: [{validation['ci']['run_id']}]({validation['ci']['url']}) "
            f"— `{validation['ci']['status']}`",
            f"- Compile: `{validation['local']['compile']}`",
            f"- Deterministic tests: `{validation['local']['deterministic_tests']}`",
            f"- Deterministic four-player full game: "
            f"`{validation['local']['deterministic_four_player_full_game']}`",
            f"- Four-player protocol demo: `{validation['local']['four_player_protocol_demo']}`",
            f"- Repository/history/security audit: "
            f"`{validation['local']['repository_history_security_audit']}`",
            f"- Wheel build and clean install: "
            f"`{validation['local']['wheel_build_and_clean_install']}`",
            f"- Replay: `{validation['replay']}`",
            f"- Privacy: `{validation['privacy']}`",
            f"- Semantic preflight: `{validation['semantic_preflight']}`",
            "",
            "AI/Codex pilot runs are optional client experiments. They are not "
            "product, rules, CI, merge, or release gates.",
            "",
            "## Current blockers",
            "",
            *(f"- {blocker}" for blocker in report["blockers"]),
            "",
            "## Exact next task",
            "",
            report["next_task"],
            "",
            "## Regeneration",
            "",
            "```bash",
            "python scripts/update_platform_status.py --write",
            "python scripts/update_platform_status.py --check",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _serialize_json(report: dict) -> str:
    persisted = copy.deepcopy(report)
    persisted["generated"]["current_runtime_git_sha"] = None
    return json.dumps(persisted, indent=2, sort_keys=True) + "\n"


def _outputs(report: dict) -> dict[Path, str]:
    return {
        JSON_OUTPUT: _serialize_json(report),
        MARKDOWN_OUTPUT: render_readiness(report),
        STATUS_OUTPUT: render_status(report),
    }


def write_outputs(report: dict) -> None:
    for path, content in _outputs(report).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def check_outputs(report: dict) -> list[str]:
    stale: list[str] = []
    for path, expected in _outputs(report).items():
        actual = path.read_text(encoding="utf-8") if path.is_file() else None
        if actual != expected:
            stale.append(path.relative_to(ROOT).as_posix())
    return stale


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = build_report()
    if args.write:
        write_outputs(report)
        print(
            json.dumps(
                {
                    "ok": True,
                    "outputs": [
                        path.relative_to(ROOT).as_posix() for path in _outputs(report)
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    stale = check_outputs(report)
    if stale:
        print(
            "platform status is stale; run "
            "`python scripts/update_platform_status.py --write`: "
            + ", ".join(stale),
            file=sys.stderr,
        )
        return 1
    print(json.dumps({"ok": True, "stale_outputs": []}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
