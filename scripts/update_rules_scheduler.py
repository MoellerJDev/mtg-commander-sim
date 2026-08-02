from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mtg_commander_sim.rules_scheduler import (
    build_rules_dependency_queue_from_root,
)
from mtg_commander_sim.util import stable_json


JSON_OUTPUT = ROOT / "coverage" / "rules-dependency-queue.json"
MARKDOWN_OUTPUT = ROOT / "docs" / "RULES_DEPENDENCY_QUEUE.md"


def _json_text(value: Mapping[str, Any]) -> str:
    return stable_json(value) + "\n"


def _markdown(value: Mapping[str, Any]) -> str:
    summary = value["summary"]
    selected = value["selected_batch"]
    lines = [
        "---",
        'title: "Rules dependency queue"',
        'status: "generated"',
        (
            'authoritative_source: '
            '"coverage/rules-dependency-queue.json"'
        ),
        f'verified: "{value["effective_date"]}"',
        'audience: "rules, compiler, and engine contributors"',
        'maintenance: "generated"',
        "---",
        "",
        "# Rules dependency queue",
        "",
        "This report schedules the pinned Comprehensive Rules by coupled "
        "subsystem. It does not claim that an unreviewed rule is behavioral; "
        "it conservatively keeps that rule queued until review proves "
        "otherwise.",
        "",
        "## Queue boundary",
        "",
        f'- Pinned rules: {summary["total_rules"]:,}',
        f'- Queued rules: {summary["queued_rules"]:,}',
        (
            "- Reviewed behavioral blockers: "
            f'{summary["reviewed_behavioral_blocked"]:,}'
        ),
        (
            "- Behavioral classification/review required: "
            f'{summary["behavioral_review_required"]:,}'
        ),
        f'- Passing behavioral rules: {summary["passing_behavioral"]:,}',
        f'- Subsystems: {summary["subsystem_count"]}',
        f'- Queue fingerprint: `{value["fingerprint"]}`',
        "",
        "## Selected next batch",
        "",
        f'- Batch: `{selected["batch_id"]}`',
        f'- Subsystem: `{selected["subsystem_id"]}`',
        "- Rules: "
        + ", ".join(f'`{rule_id}`' for rule_id in selected["rule_ids"]),
        "- Target capabilities: "
        + ", ".join(
            f'`{capability_id}`'
            for capability_id in selected["target_capability_ids"]
        ),
        f'- Rationale: {selected["rationale"]}',
        "",
        "Exit criteria:",
        "",
    ]
    lines.extend(
        f"- {criterion}" for criterion in selected["exit_criteria"]
    )
    lines.extend(
        [
            "",
            "## Dependency schedule",
            "",
            (
                "| Order | Subsystem | Dependencies | Queued | Reviewed "
                "blocked | Review required | Compiler impact |"
            ),
            "|---:|---|---|---:|---:|---:|---|",
        ]
    )
    for subsystem in value["subsystems"]:
        counts = subsystem["conformance_status_counts"]
        classifications = subsystem["classification_counts"]
        lines.append(
            "| "
            + " | ".join(
                [
                    str(subsystem["schedule_order"]),
                    f'`{subsystem["subsystem_id"]}`',
                    ", ".join(
                        f'`{dependency}`'
                        for dependency in subsystem[
                            "depends_on_subsystems"
                        ]
                    )
                    or "—",
                    str(subsystem["queued_rule_count"]),
                    str(counts.get("blocked", 0)),
                    str(classifications.get("unclassified", 0)),
                    ", ".join(
                        f'`{impact}`'
                        for impact in subsystem["compiler_impact"]
                    ),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Commands",
            "",
            "```bash",
            "python scripts/update_rules_scheduler.py --check",
            "python simctl.py rules queue --root .",
            "python simctl.py rules next --root . --limit 20",
            "```",
            "",
            "`rules next` returns the source-selected subsystem batch. "
            "Changing that selection requires changing the machine-readable "
            "catalog and regenerating this report; it is not a numerical "
            "walk through rule IDs.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    value = build_rules_dependency_queue_from_root(ROOT)
    expected_json = _json_text(value)
    expected_markdown = _markdown(value)
    if args.write:
        JSON_OUTPUT.write_text(
            expected_json, encoding="utf-8", newline="\n"
        )
        MARKDOWN_OUTPUT.write_text(
            expected_markdown, encoding="utf-8", newline="\n"
        )
        return 0
    stale = []
    for path, expected in (
        (JSON_OUTPUT, expected_json),
        (MARKDOWN_OUTPUT, expected_markdown),
    ):
        actual = path.read_text(encoding="utf-8") if path.exists() else ""
        if actual != expected:
            stale.append(path.relative_to(ROOT).as_posix())
    if stale:
        print(
            "Rules scheduler outputs are stale; run "
            "python scripts/update_rules_scheduler.py --write: "
            + ", ".join(stale),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
