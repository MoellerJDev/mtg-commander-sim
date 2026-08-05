from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from common import keep_all, load_assets, make_session
from mtg_commander_sim.card_programs import compile_card_program
from mtg_commander_sim.carddb import CardRecord
from mtg_commander_sim.compiled_cast_timing import (
    compiled_cast_timing_permissions,
)
from mtg_commander_sim.cast_timing import (
    CastTimingPermission,
    canonical_cast_timing_permissions,
)
from mtg_commander_sim.oracle_ir import generated_programs
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)
from mtg_commander_sim.rules.capabilities import (
    load_default_capability_registry,
)
from mtg_commander_sim.rules.casting.proposal import build_cast_offer
from mtg_commander_sim.semantic_runtime import SemanticNodeError
from mtg_commander_sim.semantic_runtime.cast_permissions import (
    default_cast_permission_registry,
)
from mtg_commander_sim.semantics import SemanticRegistry


class _NoRulingsDatabase:
    @staticmethod
    def rulings(record):
        del record
        return ()


def _two_face_record() -> CardRecord:
    return CardRecord(
        oracle_id="fixture:face-pinned-flash",
        name="Daybound Adept // Nightfall Adept",
        mana_cost="{2}{U} // {2}{U}",
        mana_value=3.0,
        type_line="Creature — Human // Creature — Human",
        oracle_text="Flying\n//\nFlash, flying",
        power="2",
        toughness="2",
        loyalty=None,
        defense=None,
        colors=("U",),
        color_identity=("U",),
        keywords=("Flash", "Flying"),
        produced_mana=(),
        layout="transform",
        released_at="2026-01-01",
        legalities={"commander": "legal"},
        faces=(
            {
                "name": "Daybound Adept",
                "mana_cost": "{2}{U}",
                "type_line": "Creature — Human",
                "oracle_text": "Flying",
                "keywords": ["Flying"],
            },
            {
                "name": "Nightfall Adept",
                "mana_cost": "{2}{U}",
                "type_line": "Creature — Human",
                "oracle_text": "Flash, flying",
                "keywords": ["Flash", "Flying"],
            },
        ),
        raw={},
    )


class FlashCastTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    @staticmethod
    def card(engine, seat: str, name: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == seat and card.printed_name == name
        )

    def off_turn_fixture(self, *, players: int = 2, seed: int = 7020801):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=players,
            seed=seed,
        )
        keep_all(session)
        engine = session.engine
        endurance = self.card(engine, "B", "Endurance")
        engine.move_card(endurance.object_id, "hand", log=False)
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.stack.clear()
        engine.state.priority_passes = []
        engine.state.pending_decision = None
        engine.permissions.invalidate_current()
        engine.state.priority_player = None
        engine.state.players["B"].mana_pool.update(
            {"C": 1, "G": 2}
        )
        engine._grant_priority("B")
        engine.pump()
        return session, endurance

    def test_flash_offer_and_cast_use_same_compiled_permission(self):
        session, endurance = self.off_turn_fixture()
        packet = session.packet("pilot:B", full=True)
        offer = next(
            action
            for action in packet["decision"]["ctx"]["legal"]["actions"]
            if action.get("kind") == "cast"
            and action.get("card") == endurance.ref
        )
        self.assertEqual("cast", offer["kind"])

        result = session.act(
            "pilot:B",
            {
                "a": "cast",
                "card": endurance.ref,
                "pay": "manual",
                "payment": {"C": 1, "G": 2},
            },
        )

        self.assertTrue(result.ok, result.summary)
        self.assertEqual("stack", endurance.zone)
        self.assertEqual(
            endurance.object_id,
            session.state.stack[0].card_object_id,
        )

    def test_raw_flash_keyword_without_compiled_permission_fails_closed(self):
        session, endurance = self.off_turn_fixture(seed=7020802)
        record = session.engine.card_record(endurance)
        self.assertIn("Flash", record.keywords)
        self.assertTrue(record.oracle_text.startswith("Flash"))

        with patch(
            "mtg_commander_sim.rules.casting.proposal."
            "compiled_cast_timing_permissions",
            return_value=(),
        ):
            result = build_cast_offer(session.engine, "B", endurance)

        self.assertEqual("unavailable", result.status)
        self.assertEqual("timing", result.reason)

    def test_flash_permission_is_face_pinned(self):
        record = _two_face_record()
        capabilities = load_default_capability_registry()
        programs = generated_programs(
            _NoRulingsDatabase(),
            record,
            trust_level="trusted",
            capability_registry=capabilities,
            capability_profile="commander_review",
        )
        registry = SemanticRegistry(include_builtin_packs=False)
        for program in programs:
            registry.put(program)

        class Host:
            semantics = registry

            @staticmethod
            def card_record(card):
                del card
                return record

            @staticmethod
            def semantic_program_is_current_trusted(program):
                return program.trust_level == "trusted"

        self.assertEqual(
            (),
            compiled_cast_timing_permissions(
                Host(), object(), face_name="Daybound Adept"
            ),
        )
        permissions = compiled_cast_timing_permissions(
            Host(), object(), face_name="Nightfall Adept"
        )
        self.assertEqual(1, len(permissions))
        self.assertEqual("instant", permissions[0].timing)

        card_program = compile_card_program(
            _NoRulingsDatabase(),
            record,
            capability_registry=capabilities,
            capability_profile="commander_review",
            trust_level="trusted",
        )
        permission = next(
            ability
            for ability in card_program.abilities
            if ability.ability_id.endswith(":flash")
        )
        self.assertEqual(
            "Nightfall Adept", permission.provenance["face_id"]
        )
        self.assertEqual("playable", permission.active_zone)
        self.assertEqual("cast.permission", permission.event)
        self.assertEqual(1, permission.provenance["source_span"]["line"])

    def test_flash_handler_rejects_malformed_descriptors(self):
        registry = default_cast_permission_registry()
        valid = {
            "handler_id": "ability.static.flash.v1",
            "schema_version": 1,
            "event": "cast.permission",
            "permission": {
                "schema_version": 1,
                "timing": "instant",
                "scope": "this_face",
            },
        }
        for malformed in (
            {**valid, "unknown": True},
            {**valid, "schema_version": 2},
            {**valid, "schema_version": True},
            {**valid, "event": "continuous"},
            {**valid, "permission": []},
            {
                **valid,
                "permission": {
                    **valid["permission"],
                    "schema_version": True,
                },
            },
            {
                **valid,
                "permission": {
                    **valid["permission"],
                    "scope": "all_cards",
                },
            },
        ):
            with self.subTest(malformed=malformed):
                with self.assertRaises(SemanticNodeError):
                    registry.validate(malformed)

    def test_multiple_flash_instances_are_redundant(self):
        permission = CastTimingPermission()
        self.assertEqual(
            (permission,),
            canonical_cast_timing_permissions((permission, permission)),
        )

    def test_failed_flash_cast_rolls_back(self):
        session, endurance = self.off_turn_fixture(seed=7020803)
        before = authoritative_state_hash(session.state)

        result = session.act(
            "pilot:B",
            {
                "a": "cast",
                "card": endurance.ref,
                "pay": "manual",
                "payment": {"G": 1},
            },
        )

        self.assertFalse(result.ok)
        self.assertEqual(before, authoritative_state_hash(session.state))
        self.assertEqual("hand", session.state.cards[endurance.object_id].zone)

    def test_flash_cast_is_seat_local_in_four_player_game(self):
        session, endurance = self.off_turn_fixture(
            players=4,
            seed=7020804,
        )
        b_actions = session.engine._priority_action_hints("B")["actions"]
        a_actions = session.engine._priority_action_hints("A")["actions"]

        self.assertTrue(
            any(action.get("card") == endurance.ref for action in b_actions)
        )
        self.assertFalse(
            any(action.get("card") == endurance.ref for action in a_actions)
        )

    def test_flash_offer_preserves_private_hand_projection(self):
        session, endurance = self.off_turn_fixture(seed=7020805)
        owner_packet = session.packet("pilot:B", full=True)
        opponent_packet = session.packet("pilot:A", full=True)

        self.assertIn(
            endurance.ref,
            json.dumps(owner_packet, sort_keys=True),
        )
        self.assertNotIn(
            endurance.ref,
            json.dumps(opponent_packet, sort_keys=True),
        )
        self.assertNotIn(
            endurance.printed_name,
            json.dumps(opponent_packet["state"], sort_keys=True),
        )

    def test_flash_cast_replays_exactly(self):
        session, endurance = self.off_turn_fixture(seed=7020806)
        session.initial_checkpoint = checkpoint_envelope(session.state)
        session.commands.clear()
        session.decisions.clear()

        result = session.act(
            "pilot:B",
            {
                "a": "cast",
                "card": endurance.ref,
                "pay": "manual",
                "payment": {"C": 1, "G": 2},
            },
        )
        self.assertTrue(result.ok, result.summary)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "flash-cast-replay"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)


if __name__ == "__main__":
    unittest.main()
