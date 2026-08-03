from __future__ import annotations

from copy import deepcopy
import unittest

from scripts.test_shards import (
    discovered_modules,
    load_manifest,
    suite_modules,
    TestShardError,
    validate_partition,
)


class TestShardManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = load_manifest()

    def test_every_test_module_has_one_primary_shard(self):
        summary = validate_partition(self.manifest)
        self.assertEqual(len(discovered_modules()), summary["test_modules"])

    def test_duplicate_primary_assignment_fails_closed(self):
        mutated = deepcopy(self.manifest)
        module = mutated["primary_shards"]["core-domain"][0]
        mutated["primary_shards"]["compiler-cardprogram"].append(module)
        with self.assertRaisesRegex(TestShardError, "duplicates"):
            validate_partition(mutated)

    def test_missing_primary_assignment_fails_closed(self):
        mutated = deepcopy(self.manifest)
        mutated["primary_shards"]["core-domain"].pop()
        with self.assertRaisesRegex(TestShardError, "missing"):
            validate_partition(mutated)

    def test_overlay_suites_are_explicit_and_known(self):
        windows = suite_modules(self.manifest, "windows-compat")
        self.assertIn("test_server_app", windows)
        self.assertIn("test_game_record_v3", windows)

    def test_unknown_suite_fails_closed(self):
        with self.assertRaisesRegex(TestShardError, "Unknown test suite"):
            suite_modules(self.manifest, "not-a-suite")


if __name__ == "__main__":
    unittest.main()
