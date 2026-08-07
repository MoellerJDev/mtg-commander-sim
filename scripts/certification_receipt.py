from __future__ import annotations

import argparse
from dataclasses import dataclass
import io
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import build_opener, HTTPRedirectHandler, Request
import zipfile

try:
    from scripts.source_tree_fingerprint import (
        SOURCE_TREE_FINGERPRINT_ALGORITHM,
        tracked_ref_source_fingerprint,
        tracked_worktree_source_fingerprint,
    )
except ModuleNotFoundError:  # Direct execution from scripts/.
    from source_tree_fingerprint import (  # type: ignore[no-redef]
        SOURCE_TREE_FINGERPRINT_ALGORITHM,
        tracked_ref_source_fingerprint,
        tracked_worktree_source_fingerprint,
    )


ROOT = Path(__file__).resolve().parents[1]
RECEIPT_SCHEMA_VERSION = 1
RECEIPT_FILENAME = "certification-receipt.json"
REQUIRED_CHECK_SUITE = frozenset(
    {
        "browser",
        "generated",
        "package",
        "plan",
        "python",
        "windows_certification",
    }
)
_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "repository",
        "pull_request",
        "exact_head_sha",
        "workflow_run_id",
        "workflow_name",
        "check_suite",
        "source_tree_fingerprint_algorithm",
        "source_tree_fingerprint",
    }
)
_SHA = re.compile(r"^[0-9a-f]{40}$")
_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")


class CertificationReceiptError(ValueError):
    """An exact-head certification receipt is missing, stale, or malformed."""


