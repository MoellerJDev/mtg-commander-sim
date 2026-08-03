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
    classify_changes,
    github_base,
    github_event_labels,
)


def _write_github_output(path: Path, plan: dict) -> None:
    values = {
        "browser_full": str(plan["browser_full"]).lower(),
        "windows_full": str(plan["windows_full"]).lower(),
        "changed_files": json.dumps(plan["changed_files"], separators=(",", ":")),
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
        labels=github_event_labels(args.event),
    ).to_dict()
    output = args.github_output or os.environ.get("GITHUB_OUTPUT")
    if output:
        _write_github_output(Path(output), plan)
    print(json.dumps({"base": base, **plan}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
