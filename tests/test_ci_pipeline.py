from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tests.common import ROOT
from scripts.ci_metrics import build_metrics, markdown
from scripts.ci_plan import browser_matrix
from scripts.test_shards import load_manifest, primary_matrix, suite_modules
from scripts.verify_ci_needs import failed_dependencies
from scripts.verify_windows_ci import (
    WindowsCertificationError,
    expected_suites,
    validate_dependencies,
    validate_results,
)


class CiPipelineTests(unittest.TestCase):
    @staticmethod
    def _windows_result(suite: str, *, tests_run: int = 3) -> dict:
        modules = suite_modules(load_manifest(), suite)
        return {
            "schema_version": 1,
            "type": "unittest-shard-result",
            "suite": suite,
            "modules": list(modules),
            "configured_test_count": tests_run,
            "tests_run": tests_run,
            "duration_seconds": 25.0,
            "successful": True,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
            "expected_failures": 0,
            "unexpected_successes": 0,
        }

    def test_browser_matrix_uses_one_smoke_or_three_isolated_measured_groups(self):
        smoke = browser_matrix(False)["include"]
        full = browser_matrix(True)["include"]
        self.assertEqual(1, len(smoke))
        self.assertEqual("smoke", smoke[0]["group"])
        self.assertEqual(3, len(full))
        self.assertEqual(
            {"lifecycle", "rules", "soak"},
            {row["group"] for row in full},
        )
        self.assertEqual(3, len({row["server_port"] for row in full}))
        self.assertEqual(3, len({row["web_port"] for row in full}))
        self.assertEqual(3, len({row["grep"] for row in full}))

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

    def test_windows_certification_requires_exact_mode_dependencies(self):
        validate_dependencies(
            {
                "plan": {"result": "success"},
                "windows_compatibility": {"result": "skipped"},
                "windows_full": {"result": "success"},
                "windows_package": {"result": "success"},
            },
            full=True,
        )
        with self.assertRaises(WindowsCertificationError):
            validate_dependencies(
                {
                    "plan": {"result": "success"},
                    "windows_compatibility": {"result": "skipped"},
                    "windows_full": {"result": "skipped"},
                    "windows_package": {"result": "success"},
                },
                full=True,
            )

    def test_windows_full_results_cover_every_primary_shard_and_are_nonempty(self):
        self.assertEqual(
            tuple(load_manifest()["primary_shards"]),
            expected_suites(full=True),
        )
        with TemporaryDirectory() as raw:
            root = Path(raw)
            for suite in expected_suites(full=True):
                path = root / suite / "result.json"
                path.parent.mkdir(parents=True)
                path.write_text(
                    json.dumps(self._windows_result(suite)), encoding="utf-8"
                )
            summary = validate_results(root, full=True)
            self.assertEqual(len(primary_matrix(load_manifest())["include"]), summary["suites"])
            self.assertGreater(summary["tests_run"], 0)

    def test_windows_results_fail_closed_for_missing_or_zero_test_shard(self):
        with TemporaryDirectory() as raw:
            root = Path(raw)
            result = self._windows_result("windows-compat", tests_run=0)
            (root / "result.json").write_text(json.dumps(result), encoding="utf-8")
            with self.assertRaisesRegex(WindowsCertificationError, "zero tests"):
                validate_results(root, full=False)
        with TemporaryDirectory() as raw:
            with self.assertRaisesRegex(WindowsCertificationError, "missing_results"):
                validate_results(Path(raw), full=False)

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
                        "steps": [
                            {
                                "name": "Run shard",
                                "conclusion": "success",
                                "started_at": "2026-08-03T12:00:20Z",
                                "completed_at": "2026-08-03T12:02:00Z",
                            }
                        ],
                    },
                    {
                        "name": "PR / Windows / core-domain",
                        "conclusion": "success",
                        "started_at": "2026-08-03T12:00:10Z",
                        "completed_at": "2026-08-03T12:01:10Z",
                        "steps": [
                            {
                                "name": "Install package and test dependencies",
                                "conclusion": "success",
                                "started_at": "2026-08-03T12:00:10Z",
                                "completed_at": "2026-08-03T12:00:20Z",
                            },
                            {
                                "name": "Run full Windows shard",
                                "conclusion": "success",
                                "started_at": "2026-08-03T12:00:20Z",
                                "completed_at": "2026-08-03T12:01:00Z",
                            },
                        ],
                    },
                    {
                        "name": "PR / Windows / package",
                        "conclusion": "success",
                        "started_at": "2026-08-03T12:00:08Z",
                        "completed_at": "2026-08-03T12:00:48Z",
                        "steps": [
                            {
                                "name": "Build and verify Windows wheel",
                                "conclusion": "success",
                                "started_at": "2026-08-03T12:00:20Z",
                                "completed_at": "2026-08-03T12:00:45Z",
                            }
                        ],
                    },
                    {
                        "name": "PR / Windows / casting-costs-mana",
                        "conclusion": "success",
                        # GitHub may mark a matrix job started while it is still
                        # waiting for the strategy's runner slot.
                        "started_at": "2026-08-03T12:00:11Z",
                        "completed_at": "2026-08-03T12:02:00Z",
                        "steps": [
                            {
                                "name": "Install package and test dependencies",
                                "conclusion": "success",
                                "started_at": "2026-08-03T12:01:00Z",
                                "completed_at": "2026-08-03T12:01:10Z",
                            },
                            {
                                "name": "Run full Windows shard",
                                "conclusion": "success",
                                "started_at": "2026-08-03T12:01:10Z",
                                "completed_at": "2026-08-03T12:01:40Z",
                            },
                        ],
                    },
                ]
            },
            [
                (
                    "rules",
                    {
                        "suites": [
                            {
                                "title": "four-player.spec.ts",
                                "specs": [
                                    {
                                        "title": "rules journey",
                                        "file": "four-player.spec.ts",
                                        "tests": [
                                            {
                                                "annotations": [
                                                    {
                                                        "type": "commander-journey-metrics",
                                                        "description": json.dumps(
                                                            {
                                                                "browser_contexts": 2,
                                                                "accepted_commands": 12,
                                                                "authoritative_revisions": 18,
                                                                "derived_review_seconds": 0.0,
                                                            }
                                                        ),
                                                    }
                                                ],
                                                "results": [
                                                    {
                                                        "status": "failed",
                                                        "duration": 1500,
                                                        "errors": [
                                                            {
                                                                "message": "expect timeout"
                                                            }
                                                        ],
                                                    },
                                                    {
                                                        "status": "passed",
                                                        "duration": 1250,
                                                        "errors": [],
                                                    },
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    },
                )
            ],
            [
                self._windows_result("core-domain"),
                self._windows_result("casting-costs-mana"),
            ],
        )
        self.assertEqual(5.0, metrics["queue_seconds"])
        self.assertEqual(125.0, metrics["critical_path_seconds_observed"])
        self.assertIsNone(metrics["cache_hit_rate"])
        self.assertEqual(100.0, metrics["jobs"][0]["steps"][0]["duration_seconds"])
        journey = metrics["browser_journeys"][0]
        self.assertEqual("rules", journey["group"])
        self.assertEqual(1, journey["retry_count"])
        self.assertEqual("none", journey["failure_classification"])
        self.assertEqual(12, journey["game_metrics"]["accepted_commands"])
        windows = metrics["windows"]
        self.assertEqual(100.0, windows["critical_path_seconds_observed"])
        self.assertEqual(1, windows["max_runner_concurrency_observed"])
        self.assertEqual(25.0, windows["package_duration_seconds"])
        self.assertEqual(3, windows["shards"][0]["test_count"])
        self.assertEqual(10.0, windows["shards"][0]["setup_duration_seconds"])
        self.assertIn("unavailable", markdown(metrics))
        self.assertIn("rules journey", markdown(metrics))
        self.assertIn("core-domain", markdown(metrics))

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
        self.assertIn("fromJSON(needs.plan.outputs.browser_matrix)", pr)
        self.assertIn("fromJSON(needs.plan.outputs.windows_matrix)", pr)
        self.assertIn("needs.plan.outputs.browser_focus_grep", pr)
        self.assertIn("Run focused browser journeys for affected rules", pr)
        self.assertIn('npx playwright test --grep "$MTG_BROWSER_GROUP_GREP"', pr)
        self.assertNotIn("--shard=", pr)
        self.assertIn("actions/download-artifact@v4", pr)
        self.assertIn("--browser-report-dir local/browser-results", pr)
        self.assertIn("--windows-report-dir local/windows-results", pr)
        self.assertIn("scripts/test_shards.py run", pr)
        generated = pr.split("\n  generated:", 1)[1].split("\n  package:", 1)[0]
        package = pr.split("\n  package:", 1)[1].split("\n  windows_compatibility:", 1)[0]
        windows_full = pr.split("\n  windows_full:", 1)[1].split("\n  windows_package:", 1)[0]
        self.assertIn("MTG_CARD_DB: data/test-ci.sqlite3", generated)
        self.assertIn("scripts/build_test_database.py build", generated)
        self.assertIn("python -m pip install -e .", package)
        self.assertIn("max-parallel: 5", windows_full)
        self.assertIn('python scripts/test_shards.py run "${{ matrix.shard }}"', windows_full)
        self.assertNotIn("unittest discover", windows_full)
        self.assertIn("PR / Windows Certification", pr)
        self.assertIn("windows_certification", pr)
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