def _positive_integer(value: Any, *, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise CertificationReceiptError(f"{field} must be a positive integer")
    return value


def canonical_check_suite(needs: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(needs, Mapping) or set(needs) != REQUIRED_CHECK_SUITE:
        raise CertificationReceiptError(
            "Certification check suite must contain every required PR gate"
        )
    result: dict[str, str] = {}
    for name in sorted(REQUIRED_CHECK_SUITE):
        details = needs.get(name)
        if not isinstance(details, Mapping) or details.get("result") != "success":
            raise CertificationReceiptError(
                f"Certification gate {name!r} did not succeed"
            )
        result[name] = "success"
    return result


@dataclass(frozen=True, slots=True)
class CertificationReceipt:
    repository: str
    pull_request: int
    exact_head_sha: str
    workflow_run_id: int
    check_suite: tuple[tuple[str, str], ...]
    source_tree_fingerprint: str
    workflow_name: str = "PR"

    def __post_init__(self) -> None:
        if (
            type(self.repository) is not str
            or self.repository.count("/") != 1
            or not all(self.repository.split("/"))
        ):
            raise CertificationReceiptError(
                "repository must be an owner/name coordinate"
            )
        _positive_integer(self.pull_request, field="pull_request")
        _positive_integer(self.workflow_run_id, field="workflow_run_id")
        if type(self.exact_head_sha) is not str or not _SHA.fullmatch(
            self.exact_head_sha
        ):
            raise CertificationReceiptError(
                "exact_head_sha must be a lowercase full Git SHA"
            )
        if self.workflow_name != "PR":
            raise CertificationReceiptError("workflow_name must identify PR CI")
        suite = dict(self.check_suite)
        if len(suite) != len(self.check_suite):
            raise CertificationReceiptError("check_suite contains duplicate gates")
        canonical_check_suite(
            {name: {"result": result} for name, result in suite.items()}
        )
        if (
            type(self.source_tree_fingerprint) is not str
            or not _FINGERPRINT.fullmatch(self.source_tree_fingerprint)
        ):
            raise CertificationReceiptError(
                "source_tree_fingerprint must be a lowercase SHA-256 value"
            )
        object.__setattr__(self, "check_suite", tuple(sorted(suite.items())))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "repository": self.repository,
            "pull_request": self.pull_request,
            "exact_head_sha": self.exact_head_sha,
            "workflow_run_id": self.workflow_run_id,
            "workflow_name": self.workflow_name,
            "check_suite": dict(self.check_suite),
            "source_tree_fingerprint_algorithm": (
                SOURCE_TREE_FINGERPRINT_ALGORITHM
            ),
            "source_tree_fingerprint": self.source_tree_fingerprint,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CertificationReceipt":
        if not isinstance(value, Mapping) or set(value) != _RECEIPT_FIELDS:
            raise CertificationReceiptError(
                "Certification receipt fields are incomplete or unknown"
            )
        if value.get("schema_version") != RECEIPT_SCHEMA_VERSION:
            raise CertificationReceiptError(
                "Certification receipt schema version is unsupported"
            )
        if (
            value.get("source_tree_fingerprint_algorithm")
            != SOURCE_TREE_FINGERPRINT_ALGORITHM
        ):
            raise CertificationReceiptError(
                "Certification receipt fingerprint algorithm is unsupported"
            )
        suite = value.get("check_suite")
        if not isinstance(suite, Mapping):
            raise CertificationReceiptError("check_suite must be an object")
        return cls(
            repository=value.get("repository"),
            pull_request=value.get("pull_request"),
            exact_head_sha=value.get("exact_head_sha"),
            workflow_run_id=value.get("workflow_run_id"),
            workflow_name=value.get("workflow_name"),
            check_suite=tuple(suite.items()),
            source_tree_fingerprint=value.get("source_tree_fingerprint"),
        )


def build_receipt(
    *,
    repository: str,
    pull_request: int,
    exact_head_sha: str,
    workflow_run_id: int,
    needs: Mapping[str, Any],
    root: Path = ROOT,
) -> CertificationReceipt:
    suite = canonical_check_suite(needs)
    return CertificationReceipt(
        repository=repository,
        pull_request=pull_request,
        exact_head_sha=exact_head_sha,
        workflow_run_id=workflow_run_id,
        check_suite=tuple(suite.items()),
        source_tree_fingerprint=tracked_ref_source_fingerprint(
            root, exact_head_sha
        ),
    )


def validate_receipt(
    receipt: CertificationReceipt,
    *,
    repository: str,
    pull_request: int,
    exact_head_sha: str,
    workflow_run_id: int,
    evaluated_source_tree_fingerprint: str,
) -> None:
    expected = {
        "repository": repository,
        "pull_request": pull_request,
        "exact_head_sha": exact_head_sha,
        "workflow_run_id": workflow_run_id,
    }
    for field, value in expected.items():
        if getattr(receipt, field) != value:
            raise CertificationReceiptError(
                f"Certification receipt {field} does not match GitHub"
            )
    if receipt.source_tree_fingerprint != evaluated_source_tree_fingerprint:
        raise CertificationReceiptError(
            "Current main source tree is not equivalent to the certified PR head"
        )


def select_merged_pull_request(value: Any, *, merge_sha: str) -> Mapping[str, Any]:
    if not isinstance(value, list):
        raise CertificationReceiptError(
            "GitHub associated-pull-request response is malformed"
        )
    candidates = [
        row
        for row in value
        if isinstance(row, Mapping)
        and row.get("state") == "closed"
        and row.get("merged_at")
        and row.get("merge_commit_sha") == merge_sha
    ]
    if len(candidates) != 1:
        raise CertificationReceiptError(
            "Current main commit must identify exactly one merged pull request"
        )
    return candidates[0]


def successful_pr_runs(value: Any, *, exact_head_sha: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Mapping) or not isinstance(
        value.get("workflow_runs"), list
    ):
        raise CertificationReceiptError("GitHub workflow-run response is malformed")
    candidates = [
        row
        for row in value["workflow_runs"]
        if isinstance(row, Mapping)
        and row.get("event") == "pull_request"
        and row.get("head_sha") == exact_head_sha
        and row.get("name") == "PR"
        and row.get("path") == ".github/workflows/ci.yml"
        and type(row.get("id")) is int
    ]
    return tuple(sorted(candidates, key=lambda row: int(row["id"]), reverse=True))


def select_receipt_artifact(value: Any, *, workflow_run_id: int) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not isinstance(value.get("artifacts"), list):
        raise CertificationReceiptError("GitHub artifact response is malformed")
    expected_name = f"exact-head-certification-{workflow_run_id}"
    candidates = [
        row
        for row in value["artifacts"]
        if isinstance(row, Mapping)
        and row.get("name") == expected_name
        and row.get("expired") is False
        and isinstance(row.get("archive_download_url"), str)
    ]
    if len(candidates) != 1:
        raise CertificationReceiptError(
            "Successful PR run has no unique live certification receipt"
        )
    return candidates[0]


def receipt_from_archive(raw: bytes) -> CertificationReceipt:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            if names != [RECEIPT_FILENAME]:
                raise CertificationReceiptError(
                    "Certification artifact must contain only the canonical receipt"
                )
            value = json.loads(archive.read(RECEIPT_FILENAME).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise CertificationReceiptError(
            "Certification artifact is malformed"
        ) from exc
    return CertificationReceipt.from_dict(value)


class _CertificationRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        file_pointer: Any,
        code: int,
        message: str,
        headers: Any,
        new_url: str,
    ) -> Request | None:
        redirected = super().redirect_request(
            request, file_pointer, code, message, headers, new_url
        )
        if (
            redirected is not None
            and urlparse(request.full_url).netloc
            != urlparse(new_url).netloc
        ):
            redirected.remove_header("Authorization")
        return redirected


def _github_request(url: str, token: str) -> bytes:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "quorune-certification",
        },
    )
    try:
        with build_opener(_CertificationRedirectHandler()).open(
            request, timeout=30
        ) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise CertificationReceiptError(
            "GitHub certification evidence could not be retrieved"
        ) from exc


