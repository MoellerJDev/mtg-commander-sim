from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from property_budget import (
    DEFAULT_PROPERTY_TRANSITIONS,
    property_transitions,
)


class PropertyBudgetTests(unittest.TestCase):
    def test_default_budget_remains_fast_for_prs(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(DEFAULT_PROPERTY_TRANSITIONS, property_transitions())

    def test_nightly_budget_is_explicitly_configurable(self):
        with patch.dict(
            os.environ, {"MTG_PROPERTY_TRANSITIONS": "100000"}, clear=True
        ):
            self.assertEqual(100_000, property_transitions())

    def test_invalid_budget_fails_closed(self):
        for raw in ("zero", "0", "1000001"):
            with self.subTest(raw=raw), patch.dict(
                os.environ, {"MTG_PROPERTY_TRANSITIONS": raw}, clear=True
            ):
                with self.assertRaisesRegex(ValueError, "MTG_PROPERTY_TRANSITIONS"):
                    property_transitions()


if __name__ == "__main__":
    unittest.main()
