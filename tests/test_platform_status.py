from __future__ import annotations

import subprocess
import sys
import unittest

from scripts.update_platform_status import (
    ROOT,
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
        readiness = render_readiness(report)
        status = render_status(report)
        self.assertTrue(readiness.startswith("---\n"))
        self.assertIn('status: "generated"', readiness)
        self.assertNotIn("### Pull requests", status)
        self.assertNotIn("/pull/", status)

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
