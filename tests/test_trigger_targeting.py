from __future__ import annotations

from types import SimpleNamespace
import unittest

from mtg_commander_sim.trigger_targeting import (
    begin_pending_trigger_target_selection,
)


class _Semantics:
    @staticmethod
    def get(_key):
        return None


class _Permissions:
    def __init__(self):
        self.issued = []

    def issue(self, **kwargs):
        self.issued.append(kwargs)


class _Host:
    def __init__(self, items, schemas):
        self.state = SimpleNamespace(stack=list(items))
        self.semantics = _Semantics()
        self.permissions = _Permissions()
        self.schemas = dict(schemas)
        self.logs = []

    @staticmethod
    def _stack_target_schema(item, _program):
        return item.context.get("target_schema_override")

    def _public_target_schema(self, _controller, schema, *, source_ref):
        del source_ref
        return self.schemas.get(schema["fixture"])

    @staticmethod
    def _stack_source_ref(item):
        return item.ref

    def _log(self, *args, **kwargs):
        self.logs.append((args, kwargs))


def _item(ref: str, fixture: str):
    return SimpleNamespace(
        ref=ref,
        controller="B",
        label=f"Trigger {ref}",
        semantic_key=None,
        context={
            "trigger_target_selection_pending": True,
            "target_schema_override": {"fixture": fixture},
        },
    )


class TriggerTargetingTests(unittest.TestCase):
    def test_dynamic_trigger_without_registry_program_issues_seat_choice(self):
        host = _Host(
            [_item("S1", "legal")],
            {"legal": {"legal_refs": ["A"], "count": 1}},
        )

        self.assertTrue(
            begin_pending_trigger_target_selection(
                host,
                decision_role="pilot",
                log_reason_field="reason",
            )
        )

        self.assertEqual(1, len(host.permissions.issued))
        issued = host.permissions.issued[0]
        self.assertEqual(["B"], issued["actors"])
        self.assertEqual("S1", issued["continuation"]["stack_ref"])
        self.assertEqual(
            "Choose legal targets for Trigger S1.",
            issued["payload_by_actor"]["B"]["prompt"],
        )

    def test_invalid_mandatory_trigger_is_removed_before_next_choice(self):
        invalid = _item("S1", "missing")
        legal = _item("S2", "legal")
        host = _Host(
            [invalid, legal],
            {
                "missing": None,
                "legal": {"legal_refs": ["A"], "count": 1},
            },
        )

        self.assertTrue(
            begin_pending_trigger_target_selection(
                host,
                decision_role="pilot",
                log_reason_field="reason",
            )
        )

        self.assertEqual([legal], host.state.stack)
        self.assertEqual(1, len(host.logs))
        self.assertEqual(
            "S2",
            host.permissions.issued[0]["continuation"]["stack_ref"],
        )


if __name__ == "__main__":
    unittest.main()
