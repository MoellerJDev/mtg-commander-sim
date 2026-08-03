from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import subprocess
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ImpactPlan:
    changed_files: tuple[str, ...]
    test_modules: tuple[str, ...]
    test_suites: tuple[str, ...]
    checks: tuple[str, ...]
    browser_full: bool
    windows_full: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _normalized(paths: Iterable[str]) -> tuple[str, ...]:
    def normalize(path: str) -> str:
        value = str(path).strip().replace("\\", "/")
        while value.startswith("./"):
            value = value[2:]
        return value.lstrip("/")

    return tuple(
        sorted(
            {
                normalize(path)
                for path in paths
                if str(path).strip()
            }
        )
    )


def changed_files(
    base: str,
    *,
    include_worktree: bool,
    root: Path = ROOT,
) -> tuple[str, ...]:
    subprocess.run(
        ["git", "rev-parse", "--verify", f"{base}^{{commit}}"],
        cwd=root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    separator = "" if include_worktree else "...HEAD"
    output = subprocess.check_output(
        [
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            f"{base}{separator}",
        ],
        cwd=root,
        text=True,
        encoding="utf-8",
    ).splitlines()
    if include_worktree:
        output.extend(
            subprocess.check_output(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=root,
                text=True,
                encoding="utf-8",
            ).splitlines()
        )
    return _normalized(output)


def _matches(path: str, *needles: str) -> bool:
    return any(needle in path for needle in needles)


def classify_changes(
    paths: Sequence[str],
    *,
    labels: Sequence[str] = (),
) -> ImpactPlan:
    changed = _normalized(paths)
    normalized_labels = {label.casefold() for label in labels}
    suites: set[str] = set()
    modules: set[str] = set()
    checks = {"compile", "python-runtime", "repository"}

    for path in changed:
        semantic_path = path.removeprefix("mtg_commander_sim/")
        if path.startswith("tests/test_") and path.endswith(".py"):
            modules.add(Path(path).stem)
        if path.startswith(("mtg_commander_sim/", "server/", "scripts/")):
            checks.update({"architecture", "module-classifications"})
        if path.startswith(("docs/", "README.md", "AGENTS.md")):
            checks.add("documentation")
        if path.startswith(("rules/", "mechanics/")) or _matches(
            path,
            "rules_corpus",
            "rule_conformance",
            "rules_scheduler",
        ):
            checks.update({"rules", "rules-scheduler"})
        if path.startswith("coverage/") or path == "platform/readiness-source.json":
            checks.update({"architecture", "platform-status"})
        if _matches(path, "capability", "card_program", "oracle_ir"):
            checks.add("capability-evidence")
        if path.startswith(("platform/", ".github/")):
            checks.update(
                {
                    "architecture",
                    "documentation",
                    "module-classifications",
                    "test-shards",
                }
            )

        if path.startswith("mtg_commander_sim/compiler/") or _matches(
            semantic_path,
            "oracle_ir.py",
            "card_programs/",
            "preflight.py",
            "mechanic_contract",
        ):
            suites.add("compiler-cardprogram")
            checks.add("capability-evidence")
        elif _matches(
            semantic_path,
            "replacement",
            "damage_prevention",
            "damage_modifier",
            "counter_placement",
            "counter_state",
            "life_change",
            "life_state",
            "effect_runtime/life",
            "continuous_effect",
        ):
            suites.add("rules-events-replacements")
        elif _matches(
            semantic_path,
            "casting",
            "activation",
            "activated",
            "mana",
            "cost",
            "stack",
        ):
            suites.add("casting-costs-mana")
        elif _matches(
            semantic_path,
            "target",
            "choice",
            "semantic_handler",
            "semantic_search",
            "decision_opportun",
            "linked_abilit",
        ):
            suites.add("targets-choices-continuations")
        elif _matches(semantic_path, "turn_", "trigger", "phase", "step"):
            suites.add("triggers-turns-exact-decks")
        elif _matches(
            semantic_path, "declaration", "declare_attack", "declare_block"
        ):
            suites.add("combat-declarations")
        elif _matches(
            semantic_path,
            "combat",
            "state_based_action",
            "damage_results",
            "damage_result_",
        ):
            suites.add("state-actions-damage")
        elif _matches(
            semantic_path, "commander", "multiplayer", "monarch", "mulligan"
        ):
            suites.add("multiplayer-commander")
        elif path.startswith("server/") or _matches(
            semantic_path,
            "protocol",
            "projection",
            "record",
            "game_actor",
            "session.py",
            "service.py",
        ):
            suites.add("server-replay-privacy")
        elif path.startswith("mtg_commander_sim/"):
            suites.add("core-domain")

        if path.startswith(("scripts/", ".github/workflows/")):
            suites.add("generated-validation")
        if path.startswith("web/"):
            checks.add("browser-build")
            suites.add("server-replay-privacy")

    browser_full = "browser-full" in normalized_labels or any(
        path.startswith(("web/", "server/", ".github/workflows/"))
        or path.startswith("schemas/")
        or _matches(
            path,
            "protocol.py",
            "projection.py",
            "action",
            "choice",
            "room",
            "websocket",
        )
        for path in changed
    )
    windows_full = "windows-full" in normalized_labels or any(
        path.startswith(("server/", ".github/workflows/"))
        or path in {"pyproject.toml", "requirements-dev.txt"}
        or _matches(
            path,
            "bootstrap_windows",
            "subprocess",
            "launcher",
            "persistence",
            "record.py",
            "carddb.py",
            "bulk.py",
        )
        for path in changed
    )
    return ImpactPlan(
        changed_files=changed,
        test_modules=tuple(sorted(modules)),
        test_suites=tuple(sorted(suites)),
        checks=tuple(sorted(checks)),
        browser_full=browser_full,
        windows_full=windows_full,
    )


def github_event_labels(path: str | None = None) -> tuple[str, ...]:
    event_path = path or os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return ()
    value = json.loads(Path(event_path).read_text(encoding="utf-8"))
    labels = value.get("pull_request", {}).get("labels", [])
    return tuple(
        str(label.get("name"))
        for label in labels
        if isinstance(label, dict) and label.get("name")
    )


def github_base(path: str | None = None) -> str:
    event_path = path or os.environ.get("GITHUB_EVENT_PATH")
    if event_path:
        value = json.loads(Path(event_path).read_text(encoding="utf-8"))
        base = value.get("pull_request", {}).get("base", {}).get("sha")
        if base:
            return str(base)
    return "HEAD^"
