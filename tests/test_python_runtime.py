from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
import unittest

from mtg_commander_sim.python_runtime import (
    UnsupportedPythonRuntime,
    require_supported_python,
    require_supported_runtime,
)
from scripts.validate_python_runtime import (
    project_policy_failures,
    validate,
    workflow_policy_failures,
)
from scripts.verify_wheel import _requires_python_matches


@dataclass(frozen=True)
class FakeVersion:
    major: int
    minor: int


class PythonRuntimeTests(unittest.TestCase):
    def test_current_runtime_and_repository_policy_pass(self):
        result = validate()
        self.assertTrue(result["ok"])
        self.assertEqual("3.12", result["required_minor"])

    def test_older_and_newer_minor_versions_fail_closed(self):
        for version in (FakeVersion(3, 11), FakeVersion(3, 13), FakeVersion(4, 0)):
            with self.subTest(version=version):
                with self.assertRaises(UnsupportedPythonRuntime):
                    require_supported_python(version)

    def test_exact_supported_minor_is_accepted(self):
        require_supported_python(FakeVersion(3, 12))

    def test_non_cpython_and_32_bit_runtimes_fail_closed(self):
        with self.assertRaises(UnsupportedPythonRuntime):
            require_supported_runtime(FakeVersion(3, 12), implementation="PyPy")
        with self.assertRaises(UnsupportedPythonRuntime):
            require_supported_runtime(FakeVersion(3, 12), maxsize=2**31 - 1)

    def test_project_policy_reports_every_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".python-version").write_text("3.11\n", encoding="utf-8")
            (root / "pyproject.toml").write_text(
                "[project]\nname = 'fixture'\nversion = '1.0'\n"
                "requires-python = '>=3.11'\nclassifiers = []\n",
                encoding="utf-8",
            )
            failures = project_policy_failures(root)

        self.assertEqual(5, len(failures))
        self.assertTrue(any(".python-version" in item for item in failures))
        self.assertTrue(any("requires-python" in item for item in failures))
        self.assertEqual(
            3,
            sum("classifier is missing" in item for item in failures),
        )

    def test_current_workflows_pin_two_os_jobs_and_browser_to_x64_312(self):
        self.assertEqual([], workflow_policy_failures())

    def test_wheel_requirement_accepts_canonicalized_order_only(self):
        self.assertTrue(_requires_python_matches("<3.13,>=3.12"))
        self.assertFalse(_requires_python_matches(">=3.11"))
        self.assertFalse(_requires_python_matches(None))


if __name__ == "__main__":
    unittest.main()
