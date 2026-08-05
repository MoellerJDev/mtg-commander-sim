from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.change_impact import (
    changed_files,
    changed_python_symbols,
    classify_changes,
    github_base,
    github_event_labels,
)


def browser_matrix(browser_full: bool) -> dict:
    shards = (
        (
            {
                "shard": 1,
                "total": 2,
                "server_port": 18081,
                "web_port": 15171,
            },
            {
                "shard": 2,
                "total": 2,
                "server_port": 18082,
                "web_port": 15172,
            },
        )
        if browser_full
        else (
            {
                "shard": 1,
                "total": 1,
                "server_port": 18081,
                "web_port": 15171,
            },
        )
    )
    return {"include": list(shards)}


def _write_github_output(path: Path, plan: dict) -> None:
    values = {
        "browser_full": str(plan["browser_full"]).lower(),
        "browser_focus_grep": "|".join(plan["browser_focus_patterns"]),
        "windows_full": str(plan["windows_full"]).lower(),
        "changed_files": json.dumps(plan["changed_files"], separators=(",", ":")),
        "browser_matrix": json.dumps(
            browser_matrix(bool(plan["browser_full"])), separators=(",", ":")
        ),
    }
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        for key, value in values.items():
            stream.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify exact PR CI impact")
    parser.add_argument("--base")
    parser.add_argument("--event")
    parser.add_argument("--github-output")
    args = parser.parse_args()
    base = args.base or github_base(args.event)
    plan = classify_changes(
        changed_files(base, include_worktree=False),
        changed_symbols=changed_python_symbols(
            base,
            include_worktree=False,
        ),
        labels=github_event_labels(args.event),
    ).to_dict()
    output = args.github_output or os.environ.get("GITHUB_OUTPUT")
    if output:
        _write_github_output(Path(output), plan)
    print(json.dumps({"base": base, **plan}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
