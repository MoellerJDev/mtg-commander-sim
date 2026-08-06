from __future__ import annotations

import unittest

from common import load_assets, make_session
from mtg_commander_sim.errors import GameRuleError
from mtg_commander_sim.targets import TargetGroup


class ExactCombatKeywordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_session(self, seed: int):
        session = make_session(
            self.db, self.mishra, self.zimone, seed=seed
        )
        session.engine.permissions.invalidate_current()
        session.state.pending_decision = None
        return session

    @staticmethod
    def card(engine, name: str, owner: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == owner and card.printed_name == name
        )

    def test_flying_attacker_exposes_only_flying_or_reach_blockers(self):
        session = self.make_session(831)
        engine = session.engine
        bird = self.card(engine, "Birds of Paradise", "B")
        reach = self.card(engine, "Endurance", "B")
        ground = self.card(engine, "Mishra, Eminent One", "A")
        engine.move_card(
            bird.object_id, "battlefield", controller="A", tapped=False
        )
        for blocker in (reach, ground):
            engine.move_card(
                blocker.object_id,
                "battlefield",
                controller="B",
                tapped=False,
            )
        engine.state.active_player = "A"
        engine.state.combat.attackers = {bird.object_id: "B"}
        bird.attacking = "B"
        engine.state.combat.defending_players = ["B"]
        engine.state.combat.blocker_cursor = 0

        engine._issue_next_blocker()
        packet = session.packet("pilot:B", full=True)
        legal = packet["decision"]["ctx"]["legal_blocks"]

        self.assertEqual([bird.ref], legal[reach.ref])
        self.assertNotIn(ground.ref, legal)

    def test_shadow_and_protection_restrict_blocking(self):
        session = self.make_session(832)
        engine = session.engine
        dauthi = self.card(engine, "Dauthi Voidwalker", "B")
        scryb = self.card(engine, "Scryb Ranger", "B")
        faerie = self.card(engine, "Faerie Mastermind", "B")
        for card, controller in (
            (dauthi, "A"),
            (scryb, "A"),
            (faerie, "B"),
        ):
            engine.move_card(
                card.object_id,
                "battlefield",
                controller=controller,
                tapped=False,
            )

        self.assertFalse(engine._can_block(dauthi, faerie)[0])
        self.assertFalse(engine._can_block(scryb, dauthi)[0])
        self.assertFalse(engine._can_block(scryb, faerie)[0])

    def test_protection_removes_colored_source_from_target_candidates(self):
        session = self.make_session(833)
        engine = session.engine
        protected = self.card(engine, "Scryb Ranger", "B")
        blue_source = self.card(engine, "Faerie Mastermind", "B")
        green_source = self.card(engine, "Endurance", "B")
        for card, controller in (
            (protected, "B"),
            (blue_source, "A"),
            (green_source, "A"),
        ):
            engine.move_card(
                card.object_id,
                "battlefield",
                controller=controller,
                tapped=False,
            )
        group = TargetGroup.from_mapping(
            {
                "zones": ["battlefield"],
                "categories": ["permanent"],
                "types_any": ["creature"],
                "min": 1,
                "max": 1,
            },
            default_id="creature",
        )
        row = next(
            candidate
            for candidate in engine._target_candidate_rows("A", group)
            if candidate["ref"] == protected.ref
        )

        self.assertFalse(
            engine._target_row_matches(
                "A",
                group,
                row,
                source_ref=blue_source.ref,
            )
        )
        self.assertTrue(
            engine._target_row_matches(
                "A",
                group,
                row,
                source_ref=green_source.ref,
            )
        )

    def test_deathtouch_is_derived_from_source_not_pilot_claim(self):
        session = self.make_session(834)
        engine = session.engine
        target = self.card(engine, "Mishra, Eminent One", "A")
        engine.move_card(
            target.object_id,
            "battlefield",
            controller="B",
            tapped=False,
        )
        snake_ref = engine.create_token(
            "A",
            name="Snake",
            characteristics={
                "type_line": "Creature — Snake",
                "power": "1",
                "toughness": "1",
                "keywords": ["Deathtouch"],
                "colors": ["B"],
            },
        )[0]

        with self.assertRaisesRegex(
            GameRuleError,
            "Combat damage assignments are malformed",
        ):
            engine._apply_combat_assignments(
                [
                    {
                        "source": snake_ref,
                        "target": target.ref,
                        "amount": 1,
                        "deathtouch": False,
                    }
                ]
            )

        engine._apply_combat_assignments(
            [{"source": snake_ref, "target": target.ref, "amount": 1}]
        )

        self.assertEqual("graveyard", target.zone)
