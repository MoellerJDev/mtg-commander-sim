from __future__ import annotations

import gzip
import json
from pathlib import Path
import tempfile
import unittest

from common import ROOT, load_assets
from mtg_commander_sim import CommanderSession, GameConfig
from mtg_commander_sim.record import replay_record


class PublicFixturePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_sanitized_recipe_generates_exact_private_replay_only_in_temp(self):
        fixture = json.loads(
            (
                ROOT / "tests" / "fixtures" / "sanitized-replay-smoke.json"
            ).read_text(encoding="utf-8")
        )
        deck_by_name = {"mishra": self.mishra, "zimone": self.zimone}
        session = CommanderSession.create(
            self.db,
            {
                seat: deck_by_name[name]
                for seat, name in fixture["decks"].items()
            },
            first_player="A",
            seed=fixture["seed"],
            config=GameConfig(
                seed=fixture["seed"],
                profile=fixture["profile"],
            ),
        )
        raw_capabilities = []
        for command in fixture["actions"]:
            principal = command["principal"]
            raw_capabilities.append(
                session.packet(principal, full=True)["decision"]["cap"]
            )
            result = session.act(
                principal,
                {
                    "action_id": command["action_id"],
                    "reason": "Sanitized deterministic replay fixture.",
                    "plan": "MULLIGAN",
                },
            )
            self.assertTrue(result.ok, result.summary)

        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "record"
            session.save(record)
            replay = replay_record(record, self.db, verify=True)
            self.assertTrue(replay["ok"])
            for path in record.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix == ".gz":
                    with gzip.open(path, "rt", encoding="utf-8") as handle:
                        text = handle.read()
                else:
                    text = path.read_text(encoding="utf-8")
                for capability in raw_capabilities:
                    self.assertNotIn(capability, text)


if __name__ == "__main__":
    unittest.main()
