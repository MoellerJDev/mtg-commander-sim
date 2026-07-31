from __future__ import annotations

import json
import unittest
from pathlib import Path


class SpellsAbilitiesEffectsGeneralRuleTests(unittest.TestCase):
    def test_contract_traces_the_only_cr_600_record(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "spells-abilities-effects-general.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(["600"], contract["rule_references"])
        self.assertEqual("cr-600-general", contract["mechanic_id"])


if __name__ == "__main__":
    unittest.main()