def _github_json(url: str, token: str) -> Any:
    try:
        return json.loads(_github_request(url, token).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CertificationReceiptError("GitHub returned malformed JSON") from exc


def verify_main_certification(
    *,
    repository: str,
    merge_sha: str,
    token: str,
    root: Path = ROOT,
) -> CertificationReceipt:
    if not _SHA.fullmatch(merge_sha):
        raise CertificationReceiptError("merge_sha must be a lowercase full Git SHA")
    api = f"https://api.github.com/repos/{repository}"
    pull_request = select_merged_pull_request(
        _github_json(f"{api}/commits/{merge_sha}/pulls", token),
        merge_sha=merge_sha,
    )
    pull_request_number = _positive_integer(
        pull_request.get("number"), field="pull request number"
    )
    head = pull_request.get("head")
    exact_head_sha = head.get("sha") if isinstance(head, Mapping) else None
    if type(exact_head_sha) is not str or not _SHA.fullmatch(exact_head_sha):
        raise CertificationReceiptError(
            "Merged pull request has no exact head SHA"
        )
    last_error: CertificationReceiptError | None = None
    for attempt in range(5):
        runs = successful_pr_runs(
            _github_json(
                f"{api}/actions/workflows/ci.yml/runs?event=pull_request"
                f"&head_sha={quote(exact_head_sha)}&per_page=100",
                token,
            ),
            exact_head_sha=exact_head_sha,
        )
        if not runs:
            last_error = CertificationReceiptError(
                "Merged pull request has no exact-head PR workflow"
            )
        for run in runs:
            run_id = int(run["id"])
            try:
                artifact = select_receipt_artifact(
                    _github_json(
                        f"{api}/actions/runs/{run_id}/artifacts?per_page=100",
                        token,
                    ),
                    workflow_run_id=run_id,
                )
                receipt = receipt_from_archive(
                    _github_request(str(artifact["archive_download_url"]), token)
                )
                validate_receipt(
                    receipt,
                    repository=repository,
                    pull_request=pull_request_number,
                    exact_head_sha=exact_head_sha,
                    workflow_run_id=run_id,
                    evaluated_source_tree_fingerprint=(
                        tracked_worktree_source_fingerprint(root)
                    ),
                )
                return receipt
            except CertificationReceiptError as exc:
                last_error = exc
        if attempt < 4:
            time.sleep(2)
    raise last_error or CertificationReceiptError(
        "No successful PR run supplied a valid certification receipt"
    )


def _read_needs(raw: str) -> Mapping[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CertificationReceiptError("CI needs JSON is malformed") from exc
    if not isinstance(value, Mapping):
        raise CertificationReceiptError("CI needs JSON must be an object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="operation", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--repository", required=True)
    create.add_argument("--pull-request", type=int, required=True)
    create.add_argument("--exact-head-sha", required=True)
    create.add_argument("--workflow-run-id", type=int, required=True)
    create.add_argument("--needs-json", required=True)
    create.add_argument("--output", required=True)
    verify = subparsers.add_parser("verify-main")
    verify.add_argument("--repository", required=True)
    verify.add_argument("--merge-sha", required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == "create":
            receipt = build_receipt(
                repository=args.repository,
                pull_request=args.pull_request,
                exact_head_sha=args.exact_head_sha,
                workflow_run_id=args.workflow_run_id,
                needs=_read_needs(args.needs_json),
            )
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(receipt.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            print(json.dumps(receipt.to_dict(), sort_keys=True))
            return 0
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            raise CertificationReceiptError(
                "GH_TOKEN or GITHUB_TOKEN is required"
            )
        receipt = verify_main_certification(
            repository=args.repository,
            merge_sha=args.merge_sha,
            token=token,
        )
        print(json.dumps(receipt.to_dict(), sort_keys=True))
        return 0
    except CertificationReceiptError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
