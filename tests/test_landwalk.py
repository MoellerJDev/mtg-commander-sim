from __future__ import annotations

from itertools import combinations
from pathlib import Path
import tempfile
import unittest

from common import keep_all, load_assets, make_session
from mtg_commander_sim.combat_evasion import combat_evasion_verdict
from mtg_commander_sim.landwalk import (
    BASIC_LANDWALK_TYPES,
    BasicLandwalkBlockVerdict,
    LandwalkRuleError,
    basic_landwalk_block_verdict,
)
from mtg_commander_sim.model import CombatState
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)


class BasicLandwalkTests(unittest.TestCase):
    def test_each_basic_variant_uses_current_matching_land_subtype(self):
        for keyword, land_type in BASIC_LANDWALK_TYPES:
            with self.subTest(keyword=keyword):
                verdict = basic_landwalk_block_verdict(
                    frozenset({"landwalk", keyword}),
                    frozenset({land_type}),
                )
                self.assertEqual(
                    BasicLandwalkBlockVerdict(False, (land_type,)),
                    verdict,
                )
                self.assertTrue(
                    basic_landwalk_block_verdict(
                        frozenset({"landwalk", keyword}),
                        frozenset(),
                    ).allowed
                )

    def test_multiple_variants_are_cumulative_and_repeated_instances_redundant(self):
        verdict = basic_landwalk_block_verdict(
            frozenset(
                {
                    "landwalk",
                    "islandwalk",
                    "swampwalk",
                    "forestwalk",
                }
            ),
            frozenset({"forest", "swamp", "mountain"}),
        )

        self.assertEqual(("swamp", "forest"), verdict.matching_land_types)
        self.assertEqual("attacker_has_swampwalk", verdict.reason)

    def test_basic_landwalk_holds_across_the_bounded_keyword_land_grid(self):
        pairs = tuple(BASIC_LANDWALK_TYPES)
        for keyword_count in range(len(pairs) + 1):
            for selected_keywords in combinations(pairs, keyword_count):
                keywords = frozenset(keyword for keyword, _ in selected_keywords)
                selected_types = {
                    land_type for _, land_type in selected_keywords
                }
                for land_count in range(len(pairs) + 1):
                    for selected_lands in combinations(pairs, land_count):
                        land_types = frozenset(
                            land_type for _, land_type in selected_lands
                        )
                        with self.subTest(
                            keywords=keywords,
                            land_types=land_types,
                        ):
                            self.assertEqual(
                                not bool(selected_types.intersection(land_types)),
                                basic_landwalk_block_verdict(
                                    keywords,
                                    land_types,
                                ).allowed,
                            )

    def test_malformed_and_unsupported_variants_fail_closed(self):
        with self.assertRaisesRegex(LandwalkRuleError, "attacker"):
            basic_landwalk_block_verdict({"swampwalk"}, frozenset())
        with self.assertRaisesRegex(LandwalkRuleError, "land type"):
            basic_landwalk_block_verdict(
                frozenset({"swampwalk"}), frozenset({"desert"})
            )
        for unsupported in (
            "landwalk",
            "desertwalk",
            "legendary landwalk",
            "nonbasic landwalk",
        ):
            with self.subTest(unsupported=unsupported):
                with self.assertRaisesRegex(
                    LandwalkRuleError, "Unsupported landwalk"
                ):
                    basic_landwalk_block_verdict(
                        frozenset({unsupported}), frozenset()
                    )
        with self.assertRaisesRegex(LandwalkRuleError, "requires"):
            BasicLandwalkBlockVerdict(False)

    def test_landwalk_remains_cumulative_with_shadow_and_flying(self):
        self.assertEqual(
            "attacker_has_swampwalk",
            combat_evasion_verdict(
                frozenset({"flying", "swampwalk", "landwalk"}),
                frozenset({"reach"}),
                frozenset({"swamp"}),
            ).reason,
        )
        self.assertEqual(
            "attacker_has_islandwalk",
            combat_evasion_verdict(
                frozenset({"shadow", "islandwalk", "landwalk"}),
                frozenset({"shadow"}),
                frozenset({"island"}),
            ).reason,
        )


class BasicLandwalkIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_session(self, seed: int):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=4,
            seed=seed,
            auto_pass_empty=False,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.state.priority_passes = []
        engine.state.phase = "combat"
        engine.state.step = "declare_blockers"
        session.commands.clear()
        session.decisions.clear()
        return session

    @staticmethod
    def permanent(engine, controller: str, name: str, type_line: str, *, keywords=()):
        ref = engine.create_token(
            controller,
            name=name,
            characteristics={
                "type_line": type_line,
                "power": "2" if "Creature" in type_line else None,
                "toughness": "2" if "Creature" in type_line else None,
                "keywords": list(keywords),
            },
        )[0]
        return engine._resolve_object(
            controller,
            ref,
            zones={"battlefield"},
        )

    def prepare_block(self, session, *, with_matching_land: bool):
        engine = session.engine
        attacker = self.permanent(
            engine,
            "A",
            "Current Swampwalker",
            "Token Creature — Test",
            keywords=("Landwalk", "Swampwalk", "SWAMPWALK"),
        )
        blocker = self.permanent(
            engine,
            "C",
            "C blocker",
            "Token Creature — Test",
        )
        if with_matching_land:
            self.permanent(
                engine,
                "C",
                "Nonbasic Swamp",
                "Token Land — Swamp",
            )
            ordinary = self.permanent(
                engine,
                "A",
                "Ordinary attacker",
                "Token Creature — Test",
            )
            ordinary.attacking = "C"
        attacker.attacking = "C"
        attackers = {attacker.object_id: "C"}
        if with_matching_land:
            attackers[ordinary.object_id] = "C"
        engine.state.combat = CombatState(
            attackers_declared=True,
            had_attacking_creature=True,
            attackers=attackers,
            defending_players=["C"],
        )
        engine._begin_blocker_decisions()
        return attacker, blocker

    def test_offer_and_command_share_current_landwalk_legality_and_rollback(self):
        session = self.make_session(702_014_001)
        attacker, blocker = self.prepare_block(
            session,
            with_matching_land=True,
        )
        decision = session.packet("pilot:C", full=True)["decision"]
        self.assertNotIn(
            attacker.ref,
            decision["ctx"]["legal_blocks"][blocker.ref],
        )
        for hidden_seat in ("A", "B", "D"):
            self.assertIsNone(
                session.packet(f"pilot:{hidden_seat}", full=True)["decision"]
            )

        before = authoritative_state_hash(session.state)
        rejected = session.act(
            "pilot:C",
            {"a": "block", "blk": {blocker.ref: attacker.ref}},
        )
        self.assertFalse(rejected.ok)
        self.assertIn("swampwalk", rejected.summary)
        self.assertEqual(before, authoritative_state_hash(session.state))

    def test_legal_nonmatching_block_is_seat_scoped_and_replays(self):
        session = self.make_session(702_014_002)
        attacker, blocker = self.prepare_block(
            session,
            with_matching_land=False,
        )
        decision = session.packet("pilot:C", full=True)["decision"]
        self.assertEqual(
            [attacker.ref],
            decision["ctx"]["legal_blocks"][blocker.ref],
        )
        session.initial_checkpoint = checkpoint_envelope(session.state)

        accepted = session.act(
            "pilot:C",
            {"a": "block", "blk": {blocker.ref: attacker.ref}},
        )
        self.assertTrue(accepted.ok, accepted.summary)
        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "basic-landwalk"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(1, replay["commands"])


if __name__ == "__main__":
    unittest.main()
