from __future__ import annotations

import unittest

from quorune import apply_json_patch, json_patch, view_hash
from common import load_assets, make_session


class ProtocolPatchTests(unittest.TestCase):
    def test_patch_round_trip_handles_lists_and_escaped_keys(self):
        old = {
            "players": {
                "A": {
                    "bf": [{"id": "A1"}, {"id": "A2"}],
                    "path/with~chars": 1,
                }
            }
        }
        new = {
            "players": {
                "A": {
                    "bf": [{"id": "A2"}, {"id": "A3"}],
                    "path/with~chars": 2,
                    "life": 37,
                }
            }
        }
        operations = json_patch(old, new)
        self.assertEqual(new, apply_json_patch(old, operations))
        self.assertTrue(any("~1" in op["path"] and "~0" in op["path"] for op in operations))

    def test_view_hash_is_canonical_across_key_order(self):
        self.assertEqual(view_hash({"b": 2, "a": 1}), view_hash({"a": 1, "b": 2}))


class PilotRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_runner_retries_rejected_action_on_same_capability(self):
        from quorune import SequentialPilotRunner

        session = make_session(self.db, self.mishra, self.zimone, seed=700)
        calls = []

        def pilot(principal, packet):
            calls.append((principal, packet))
            if len(calls) == 1:
                return {"a": "cast", "card": "not-a-card"}
            self.assertIn("retry", packet)
            self.assertIn("outside capability scope", packet["retry"]["error"])
            return {"a": "keep"}

        runner = SequentialPilotRunner(session, pilot, max_retries_per_decision=1)
        self.assertTrue(runner.step())
        self.assertEqual(1, runner.metrics.accepted_decisions)
        self.assertEqual(2, runner.metrics.action_attempts)
        self.assertEqual(1, runner.metrics.failed_actions)
        self.assertEqual(1, runner.metrics.retries)
        self.assertEqual(["pilot:B"], session.pending_principals())


if __name__ == "__main__":
    unittest.main()
