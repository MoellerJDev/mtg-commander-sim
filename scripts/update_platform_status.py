from __future__ import annotations

import argparse
import copy
import difflib
import hashlib
import json
import os
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
SOURCE_TREE_FINGERPRINT_ALGORITHM = "tracked-git-clean-blobs-sha256-v3"


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


def _current_merged_main_sha(source: dict) -> str:
    default_branch = str(source["repository"]["default_branch"])
    return _git("rev-parse", f"origin/{default_branch}")


def _git_is_ancestor(ancestor: str, descendant: str) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    return completed.returncode == 0


def _git_tree_sha(commit: str) -> str:
    return _git("show", "-s", "--format=%T", commit)


def _git_ref_or_none(ref: str) -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.decode("ascii", errors="strict").strip()


def _github_pull_request(number: int) -> dict:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path and Path(event_path).is_file():
        event = _load_json(Path(event_path))
        pull_request = event.get("pull_request")
        if (
            isinstance(pull_request, dict)
            and int(pull_request.get("number") or event.get("number") or 0)
            == number
        ):
            return {
                "number": number,
                "state": str(pull_request.get("state") or "").upper(),
                "headRefName": str(
                    (pull_request.get("head") or {}).get("ref") or ""
                ),
                "headRefOid": str(
                    (pull_request.get("head") or {}).get("sha") or ""
                ),
                "baseRefName": str(
                    (pull_request.get("base") or {}).get("ref") or ""
                ),
            }
    try:
        completed = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                str(number),
                "--json",
                "number,state,headRefName,headRefOid,baseRefName",
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise ValueError(
            f"active pull request #{number} could not be verified"
        ) from exc
    if completed.returncode != 0:
        raise ValueError(
            f"active pull request #{number} could not be verified"
        )
    value = json.loads(completed.stdout.decode("utf-8", errors="strict"))
    if not isinstance(value, dict):
        raise ValueError(f"active pull request #{number} returned invalid data")
    return value


def _tracked_source_tree_hash() -> str:
    """Fingerprint canonical tracked blobs without self-referential outputs.

    Git's clean filters define the repository content being evaluated.  Hashing
    raw working-tree bytes made the same tree differ between LF CI checkouts and
    CRLF Windows checkouts.
    """

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
    included_paths = [
        relative
        for relative in relative_paths
        if not _is_generated_report(relative, ROOT / relative)
    ]
    blob_oids = _canonical_tracked_blob_oids(included_paths)
    digest = hashlib.sha256()
    digest.update((SOURCE_TREE_FINGERPRINT_ALGORITHM + "\0").encode("ascii"))
    for relative, blob_oid in zip(included_paths, blob_oids, strict=True):
        path_bytes = relative.encode("utf-8")
        blob_bytes = blob_oid.encode("ascii")
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(blob_bytes).to_bytes(8, "big"))
        digest.update(blob_bytes)
    return digest.hexdigest()


