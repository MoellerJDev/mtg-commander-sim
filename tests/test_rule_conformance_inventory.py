from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any, Mapping

from quorune.rule_conformance import (
    case_by_rule_id,
    inventory_case_errors,
)


ROOT = Path(__file__).resolve().parents[1]
RULE_INDEX = json.loads(
    (ROOT / "rules" / "rule-index.json").read_text(encoding="utf-8")
)
CONFORMANCE = json.loads(
    (ROOT / "rules" / "conformance-cases.json").read_text(
        encoding="utf-8"
    )
)
CASES_BY_RULE = case_by_rule_id(CONFORMANCE)


class GeneratedRuleConformanceInventoryTests(unittest.TestCase):
    """One source-linkage test per pinned CR rule; not semantic evidence."""


def _inventory_test(
    rule: Mapping[str, Any],
):
    def test(self: GeneratedRuleConformanceInventoryTests) -> None:
        rule_id = str(rule["rule_id"])
        self.assertIn(rule_id, CASES_BY_RULE)
        self.assertEqual(
            [],
            list(
                inventory_case_errors(
                    CASES_BY_RULE[rule_id],
                    rule,
                    effective_date=str(RULE_INDEX["effective_date"]),
                    source_sha256=str(RULE_INDEX["source_sha256"]),
                )
            ),
        )

    return test


for _rule in RULE_INDEX["rules"]:
    _rule_id = str(_rule["rule_id"])
    _method_name = "test_inventory_" + re.sub(
        r"[^a-zA-Z0-9]+",
        "_",
        f"cr_{_rule_id}",
    )
    _method = _inventory_test(_rule)
    _method.__name__ = _method_name
    _method.__doc__ = (
        f"Inventory/source-linkage assertion for CR {_rule_id}; "
        "not a semantic implementation pass."
    )
    setattr(
        GeneratedRuleConformanceInventoryTests,
        _method_name,
        _method,
    )


del _method
del _method_name
del _rule
del _rule_id
