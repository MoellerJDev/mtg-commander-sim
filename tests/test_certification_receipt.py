from __future__ import annotations

import io
import json
from pathlib import Path
import unittest
import zipfile

from scripts.certification_receipt import (
    CertificationReceipt,
    CertificationReceiptError,
    RECEIPT_FILENAME,
    REQUIRED_CHECK_SUITE,
    canonical_check_suite,
    receipt_from_archive,
    select_merged_pull_request,
    select_receipt_artifact,
    successful_pr_runs,
    validate_receipt,
)
from scripts.source_tree_fingerprint import (
    tracked_ref_source_fingerprint,
    tracked_worktree_source_fingerprint,
)


ROOT = Path(__file__).resolve().parents[1]


def required_needs() -> dict[str, dict[str, str]]:
    return {
        name: {"result": "success"}
        for name in REQUIRED_CHECK_SUITE
    }


def receipt() -> CertificationReceipt:
    return CertificationReceipt(
        repository="MoellerJDev/mtg-commander-sim",
        pull_request=132,
        exact_head_sha="a" * 40,
        workflow_run_id=12345,
        check_suite=tuple(canonical_check_suite(required_needs()).items()),
        source_tree_fingerprint="b" * 64,
    )


class CertificationReceiptTests(unittest.TestCase):
    def test_squash_equivalent_source_tree_remains_certified(self):
        value = receipt()
        validate_receipt(
            value,
            repository=value.repository,
            pull_request=value.pull_request,
            exact_head_sha=value.exact_head_sha,
            workflow_run_id=value.workflow_run_id,
            evaluated_source_tree_fingerprint=value.source_tree_fingerprint,
        )

    def test_materially_changed_source_tree_is_not_certified(self):
        value = receipt()
        with self.assertRaisesRegex(CertificationReceiptError, "not equivalent"):
            validate_receipt(
                value,
                repository=value.repository,
                pull_request=value.pull_request,
                exact_head_sha=value.exact_head_sha,
                workflow_run_id=value.workflow_run_id,
                evaluated_source_tree_fingerprint="c" * 64,
            )

    def test_stale_or_mismatched_receipt_fails_closed(self):
        value = receipt()
        for field, replacement in (
            ("repository", "other/repository"),
            ("pull_request", 999),
            ("exact_head_sha", "c" * 40),
            ("workflow_run_id", 999),
        ):
            arguments = {
                "repository": value.repository,
                "pull_request": value.pull_request,
                "exact_head_sha": value.exact_head_sha,
                "workflow_run_id": value.workflow_run_id,
                "evaluated_source_tree_fingerprint": value.source_tree_fingerprint,
            }
            arguments[field] = replacement
            with self.subTest(field=field):
                with self.assertRaisesRegex(CertificationReceiptError, field):
                    validate_receipt(value, **arguments)

        malformed = value.to_dict()
        malformed["unknown"] = True
        with self.assertRaisesRegex(CertificationReceiptError, "unknown"):
            CertificationReceipt.from_dict(malformed)

    def test_required_ci_check_suite_cannot_be_weakened(self):
        for missing in sorted(REQUIRED_CHECK_SUITE):
            needs = required_needs()
            needs.pop(missing)
            with self.subTest(missing=missing):
                with self.assertRaisesRegex(CertificationReceiptError, "every required"):
                    canonical_check_suite(needs)

        needs = required_needs()
        needs["generated"]["result"] = "skipped"
        with self.assertRaisesRegex(CertificationReceiptError, "did not succeed"):
            canonical_check_suite(needs)

    def test_current_clean_tree_matches_its_committed_head_without_self_reference(self):
        self.assertEqual(
            tracked_ref_source_fingerprint(ROOT, "HEAD"),
            tracked_worktree_source_fingerprint(ROOT),
        )

    def test_github_merge_run_and_artifact_selection_is_strict(self):
        pull = select_merged_pull_request(
            [
                {
                    "number": 132,
                    "state": "closed",
                    "merged_at": "2026-08-07T00:00:00Z",
                    "merge_commit_sha": "d" * 40,
                    "head": {"sha": "a" * 40},
                }
            ],
            merge_sha="d" * 40,
        )
        self.assertEqual(132, pull["number"])
        runs = successful_pr_runs(
            {
                "workflow_runs": [
                    {
                        "id": 12345,
                        "event": "pull_request",
                        "head_sha": "a" * 40,
                        "conclusion": "success",
                        "name": "PR",
                        "path": ".github/workflows/ci.yml",
                    },
                    {
                        "id": 99999,
                        "event": "push",
                        "head_sha": "a" * 40,
                        "conclusion": "success",
                        "name": "PR",
                        "path": ".github/workflows/ci.yml",
                    },
                ]
            },
            exact_head_sha="a" * 40,
        )
        self.assertEqual([12345], [row["id"] for row in runs])
        artifact = select_receipt_artifact(
            {
                "artifacts": [
                    {
                        "name": "exact-head-certification-12345",
                        "expired": False,
                        "archive_download_url": "https://example.invalid/receipt",
                    }
                ]
            },
            workflow_run_id=12345,
        )
        self.assertEqual(
            "https://example.invalid/receipt",
            artifact["archive_download_url"],
        )

    def test_artifact_archive_requires_one_canonical_receipt(self):
        expected = receipt()
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr(
                RECEIPT_FILENAME,
                json.dumps(expected.to_dict(), sort_keys=True),
            )
        self.assertEqual(expected, receipt_from_archive(stream.getvalue()))

        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr(RECEIPT_FILENAME, "{}")
            archive.writestr("extra.txt", "unexpected")
        with self.assertRaisesRegex(CertificationReceiptError, "only"):
            receipt_from_archive(stream.getvalue())

    def test_workflow_preserves_required_gates_and_publishes_receipt(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        certification = workflow.split("  certification:\n", 1)[1].split(
            "\n  metrics:\n", 1
        )[0]
        self.assertIn(
            "needs: [plan, python, generated, package, windows_certification, browser]",
            certification,
        )
        self.assertIn("python scripts/verify_ci_needs.py", certification)
        self.assertIn("certification_receipt.py create", certification)
        self.assertIn("actions/upload-artifact@v4", certification)


if __name__ == "__main__":
    unittest.main()
