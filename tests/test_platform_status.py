from __future__ import annotations

import json
import subprocess
import sys
import unittest
from unittest import mock

from scripts.update_platform_status import (
    ROOT,
    _canonical_tracked_blob_oids,
    _is_generated_report,
    _serialize_json,
    _validate_provenance,
    build_report,
    render_readiness,
    render_status,
)


class PlatformStatusTests(unittest.TestCase):
    def test_report_derives_package_test_and_subsystem_state(self):
        report = build_report()
        self.assertEqual(report["package"]["version"], "0.8.0")
        self.assertGreaterEqual(report["tests"]["deterministic_cases_discovered"], 286)
        self.assertGreaterEqual(report["tests"]["server_files"], 4)
        self.assertGreaterEqual(report["tests"]["web_files"], 10)
        self.assertGreaterEqual(report["tests"]["migration_files"], 1)
        self.assertEqual(report["platform"]["ai_dependency"], "none_for_core_tests_or_runtime")
        self.assertNotIn("pull_requests", report["integration"])
        self.assertNotIn("branch", report["integration"])
        self.assertNotIn("branch_ancestry", report["integration"])
        self.assertEqual(
            len(report["generated"]["evaluated_source_tree_hash"]),
            64,
        )
        self.assertEqual(
            report["generated"]["current_runtime_git_sha"],
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
        )
        self.assertEqual(
            report["generated"]["current_merged_main_git_sha"],
            subprocess.check_output(
                ["git", "rev-parse", "origin/main"], cwd=ROOT, text=True
            ).strip(),
        )
        persisted = json.loads(_serialize_json(report))
        self.assertIsNone(persisted["generated"]["current_runtime_git_sha"])
        self.assertIsNone(
            persisted["generated"]["current_merged_main_git_sha"]
        )
        readiness = render_readiness(report)
        status = render_status(report)
        self.assertTrue(readiness.startswith("---\n"))
        self.assertIn('status: "generated"', readiness)
        self.assertNotIn("### Pull requests", status)
        self.assertNotIn("/pull/", status)
        self.assertNotIn("Current commit:", status)
        self.assertIn("Evaluated source tree:", status)

    def test_source_tree_fingerprint_excludes_generated_reports_only(self):
        self.assertTrue(
            _is_generated_report(
                "coverage/example.json", ROOT / "coverage" / "example.json"
            )
        )
        self.assertTrue(
            _is_generated_report(
                "docs/PLATFORM_IMPLEMENTATION_STATUS.md",
                ROOT / "docs" / "PLATFORM_IMPLEMENTATION_STATUS.md",
            )
        )
        self.assertFalse(
            _is_generated_report("README.md", ROOT / "README.md")
        )

    def test_source_tree_fingerprint_uses_git_clean_blobs(self):
        expected = subprocess.check_output(
            ["git", "rev-parse", "HEAD:.gitattributes"],
            cwd=ROOT,
            text=True,
        ).strip()
        self.assertEqual(
            _canonical_tracked_blob_oids([".gitattributes"]),
            [expected],
        )

    def test_provenance_rejects_old_or_duplicated_commit_coordinates(self):
        source = json.loads(
            (ROOT / "platform" / "readiness-source.json").read_text(
                encoding="utf-8"
            )
        )
        source["validation"]["baseline_commit"] = source["provenance"][
            "certified_head_sha"
        ]
        with self.assertRaisesRegex(ValueError, "baseline_commit"):
            _validate_provenance(source)

        source["validation"].pop("baseline_commit")
        source["integration"]["commit_reference"] = "duplicated current main"
        with self.assertRaisesRegex(ValueError, "commit_reference"):
            _validate_provenance(source)

    def test_provenance_rejects_pending_certification_language(self):
        source = json.loads(
            (ROOT / "platform" / "readiness-source.json").read_text(
                encoding="utf-8"
            )
        )
        source["integration"]["description"] = "certification pending"
        with self.assertRaisesRegex(ValueError, "certification pending"):
            _validate_provenance(source)

    def test_active_candidate_may_have_feature_head_milestone(self):
        source = json.loads(
            (ROOT / "platform" / "readiness-source.json").read_text(
                encoding="utf-8"
            )
        )
        source["integration"]["pull_requests"] = []
        source["milestones"][0]["status"] = "implemented_at_feature_head"
        with mock.patch(
            "scripts.update_platform_status._git_is_ancestor",
            side_effect=(False, True),
        ):
            _validate_provenance(source)

    def test_integrated_feature_cannot_retain_feature_head_milestone(self):
        source = json.loads(
            (ROOT / "platform" / "readiness-source.json").read_text(
                encoding="utf-8"
            )
        )
        source["integration"]["pull_requests"] = []
        source["provenance"]["feature_head_classification"] = (
            "historical_integrated"
        )
        source["milestones"][0]["status"] = "implemented_at_feature_head"
        with mock.patch(
            "scripts.update_platform_status._git_is_ancestor",
            side_effect=(True, True),
        ):
            with self.assertRaisesRegex(ValueError, "cannot remain at feature head"):
                _validate_provenance(source)

    def test_active_phase_rejects_a_feature_already_on_main(self):
        source = json.loads(
            (ROOT / "platform" / "readiness-source.json").read_text(
                encoding="utf-8"
            )
        )
        source["integration"]["active_phase"] = {
            "id": "stale_active_phase",
            "pull_request": 100,
            "head": "rules/generic-flash-cast-timing",
        }
        source["integration"]["pull_requests"] = []
        source["provenance"]["feature_head_classification"] = (
            "active_candidate"
        )
        with mock.patch(
            "scripts.update_platform_status._git_is_ancestor",
            return_value=True,
        ):
            with self.assertRaisesRegex(ValueError, "already reachable"):
                _validate_provenance(source)

    def test_active_phase_requires_a_matching_open_pull_request(self):
        source = json.loads(
            (ROOT / "platform" / "readiness-source.json").read_text(
                encoding="utf-8"
            )
        )
        source["integration"]["active_phase"] = {
            "id": "active_phase",
            "pull_request": 100,
            "head": "rules/generic-flash-cast-timing",
        }
        source["integration"]["pull_requests"] = []
        source["provenance"]["feature_head_classification"] = (
            "active_candidate"
        )
        with (
            mock.patch(
                "scripts.update_platform_status._git_is_ancestor",
                side_effect=(False, True),
            ),
            mock.patch(
                "scripts.update_platform_status._github_pull_request",
                return_value={
                    "state": "CLOSED",
                    "headRefName": "rules/generic-flash-cast-timing",
                    "headRefOid": source["provenance"]["feature_head_sha"],
                    "baseRefName": "main",
                },
            ),
        ):
            with self.assertRaisesRegex(ValueError, "no matching open"):
                _validate_provenance(source)

    def test_merged_pull_request_cannot_remain_pending(self):
        source = json.loads(
            (ROOT / "platform" / "readiness-source.json").read_text(
                encoding="utf-8"
            )
        )
        source["integration"]["pull_requests"] = [
            {
                "base": "main",
                "head": "feature/already-merged",
                "number": 999,
                "state": "open",
                "url": "https://example.invalid/pull/999",
            }
        ]
        with (
            mock.patch(
                "scripts.update_platform_status._github_pull_request",
                return_value={
                    "state": "MERGED",
                    "headRefName": "feature/already-merged",
                    "headRefOid": source["provenance"]["feature_head_sha"],
                    "baseRefName": "main",
                },
            ),
        ):
            with self.assertRaisesRegex(ValueError, "not the recorded open"):
                _validate_provenance(source)

    def test_open_pull_request_coordinates_must_match_github(self):
        source = json.loads(
            (ROOT / "platform" / "readiness-source.json").read_text(
                encoding="utf-8"
            )
        )
        source["integration"]["pull_requests"] = [
            {
                "base": "main",
                "head": "feature/recorded",
                "number": 999,
                "state": "open",
                "url": "https://example.invalid/pull/999",
            }
        ]
        with mock.patch(
            "scripts.update_platform_status._github_pull_request",
            return_value={
                "state": "OPEN",
                "headRefName": "feature/different",
                "headRefOid": source["provenance"]["feature_head_sha"],
                "baseRefName": "main",
            },
        ):
            with self.assertRaisesRegex(ValueError, "not the recorded open"):
                _validate_provenance(source)

    def test_stale_heads_require_explicit_historical_classification(self):
        source = json.loads(
            (ROOT / "platform" / "readiness-source.json").read_text(
                encoding="utf-8"
            )
        )
        source["integration"]["pull_requests"] = []
        source["provenance"]["certified_head_sha"] = subprocess.check_output(
            ["git", "rev-parse", "origin/main^"],
            cwd=ROOT,
            text=True,
        ).strip()
        source["provenance"]["certified_head_classification"] = (
            "current_main"
        )
        with self.assertRaisesRegex(ValueError, "trails current main"):
            _validate_provenance(source)

    def test_current_card_baseline_is_derived_not_hand_copied(self):
        source = json.loads(
            (ROOT / "platform" / "readiness-source.json").read_text(
                encoding="utf-8"
            )
        )
        source["integration"]["pull_requests"] = []
        source["validation"]["card_program_census"] = "stale hand copy"
        with self.assertRaisesRegex(ValueError, "must be derived"):
            _validate_provenance(source)

    def test_generated_platform_status_is_current(self):
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "update_platform_status.py"),
                "--check",
            ],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
