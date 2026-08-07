from __future__ import annotations

from types import SimpleNamespace
import unittest

from quorune.abilities import ActivatedAbility
from quorune.characteristic_evaluation import type_parts
from quorune.rules.activation import activation_condition_status


class _Host:
    def __init__(self, type_lines: dict[str, object]) -> None:
        cards = {
            object_id: SimpleNamespace(
                object_id=object_id,
                controller="A",
                phased_out=False,
            )
            for object_id in type_lines
        }
        self._type_lines = type_lines
        self.state = SimpleNamespace(
            active_player="A",
            turn_sequence=1,
            cards=cards,
            players={
                "A": SimpleNamespace(
                    zones={
                        "battlefield": list(cards),
                        "graveyard": [],
                    },
                    stats={},
                )
            },
        )

    def _effective_card_data(self, card):
        object_id = card if isinstance(card, str) else card.object_id
        return {"type_line": self._type_lines[object_id]}

    @staticmethod
    def _type_parts(type_line: str):
        return type_parts(type_line)


def _ability(kind: str) -> ActivatedAbility:
    line = f"Activate only if you control two or more {kind}s."
    return ActivatedAbility(
        ability_id="ab1",
        line_index=0,
        oracle_line=f"{{T}}: Add {{C}}. {line}",
        cost_text="{T}",
        effect_text=f"Add {{C}}. {line}",
        zones=("battlefield",),
        mana={},
    )


class ActivationConditionTypeCountTests(unittest.TestCase):
    def test_count_uses_exact_parsed_card_types_not_subtype_substrings(self):
        artifact_host = _Host(
            {
                "real": "Artifact Creature — Construct",
                "false-subtype": "Creature — Artifact",
            }
        )
        self.assertEqual(
            ("unavailable", "requires_2_artifacts"),
            activation_condition_status(
                artifact_host,
                "A",
                _ability("artifact"),
            ),
        )
        artifact_host._type_lines["second-real"] = "Artifact"
        artifact_host.state.cards["second-real"] = SimpleNamespace(
            object_id="second-real",
            controller="A",
            phased_out=False,
        )
        artifact_host.state.players["A"].zones["battlefield"].append(
            "second-real"
        )
        self.assertEqual(
            ("payable", None),
            activation_condition_status(
                artifact_host,
                "A",
                _ability("artifact"),
            ),
        )

        land_host = _Host(
            {"false-subtype": "Creature — Island", "real": "Land"}
        )
        self.assertEqual(
            ("unavailable", "requires_2_lands"),
            activation_condition_status(land_host, "A", _ability("land")),
        )

    def test_malformed_effective_type_line_fails_closed(self):
        host = _Host({"malformed": ["Artifact"], "real": "Artifact"})

        self.assertEqual(
            ("unresolved", "malformed_effective_type_line"),
            activation_condition_status(host, "A", _ability("artifact")),
        )


if __name__ == "__main__":
    unittest.main()
