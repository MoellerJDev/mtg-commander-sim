from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Mapping, Sequence


def _time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _duration(start: str | None, end: str | None) -> float | None:
    started = _time(start)
    completed = _time(end)
    if started is None or completed is None:
        return None
    return round((completed - started).total_seconds(), 3)


def build_metrics(run: Mapping, jobs_document: Mapping) -> dict:
    jobs = jobs_document.get("jobs")
    if not isinstance(jobs, Sequence):
        raise ValueError("Jobs document must contain a jobs list")
    rows = []
    for job in jobs:
        if not isinstance(job, Mapping):
            raise ValueError("Every jobs entry must be an object")
        rows.append(
            {
                "name": str(job.get("name") or "unknown"),
                "conclusion": job.get("conclusion"),
                "started_at": job.get("started_at"),
                "completed_at": job.get("completed_at"),
                "duration_seconds": _duration(
                    job.get("started_at"), job.get("completed_at")
                ),
            }
        )
    created = _time(str(run.get("created_at") or ""))
    starts = [_time(row["started_at"]) for row in rows]
    starts = [value for value in starts if value is not None]
    completions = [_time(row["completed_at"]) for row in rows]
    completions = [value for value in completions if value is not None]
    queue = (
        round((min(starts) - created).total_seconds(), 3)
        if created is not None and starts
        else None
    )
    critical = (
        round((max(completions) - created).total_seconds(), 3)
        if created is not None and completions
        else None
    )
    return {
        "schema_version": 1,
        "run_id": run.get("id"),
        "head_sha": run.get("head_sha"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "queue_seconds": queue,
        "critical_path_seconds_observed": critical,
        "cache_hit_rate": None,
        "agent_idle_seconds": None,
        "stale_run_cancellation_count": None,
        "jobs": sorted(rows, key=lambda row: row["name"]),
    }


def markdown(metrics: Mapping) -> str:
    lines = [
        "## CI duration report",
        "",
        f"- Queue: {metrics['queue_seconds']} seconds",
        f"- Observed critical path: {metrics['critical_path_seconds_observed']} seconds",
        "- Cache-hit rate: unavailable from the jobs API (not estimated)",
        "- Agent idle time: unavailable from GitHub Actions (not estimated)",
        "- Stale-run cancellation count: unavailable per run (not estimated)",
        "",
        "| Job | Conclusion | Duration (seconds) |",
        "|---|---|---:|",
    ]
    for row in metrics["jobs"]:
        lines.append(
            f"| {row['name']} | {row['conclusion']} | {row['duration_seconds']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize GitHub Actions timing")
    parser.add_argument("--run-json", required=True)
    parser.add_argument("--jobs-json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary")
    args = parser.parse_args()
    run = json.loads(Path(args.run_json).read_text(encoding="utf-8"))
    jobs = json.loads(Path(args.jobs_json).read_text(encoding="utf-8"))
    metrics = build_metrics(run, jobs)
    Path(args.output).write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if args.summary:
        with Path(args.summary).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(markdown(metrics))
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
