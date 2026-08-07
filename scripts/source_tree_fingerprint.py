from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess


SOURCE_TREE_FINGERPRINT_ALGORITHM = "tracked-git-clean-blobs-sha256-v3"
TRACKED_PLATFORM_OUTPUTS = frozenset(
    {
        "coverage/platform-readiness.json",
        "coverage/platform-readiness.md",
        "docs/PLATFORM_IMPLEMENTATION_STATUS.md",
    }
)


def _git(root: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def is_generated_report(
    relative: str,
    path: Path | None = None,
    *,
    markdown_prefix: str | None = None,
) -> bool:
    if relative in TRACKED_PLATFORM_OUTPUTS or relative.startswith("coverage/"):
        return True
    if relative == "platform/card-name-hash-index.json":
        return True
    if Path(relative).suffix.lower() != ".md":
        return False
    if markdown_prefix is None:
        if path is None:
            return False
        try:
            markdown_prefix = path.read_text(encoding="utf-8")[:512]
        except UnicodeDecodeError:
            return False
    return bool(
        re.search(
            r"(?m)^status:\s*[\"']?generated[\"']?\s*$",
            markdown_prefix[:512],
        )
    )


def canonical_tracked_blob_oids(
    root: Path,
    relative_paths: list[str],
) -> list[str]:
    """Return Git-clean blob identities for current tracked files."""

    if any("\n" in path or "\r" in path for path in relative_paths):
        raise ValueError("tracked source paths containing newlines are unsupported")
    if not relative_paths:
        return []
    output = _git(
        root,
        "hash-object",
        "--filters",
        "--stdin-paths",
        input_bytes=("\n".join(relative_paths) + "\n").encode("utf-8"),
    )
    blob_oids = output.decode("ascii", errors="strict").splitlines()
    if len(blob_oids) != len(relative_paths):
        raise RuntimeError("git hash-object returned an incomplete tracked blob set")
    return blob_oids


def _fingerprint(entries: list[tuple[str, str]]) -> str:
    digest = hashlib.sha256()
    digest.update((SOURCE_TREE_FINGERPRINT_ALGORITHM + "\0").encode("ascii"))
    for relative, blob_oid in entries:
        path_bytes = relative.encode("utf-8")
        blob_bytes = blob_oid.encode("ascii")
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(blob_bytes).to_bytes(8, "big"))
        digest.update(blob_bytes)
    return digest.hexdigest()


def tracked_worktree_source_fingerprint(root: Path) -> str:
    """Fingerprint canonical tracked working-tree blobs.

    Generated reports are excluded so a tracked report never needs to predict
    the commit that will contain it.
    """

    output = _git(root, "ls-files", "-z")
    relative_paths = sorted(
        path.decode("utf-8", errors="strict")
        for path in output.split(b"\0")
        if path
    )
    included = [
        relative
        for relative in relative_paths
        if not is_generated_report(relative, root / relative)
    ]
    return _fingerprint(
        list(
            zip(
                included,
                canonical_tracked_blob_oids(root, included),
                strict=True,
            )
        )
    )


def _ref_entries(root: Path, ref: str) -> list[tuple[str, str]]:
    output = _git(root, "ls-tree", "-r", "-z", "--full-tree", ref)
    entries: list[tuple[str, str]] = []
    for raw in output.split(b"\0"):
        if not raw:
            continue
        metadata, raw_path = raw.split(b"\t", 1)
        _, object_type, raw_oid = metadata.split(b" ", 2)
        if object_type != b"blob":
            continue
        entries.append(
            (
                raw_path.decode("utf-8", errors="strict"),
                raw_oid.decode("ascii", errors="strict"),
            )
        )
    return sorted(entries)


def tracked_ref_source_fingerprint(root: Path, ref: str) -> str:
    """Fingerprint the tracked source blobs committed at ``ref``."""

    included: list[tuple[str, str]] = []
    for relative, blob_oid in _ref_entries(root, ref):
        prefix: str | None = None
        if Path(relative).suffix.lower() == ".md" and not (
            relative in TRACKED_PLATFORM_OUTPUTS
            or relative.startswith("coverage/")
        ):
            raw = _git(root, "show", f"{ref}:{relative}")[:512]
            try:
                prefix = raw.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                prefix = ""
        if not is_generated_report(relative, markdown_prefix=prefix):
            included.append((relative, blob_oid))
    return _fingerprint(included)


__all__ = [
    "SOURCE_TREE_FINGERPRINT_ALGORITHM",
    "TRACKED_PLATFORM_OUTPUTS",
    "canonical_tracked_blob_oids",
    "is_generated_report",
    "tracked_ref_source_fingerprint",
    "tracked_worktree_source_fingerprint",
]
