from __future__ import annotations

import json
import subprocess
import sys
import unittest

from scripts.certification_receipt import RECEIPT_SCHEMA_VERSION
from scripts.source_tree_fingerprint import SOURCE_TREE_FINGERPRINT_ALGORITHM
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
    def source(self) -> dict:
        return json.loads(
            (ROOT / "platform" / "readiness-source.json").read_text(
                encoding="utf-8"
            )
        )

    def test_report_derives_durable_package_test_and_subsystem_state(self):
        report = build_report()
        self.assertEqual("0.8.0", report["package"]["version"])
        self.assertGreaterEqual(report["tests"]["deterministic_cases_discovered"], 286)
        self.assertGreaterEqual(report["tests"]["server_files"], 4)
        self.assertGreaterEqual(report["tests"]["web_files"], 10)
        self.assertGreaterEqual(report["tests"]["migration_files"], 1)
        self.assertEqual("none_for_core_tests_or_runtime", report["platform"]["ai_dependency"])
        self.assertNotIn("integration", report)
        self.assertNotIn("next_task", report)
        self.assertEqual(
            SOURCE_TREE_FINGERPRINT_ALGORITHM,
            report["generated"]["source_tree_fingerprint_algorithm"],
        )
        self.assertEqual(64, len(report["generated"]["evaluated_source_tree_hash"]))
        self.assertNotIn("current_runtime_git_sha", report["generated"])
        self.assertNotIn("current_merged_main_git_sha", report["generated"])
        persisted = json.loads(_serialize_json(report))
        self.assertEqual(report["generated"], persisted["generated"])

        readiness = render_readiness(report)
        status = render_status(report)
        self.assertTrue(readiness.startswith("---\n"))
        self.assertIn('status: "generated"', readiness)
        self.assertNotIn("### Pull requests", status)
        self.assertNotIn("/pull/", status)
        self.assertNotIn("Current commit:", status)
        self.assertIn("Source fingerprint:", status)
        self.assertIn("## Current top-level state", status)
        self.assertIn("## Top blockers", status)
        self.assertIn("coverage/platform-readiness.json", status)
        self.assertIn("scripts\\update_platform_status.py --write", status)

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
        self.assertFalse(_is_generated_report("README.md", ROOT / "README.md"))

    def test_source_tree_fingerprint_uses_git_clean_blobs(self):
        expected = subprocess.check_output(
            ["git", "rev-parse", "HEAD:.gitattributes"],
            cwd=ROOT,
            text=True,
        ).strip()
        self.assertEqual(
            [expected],
            _canonical_tracked_blob_oids([".gitattributes"]),
        )

    def test_durable_provenance_has_no_execution_coordinates(self):
        source = self.source()
        _validate_provenance(source)
        self.assertEqual(3, source["schema_version"])
        self.assertEqual(
            RECEIPT_SCHEMA_VERSION,
            source["provenance"]["certification_receipt_schema_version"],
        )
        serialized = json.dumps(source, sort_keys=True).lower()
        for value in (
            "active_phase",
            "feature_head_sha",
            "certified_head_sha",
            "generation_timestamp",
            "pull_requests",
            "run_id",
            "runtime_branch",
        ):
            self.assertNotIn(value, serialized)

    def test_durable_provenance_rejects_transient_integration_state(self):
        source = self.source()
        source["integration"] = {"branch": "feature/transient"}
        with self.assertRaisesRegex(ValueError, "transient integration"):
            _validate_provenance(source)

        source = self.source()
        source["next_task"] = "transient scheduler duplicate"
        with self.assertRaisesRegex(ValueError, "rules scheduler"):
            _validate_provenance(source)

    def test_durable_provenance_rejects_unknown_policy_or_execution_receipt(self):
        source = self.source()
        source["provenance"]["source_tree_fingerprint_algorithm"] = "stale-v1"
        with self.assertRaisesRegex(ValueError, "algorithm"):
            _validate_provenance(source)

        source = self.source()
        source["validation"]["ci"]["run_id"] = 123
        with self.assertRaisesRegex(ValueError, "durable CI"):
            _validate_provenance(source)

    def test_card_census_remains_derived(self):
        source = self.source()
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
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
