from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "platform" / "documentation-policy.json"
FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
FENCE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
ADR_FILE = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")
COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ][0-9:.+\-Z]+)?$")


def load_policy(path: Path = POLICY_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_front_matter(text: str) -> dict[str, str]:
    match = FRONT_MATTER.match(text.replace("\r\n", "\n"))
    if not match:
        return {}
    metadata: dict[str, str] = {}
    for raw in match.group(1).splitlines():
        if not raw.strip() or raw.lstrip().startswith("#") or ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata


def discover_documents(root: Path, policy: dict) -> list[Path]:
    paths = {
        path.resolve()
        for pattern in policy["document_globs"]
        for path in root.glob(pattern)
        if path.is_file()
    }
    tracked = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=root,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if tracked.returncode == 0:
        paths.update(
            (root / relative).resolve()
            for relative in tracked.stdout.splitlines()
            if relative and (root / relative).is_file()
        )
    excluded = tuple(policy.get("excluded_prefixes", []))
    return sorted(
        path
        for path in paths
        if not path.relative_to(root).as_posix().startswith(excluded)
    )


def _verified_value_valid(metadata: dict[str, str]) -> bool:
    value = metadata.get("verified", "")
    return bool(COMMIT.fullmatch(value) or TIMESTAMP.fullmatch(value))


def metadata_failures(
    root: Path, paths: list[Path], policy: dict
) -> list[str]:
    failures: list[str] = []
    required = set(policy["required_metadata"])
    statuses = set(policy["statuses"])
    modes = set(policy["maintenance_modes"])
    for path in paths:
        relative = path.relative_to(root).as_posix()
        metadata = parse_front_matter(path.read_text(encoding="utf-8"))
        missing = sorted(required - metadata.keys())
        if missing:
            failures.append(f"{relative}: missing metadata {missing}")
            continue
        if metadata["status"] not in statuses:
            failures.append(f"{relative}: invalid status {metadata['status']!r}")
        if metadata["maintenance"] not in modes:
            failures.append(
                f"{relative}: invalid maintenance {metadata['maintenance']!r}"
            )
        expected = "generated" if metadata["status"] == "generated" else "hand-maintained"
        if metadata["maintenance"] != expected:
            failures.append(
                f"{relative}: status {metadata['status']!r} requires {expected!r} maintenance"
            )
        if not _verified_value_valid(metadata):
            failures.append(f"{relative}: verified must be a commit or timestamp")
    return failures


def _without_fences(text: str) -> str:
    return FENCE.sub("", text)


def _slug(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value).strip().lower()
    value = re.sub(r"[^\w\- ]", "", value, flags=re.UNICODE)
    return re.sub(r"[\s-]+", "-", value).strip("-")


def _anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for heading in HEADING.findall(_without_fences(path.read_text(encoding="utf-8"))):
        base = _slug(heading)
        index = counts.get(base, 0)
        anchors.add(base if index == 0 else f"{base}-{index}")
        counts[base] = index + 1
    return anchors


def _link_target(source: Path, raw: str, root: Path) -> tuple[Path, str] | None:
    value = raw.strip().strip("<>")
    if not value or value.startswith(("http://", "https://", "mailto:", "data:")):
        return None
    if value.startswith(("/api/", "ws://", "wss://")) or any(char in value for char in "{}*$"):
        return None
    location, _, fragment = value.partition("#")
    location = unquote(location.split("?", 1)[0])
    target = source if not location else (source.parent / location).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return Path("__outside_repository__"), fragment
    return target, unquote(fragment)


def link_failures(root: Path, paths: list[Path]) -> list[str]:
    failures: list[str] = []
    for source in paths:
        text = _without_fences(source.read_text(encoding="utf-8"))
        for raw in LINK.findall(text):
            resolved = _link_target(source, raw, root)
            if resolved is None:
                continue
            target, fragment = resolved
            relative = source.relative_to(root).as_posix()
            if not target.exists():
                failures.append(f"{relative}: broken link {raw!r}")
            elif fragment and target.is_file() and _slug(fragment) not in _anchors(target):
                failures.append(f"{relative}: missing anchor {raw!r}")
    return failures


def stale_claim_failures(
    root: Path, paths: list[Path], policy: dict
) -> list[str]:
    patterns = [
        (
            entry["name"],
            re.compile(entry["pattern"]),
            set(entry.get("excluded_documents", [])),
        )
        for entry in policy["stale_claim_patterns"]
    ]
    failures: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        metadata = parse_front_matter(text)
        if metadata.get("status") in {"generated", "historical"}:
            continue
        body = _without_fences(FRONT_MATTER.sub("", text, count=1))
        relative = path.relative_to(root).as_posix()
        for name, pattern, excluded in patterns:
            if relative in excluded:
                continue
            match = pattern.search(body)
            if match:
                failures.append(f"{relative}: duplicates generated {name}: {match.group(0)!r}")
        pr_references = re.findall(
            r"(?i)\bPRs?\s*#\d+|github\.com/[^\s)]+/pull/\d+",
            body,
        )
        has_pr_ledger = bool(
            re.search(
                r"(?im)^#{2,6}\s+pull requests?\s*$|^\|\s*PR\s*\|",
                body,
            )
        )
        if len(pr_references) > 1 or has_pr_ledger:
            failures.append(f"{relative}: current guidance contains PR history")
    return failures


def index_failures(root: Path, paths: list[Path]) -> list[str]:
    index = root / "docs" / "index.md"
    if not index.is_file():
        return ["docs/index.md: authoritative documentation map is missing"]
    linked: set[Path] = set()
    for raw in LINK.findall(_without_fences(index.read_text(encoding="utf-8"))):
        resolved = _link_target(index, raw, root)
        if resolved is not None:
            linked.add(resolved[0])
    missing = [
        path.relative_to(root).as_posix()
        for path in paths
        if path != index and path not in linked
    ]
    return [f"docs/index.md: unindexed document {path}" for path in missing]


def adr_failures(root: Path, policy: dict) -> list[str]:
    directory = root / "docs" / "adr"
    index = directory / "index.md"
    if not index.is_file():
        return ["docs/adr/index.md: ADR index is missing"]
    index_text = _without_fences(index.read_text(encoding="utf-8"))
    failures: list[str] = []
    ids: set[str] = set()
    for path in sorted(directory.glob("[0-9][0-9][0-9][0-9]-*.md")):
        match = ADR_FILE.fullmatch(path.name)
        if match is None:
            continue
        metadata = parse_front_matter(path.read_text(encoding="utf-8"))
        adr_id = metadata.get("adr_id", "")
        if adr_id != match.group(1) or adr_id in ids:
            failures.append(f"{path.relative_to(root).as_posix()}: invalid or duplicate adr_id")
        ids.add(adr_id)
        if metadata.get("status") != "ADR":
            failures.append(f"{path.relative_to(root).as_posix()}: status must be ADR")
        if metadata.get("decision_status") not in policy["adr_decision_statuses"]:
            failures.append(f"{path.relative_to(root).as_posix()}: invalid decision_status")
        if not TIMESTAMP.fullmatch(metadata.get("date", "")):
            failures.append(f"{path.relative_to(root).as_posix()}: invalid ADR date")
        headings = {_slug(value) for value in HEADING.findall(path.read_text(encoding="utf-8"))}
        for required in {"context", "decision", "alternatives", "consequences"} - headings:
            failures.append(f"{path.relative_to(root).as_posix()}: missing {required!r} heading")
        if path.name not in index_text:
            failures.append(f"docs/adr/index.md: missing {path.name}")
    return failures


def validate(root: Path = ROOT, policy_path: Path = POLICY_PATH) -> list[str]:
    policy = load_policy(policy_path)
    paths = discover_documents(root, policy)
    return [
        *metadata_failures(root, paths, policy),
        *link_failures(root, paths),
        *stale_claim_failures(root, paths, policy),
        *index_failures(root, paths),
        *adr_failures(root, policy),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    failures = validate()
    if failures:
        raise ValueError("\n".join(sorted(set(failures))))
    print(json.dumps({"ok": True, "documentation_policy": "pass"}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"documentation validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