def _canonical_tracked_blob_oids(relative_paths: list[str]) -> list[str]:
    """Return Git-clean blob identities for current tracked working-tree files."""

    if any("\n" in path or "\r" in path for path in relative_paths):
        raise ValueError("tracked source paths containing newlines are unsupported")
    if not relative_paths:
        return []
    completed = subprocess.run(
        ["git", "hash-object", "--filters", "--stdin-paths"],
        cwd=ROOT,
        check=True,
        input=("\n".join(relative_paths) + "\n").encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    blob_oids = completed.stdout.decode("ascii", errors="strict").splitlines()
    if len(blob_oids) != len(relative_paths):
        raise RuntimeError("git hash-object returned an incomplete tracked blob set")
    return blob_oids


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
        "feature_head_classification",
        "certified_head_sha",
        "certified_head_classification",
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
    feature_classification = provenance["feature_head_classification"]
    if feature_classification not in {
        "active_candidate",
        "historical_integrated",
    }:
        raise ValueError("feature_head_classification is unsupported")
    certified_classification = provenance["certified_head_classification"]
    if certified_classification not in {
        "current_main",
        "current_main_tree_equivalent",
        "historical_certified",
    }:
        raise ValueError("certified_head_classification is unsupported")
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
    current_main = _current_merged_main_sha(source)
    feature_on_main = _git_is_ancestor(
        provenance["feature_head_sha"], current_main
    )
    if feature_classification == "active_candidate" and feature_on_main:
        raise ValueError("active feature head is already reachable from current main")
    if feature_classification == "historical_integrated" and not feature_on_main:
        raise ValueError("historical feature head is not reachable from current main")
    if certified_classification == "current_main":
        if provenance["certified_head_sha"] != current_main:
            raise ValueError(
                "certified head trails current main without historical classification"
            )
    elif certified_classification == "current_main_tree_equivalent":
        if _git_tree_sha(provenance["certified_head_sha"]) != _git_tree_sha(
            current_main
        ):
            raise ValueError(
                "certified exact head is not tree-equivalent to current main"
            )
    elif not _git_is_ancestor(
        provenance["certified_head_sha"], current_main
    ):
        raise ValueError("certified head is not reachable from current main")
    integration = source.get("integration")
    if not isinstance(integration, dict):
        raise ValueError("platform readiness source requires integration")
    active_phase = integration.get("active_phase")
    if active_phase is not None:
        if not isinstance(active_phase, dict) or set(active_phase) != {
            "id",
            "pull_request",
            "head",
        }:
            raise ValueError(
                "active_phase must be null or a structured active PR phase"
            )
        if (
            not isinstance(active_phase["id"], str)
            or not active_phase["id"].strip()
            or type(active_phase["pull_request"]) is not int
            or active_phase["pull_request"] <= 0
            or not isinstance(active_phase["head"], str)
            or not active_phase["head"].strip()
        ):
            raise ValueError("active_phase fields are invalid")
        if feature_classification != "active_candidate":
            raise ValueError(
                "an active PR phase requires an active-candidate feature head"
            )
        pull_request = _github_pull_request(active_phase["pull_request"])
        if str(pull_request.get("state") or "").upper() != "OPEN":
            raise ValueError("active PR phase has no matching open pull request")
        if (
            pull_request.get("headRefName") != active_phase["head"]
            or pull_request.get("baseRefName")
            != source["repository"]["default_branch"]
            or not _git_is_ancestor(
                provenance["feature_head_sha"],
                str(pull_request.get("headRefOid") or ""),
            )
        ):
            raise ValueError("active PR phase does not match repository truth")
    for row in integration.get("pull_requests", ()):
        if not isinstance(row, dict):
            raise ValueError("integration.pull_requests entries must be objects")
        if str(row.get("state") or "").casefold() not in {"open", "pending"}:
            continue
        number = row.get("number")
        if type(number) is not int or number <= 0:
            raise ValueError("pending pull-request entries require a PR number")
        pull_request = _github_pull_request(number)
        if (
            str(pull_request.get("state") or "").upper() != "OPEN"
            or pull_request.get("headRefName") != row.get("head")
            or pull_request.get("baseRefName") != row.get("base")
        ):
            raise ValueError(
                f"pull request #{number} is not the recorded open candidate"
            )
        head = str(row.get("head") or "")
        head_sha = str(pull_request.get("headRefOid") or "") or _git_ref_or_none(
            f"origin/{head}"
        )
        if head_sha is not None and _git_is_ancestor(head_sha, current_main):
            raise ValueError(
                f"pull request #{number} is merged but described as pending"
            )
    if "card_program_census" in source.get("validation", {}):
        raise ValueError(
            "card_program_census must be derived from authoritative coverage artifacts"
        )
    if feature_on_main:
        stale = [
            str(row.get("id") or "")
            for row in source.get("milestones", ())
            if row.get("status") == "implemented_at_feature_head"
        ]
        if stale:
            raise ValueError(
                "merged certified milestones cannot remain at feature head: "
                + ", ".join(stale)
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


def _card_program_metrics() -> dict:
    def summary(relative: str) -> dict:
        value = _optional_json(relative) or {}
        return {
            "cards_considered": value.get("cards_considered"),
            "status_counts": value.get("status_counts"),
            "trust_basis_counts": value.get("trust_basis_counts"),
            "material_residuals": value.get("material_residuals"),
        }

    return {
        "full": summary("coverage/card-program-coverage.json"),
        "commander": summary(
            "coverage/card-program-coverage-commander.json"
        ),
    }


def _active_phase_label(value: object) -> str:
    if value is None:
        return "none recorded; derive active PR state at generation time"
    if isinstance(value, dict):
        return str(value.get("id") or "invalid active phase")
    return str(value)


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
        "current_merged_main_git_sha": _current_merged_main_sha(source),
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
    report["validation"]["card_program_census"] = _card_program_metrics()
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
    generated = report["generated"]
    fingerprint = hashlib.sha256(_serialize_json(report).encode("utf-8")).hexdigest()
    command = r".\.venv\Scripts\python.exe scripts\update_platform_status.py --write"
    lines = [
        "---",
        'title: "Platform readiness"',
        'status: "generated"',
        'authoritative_source: "platform/readiness-source.json"',
        f'verified: "{fingerprint}"',
        'audience: "maintainers, operators, and contributors"',
        'maintenance: "generated"',
        'generated_source: "coverage/platform-readiness.json"',
        f'generation_command: "{command}"',
        "---",
        "",
        "# Platform readiness",
        "",
        f"Source fingerprint: `{fingerprint}`",
        "",
        "## Current top-level state",
        "",
        f"- Package: `{report['package']['version']}`",
        f"- Authoritative kernel: `{report['platform']['authoritative_kernel']}`",
        f"- Server runtime: `{report['platform']['http_websocket_server']}`",
        f"- Browser client: `{report['platform']['browser_client']}`",
        f"- Durable persistence: `{report['platform']['durable_database']}`",
        f"- Exact command replay: `{report['platform']['replay']}`",
        f"- Hidden-information projection: `{report['platform']['hidden_information']}`",
        f"- Core AI dependency: `{report['platform']['ai_dependency']}`",
        f"- Rules snapshot integrated: {_value(report['rules_coverage']['manifest_present'])}",
        f"- Rules snapshot complete: {_value(report['rules_coverage']['current_snapshot_complete'])}",
    ]
    lines.extend(
        [
            "",
            "## Top blockers",
            "",
            *(f"- {blocker}" for blocker in report["blockers"][:5]),
            "",
            "Complete inventories and provenance are in the "
            "[machine-readable platform report](platform-readiness.json).",
            "",
            "Exact generation command:",
            "",
            "```powershell",
            command,
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def render_status(report: dict) -> str:
    generated = report["generated"]
    rules = report["rules_coverage"]
    fingerprint = hashlib.sha256(_serialize_json(report).encode("utf-8")).hexdigest()
    command = r".\.venv\Scripts\python.exe scripts\update_platform_status.py --write"
    lines = [
        "---",
        'title: "Platform implementation status"',
        'status: "generated"',
        'authoritative_source: "platform/readiness-source.json"',
        f'verified: "{fingerprint}"',
        'audience: "maintainers, operators, and contributors"',
        'maintenance: "generated"',
        'generated_source: "coverage/platform-readiness.json"',
        f'generation_command: "{command}"',
        "---",
        "",
        "# Platform implementation status",
        "",
        f"Source fingerprint: `{fingerprint}`",
        "",
        "## Current top-level state",
        "",
        f"- Package version: `{report['package']['version']}`",
        f"- Authoritative kernel: `{report['platform']['authoritative_kernel']}`",
        f"- Server runtime: `{report['platform']['http_websocket_server']}`",
        f"- Browser client: `{report['platform']['browser_client']}`",
        f"- Durable persistence: `{report['platform']['durable_database']}`",
        f"- Exact replay: `{report['platform']['replay']}`",
        f"- Hidden-information projection: `{report['platform']['hidden_information']}`",
        f"- Core AI dependency: `{report['platform']['ai_dependency']}`",
        f"- Rules snapshot integrated: {_value(rules['manifest_present'])}",
        f"- Rules snapshot complete: {_value(rules['current_snapshot_complete'])}",
            "",
            "## Top blockers",
            "",
            *(f"- {blocker}" for blocker in report["blockers"][:5]),
            "",
            "Complete platform, validation, milestone, and provenance data is in the "
            "[machine-readable platform report](../coverage/platform-readiness.json).",
            "",
            "Exact generation command:",
            "",
            "```powershell",
            command,
            "```",
            "",
    ]
    return "\n".join(lines)


def _serialize_json(report: dict) -> str:
    persisted = copy.deepcopy(report)
    persisted["generated"]["current_runtime_git_sha"] = None
    persisted["generated"]["current_merged_main_git_sha"] = None
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
        if JSON_OUTPUT.relative_to(ROOT).as_posix() in stale:
            actual = (
                JSON_OUTPUT.read_text(encoding="utf-8").splitlines()
                if JSON_OUTPUT.is_file()
                else []
            )
            expected = _serialize_json(report).splitlines()
            diagnostic = list(
                difflib.unified_diff(
                    actual,
                    expected,
                    fromfile="tracked platform status",
                    tofile="expected platform status",
                    lineterm="",
                )
            )
            print("\n".join(diagnostic[:80]), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "stale_outputs": []}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
