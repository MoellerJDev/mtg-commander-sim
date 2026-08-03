from __future__ import annotations

import json
import unittest

from tests.common import ROOT
from scripts.ci_metrics import build_metrics, markdown
from scripts.verify_ci_needs import failed_dependencies


class CiPipelineTests(unittest.TestCase):
    def test_certification_fails_for_any_non_success_dependency(self):
        self.assertEqual(
            ("browser", "windows"),
            failed_dependencies(
                {
                    "python": {"result": "success"},
                    "browser": {"result": "failure"},
                    "windows": {"result": "cancelled"},
                }
            ),
        )
        self.assertEqual((), failed_dependencies({"python": {"result": "success"}}))

    def test_metrics_report_observed_values_without_estimates(self):
        metrics = build_metrics(
            {
                "id": 42,
                "head_sha": "abc",
                "status": "completed",
                "conclusion": "success",
                "created_at": "2026-08-03T12:00:00Z",
            },
            {
                "jobs": [
                    {
                        "name": "PR / Python / core-domain",
                        "conclusion": "success",
                        "started_at": "2026-08-03T12:00:05Z",
                        "completed_at": "2026-08-03T12:02:05Z",
                    }
                ]
            },
        )
        self.assertEqual(5.0, metrics["queue_seconds"])
        self.assertEqual(125.0, metrics["critical_path_seconds_observed"])
        self.assertIsNone(metrics["cache_hit_rate"])
        self.assertIn("unavailable", markdown(metrics))

    def test_workflows_separate_pr_main_and_nightly_responsibilities(self):
        pr = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        main = (ROOT / ".github/workflows/main-smoke.yml").read_text(
            encoding="utf-8"
        )
        nightly = (ROOT / ".github/workflows/nightly.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("cancel-in-progress: true", pr)
        self.assertIn("PR / Certification", pr)
        self.assertIn("scripts/test_shards.py run", pr)
        generated = pr.split("\n  generated:", 1)[1].split("\n  package:", 1)[0]
        package = pr.split("\n  package:", 1)[1].split("\n  windows:", 1)[0]
        self.assertIn("MTG_CARD_DB: data/test-ci.sqlite3", generated)
        self.assertIn("scripts/build_test_database.py build", generated)
        self.assertIn("python -m pip install -e .", package)
        self.assertIn("branches: [\"main\"]", main)
        self.assertNotIn("test_*.py", main)
        self.assertIn("schedule:", nightly)
        self.assertIn("MTG_PROPERTY_TRANSITIONS: \"33334\"", nightly)
        self.assertIn("test_*.py", nightly)

    def test_browser_smoke_is_headless_and_never_opens_report(self):
        package = json.loads((ROOT / "web/package.json").read_text(encoding="utf-8"))
        self.assertIn("--grep @smoke", package["scripts"]["e2e:smoke"])
        config = (ROOT / "web/playwright.config.ts").read_text(encoding="utf-8")
        self.assertIn("headless: true", config)
        self.assertIn('open: "never"', config)


if __name__ == "__main__":
    unittest.main()
