from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_documentation", ROOT / "scripts" / "validate_documentation.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DocumentationPolicyTests(unittest.TestCase):
    def test_repository_documentation_passes(self) -> None:
        failures = MODULE.validate(ROOT)
        self.assertEqual([], failures, "\n".join(failures))

    def test_missing_metadata_is_rejected(self) -> None:
        policy = MODULE.load_policy()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "README.md"
            path.write_text("# No metadata\n", encoding="utf-8")
            failures = MODULE.metadata_failures(root, [path], policy)
        self.assertTrue(any("missing metadata" in item for item in failures))

    def test_broken_relative_link_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "README.md"
            path.write_text("[missing](docs/nope.md)\n", encoding="utf-8")
            failures = MODULE.link_failures(root, [path])
        self.assertTrue(any("broken link" in item for item in failures))

    def test_current_numeric_status_claim_is_rejected(self) -> None:
        policy = MODULE.load_policy()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "README.md"
            path.write_text(
                "---\nstatus: current\n---\n\n"
                "4,200 tests passed. Packet uses 1,549 tokens.\n",
                encoding="utf-8",
            )
            failures = MODULE.stale_claim_failures(root, [path], policy)
        self.assertTrue(any("test or case count" in item for item in failures))
        self.assertTrue(any("grouped numerical metric" in item for item in failures))

    def test_generated_numeric_status_is_allowed(self) -> None:
        policy = MODULE.load_policy()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "status.md"
            path.write_text(
                "---\nstatus: generated\n---\n\n4,200 tests passed.\n",
                encoding="utf-8",
            )
            self.assertEqual(
                [], MODULE.stale_claim_failures(root, [path], policy)
            )

    def test_source_tree_fingerprint_is_valid_verification_provenance(self) -> None:
        metadata = {"verified": "a" * 64}
        self.assertTrue(MODULE._verified_value_valid(metadata))
        self.assertFalse(MODULE._verified_value_valid({"verified": "a" * 63}))

    def test_current_pull_request_history_is_rejected(self) -> None:
        policy = MODULE.load_policy()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "README.md"
            path.write_text(
                "---\nstatus: current\n---\n\n"
                "PR #41 introduced this.\n",
                encoding="utf-8",
            )
            failures = MODULE.stale_claim_failures(root, [path], policy)
        self.assertTrue(any("pull-request history" in item for item in failures))

    def test_current_workflow_run_and_transient_branch_are_rejected(self) -> None:
        policy = MODULE.load_policy()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "README.md"
            path.write_text(
                "---\nstatus: current\n---\n\n"
                "Workflow run 123456789 passed on branch fix/example.\n",
                encoding="utf-8",
            )
            failures = MODULE.stale_claim_failures(root, [path], policy)
        self.assertTrue(any("workflow run ID" in item for item in failures))
        self.assertTrue(any("transient branch" in item for item in failures))

    def test_root_document_allowlist_is_enforced(self) -> None:
        policy = MODULE.load_policy()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            allowed = root / "README.md"
            extra = root / ".." / root.name / "STATUS.md"
            allowed.write_text("# Readme\n", encoding="utf-8")
            extra.write_text("# Status\n", encoding="utf-8")
            failures = MODULE.root_document_failures(root, [allowed, extra], policy)
        self.assertTrue(any("STATUS.md" in item for item in failures))

    def test_historical_document_outside_allowed_location_is_rejected(self) -> None:
        policy = MODULE.load_policy()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "docs" / "old-status.md"
            path.parent.mkdir()
            path.write_text(
                "---\nstatus: historical\nmaintenance: hand-maintained\n---\n",
                encoding="utf-8",
            )
            failures = MODULE.historical_placement_failures(root, [path], policy)
        self.assertTrue(any("outside an allowed location" in item for item in failures))

    def test_generated_dashboard_fingerprint_must_match_source(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "coverage").mkdir()
            source = root / "coverage" / "status.json"
            source.write_text("{}\n", encoding="utf-8", newline="\n")
            dashboard = root / "coverage" / "status.md"
            command = "python scripts/update.py --write"
            dashboard.write_text(
                "---\nstatus: generated\nmaintenance: generated\n"
                "generated_source: coverage/status.json\n"
                f"generation_command: {command}\nverified: {'0' * 64}\n---\n\n"
                f"{command}\n",
                encoding="utf-8",
            )
            policy = {
                "generated_dashboards": {
                    "coverage/status.md": {
                        "source": "coverage/status.json",
                        "command": command,
                    }
                }
            }
            failures = MODULE.generated_source_failures(root, policy)
        self.assertTrue(any("is stale" in item for item in failures))

    def test_adr_requires_alternatives(self) -> None:
        policy = MODULE.load_policy()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            directory = root / "docs" / "adr"
            directory.mkdir(parents=True)
            decision = directory / "0001-example.md"
            decision.write_text(
                "---\n"
                "status: ADR\n"
                "adr_id: \"0001\"\n"
                "decision_status: accepted\n"
                "date: \"2026-08-01\"\n"
                "---\n\n"
                "# Example\n\n## Context\n\n## Decision\n\n## Consequences\n",
                encoding="utf-8",
            )
            (directory / "index.md").write_text(
                "[Example](0001-example.md)\n", encoding="utf-8"
            )
            failures = MODULE.adr_failures(root, policy)
        self.assertTrue(any("alternatives" in item for item in failures))


if __name__ == "__main__":
    unittest.main()
