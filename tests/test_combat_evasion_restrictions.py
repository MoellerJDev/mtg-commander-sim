from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from common import keep_all, load_assets, make_session
from quorune.combat_evasion import (
    CombatantEvasionCharacteristics,
    CombatEvasionRuleError,
    combat_evasion_verdict,
)
from quorune.model import CombatState
from quorune.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)


def _combatant(
    *keywords: str,
    colors: tuple[str, ...] = (),
    card_types: tuple[str, ...] = ("creature",),
    power: int | None = 2,
) -> CombatantEvasionCharacteristics:
    return CombatantEvasionCharacteristics(
        keywords=frozenset(keywords),
        colors=frozenset(colors),
        card_types=frozenset(card_types),
        power=power,
    )


class CombatEvasionRestrictionTests(unittest.TestCase):
    def verdict(
        self,
        attacker: CombatantEvasionCharacteristics,
        blocker: CombatantEvasionCharacteristics,
    ):
        return combat_evasion_verdict(attacker, blocker, frozenset())

    def test_shadow_is_symmetric_and_horsemanship_is_not(self):
        self.assertEqual(
            "attacker_has_shadow",
            self.verdict(_combatant("shadow"), _combatant()).reason,
        )
        self.assertEqual(
            "blocker_has_shadow",
            self.verdict(_combatant(), _combatant("shadow")).reason,
        )
        self.assertTrue(
            self.verdict(_combatant("shadow"), _combatant("shadow")).allowed
        )
        self.assertEqual(
            "attacker_has_horsemanship",
            self.verdict(_combatant("horsemanship"), _combatant()).reason,
        )
        self.assertTrue(
            self.verdict(_combatant(), _combatant("horsemanship")).allowed
        )

    def test_fear_accepts_black_or_artifact_blockers(self):
        attacker = _combatant("fear", colors=("B",))
        self.assertTrue(
            self.verdict(attacker, _combatant(colors=("B",))).allowed
        )
        self.assertTrue(
            self.verdict(
                attacker,
                _combatant(card_types=("artifact", "creature")),
            ).allowed
        )
        self.assertEqual(
            "attacker_has_fear",
            self.verdict(attacker, _combatant(colors=("G",))).reason,
        )

    def test_intimidate_accepts_artifacts_or_a_shared_color(self):
        attacker = _combatant("intimidate", colors=("G", "U"))
        self.assertTrue(
            self.verdict(attacker, _combatant(colors=("U",))).allowed
        )
        self.assertTrue(
            self.verdict(
                attacker,
                _combatant(card_types=("artifact", "creature")),
            ).allowed
        )
        self.assertEqual(
            "attacker_has_intimidate",
            self.verdict(attacker, _combatant(colors=("B",))).reason,
        )
        self.assertEqual(
            "attacker_has_intimidate",
            self.verdict(
                _combatant("intimidate"),
                _combatant(colors=("B",)),
            ).reason,
        )

    def test_skulk_compares_exact_current_power(self):
        attacker = _combatant("skulk", power=2)
        self.assertTrue(self.verdict(attacker, _combatant(power=1)).allowed)
        self.assertTrue(self.verdict(attacker, _combatant(power=2)).allowed)
        self.assertEqual(
            "attacker_has_skulk",
            self.verdict(attacker, _combatant(power=3)).reason,
        )
        self.assertTrue(
            self.verdict(
                _combatant("skulk", power=-2),
                _combatant(power=-2),
            ).allowed
        )

    def test_all_represented_restrictions_are_cumulative(self):
        attacker = _combatant(
            "fear",
            "horsemanship",
            "intimidate",
            "shadow",
            "skulk",
            colors=("G",),
            power=2,
        )
        legal = _combatant(
            "horsemanship",
            "shadow",
            card_types=("artifact", "creature"),
            power=2,
        )
        self.assertTrue(self.verdict(attacker, legal).allowed)
        self.assertEqual(
            "attacker_has_intimidate",
            self.verdict(
                attacker,
                _combatant(
                    "horsemanship",
                    "shadow",
                    colors=("B",),
                    power=2,
                ),
            ).reason,
        )

    def test_keyword_bundle_holds_across_bounded_blocker_grid(self):
        for colors in ((), ("B",), ("G",)):
            for artifact in (False, True):
                for power in (1, 2, 3):
                    for shadow in (False, True):
                        for horsemanship in (False, True):
                            blocker_keywords = tuple(
                                keyword
                                for keyword, present in (
                                    ("shadow", shadow),
                                    ("horsemanship", horsemanship),
                                )
                                if present
                            )
                            blocker = _combatant(
                                *blocker_keywords,
                                colors=colors,
                                card_types=(
                                    ("artifact", "creature")
                                    if artifact
                                    else ("creature",)
                                ),
                                power=power,
                            )
                            expectations = {
                                "fear": artifact or "B" in colors,
                                "horsemanship": horsemanship,
                                "intimidate": artifact or "G" in colors,
                                "shadow": shadow,
                                "skulk": power <= 2,
                            }
                            for keyword, expected in expectations.items():
                                expected = expected and (
                                    not shadow or keyword == "shadow"
                                )
                                with self.subTest(
                                    keyword=keyword,
                                    colors=colors,
                                    artifact=artifact,
                                    power=power,
                                    shadow=shadow,
                                    horsemanship=horsemanship,
                                ):
                                    attacker = _combatant(
                                        keyword,
                                        colors=("G",),
                                        power=2,
                                    )
                                    self.assertEqual(
                                        expected,
                                        self.verdict(attacker, blocker).allowed,
                                    )

    def test_malformed_and_unresolved_inputs_fail_closed(self):
        for malformed in (
            {"keywords": {"fear"}},
            {"colors": frozenset({"black"})},
            {"card_types": frozenset({"creature", "vehicle"})},
            {"power": True},
        ):
            values = {
                "keywords": frozenset(),
                "colors": frozenset(),
                "card_types": frozenset({"creature"}),
                "power": 2,
                **malformed,
            }
            with self.subTest(malformed=malformed):
                with self.assertRaises(CombatEvasionRuleError):
                    CombatantEvasionCharacteristics(**values)
        with self.assertRaisesRegex(CombatEvasionRuleError, "Skulk"):
            self.verdict(
                _combatant("skulk", power=None),
                _combatant(power=2),
            )
        with self.assertRaisesRegex(CombatEvasionRuleError, "typed"):
            combat_evasion_verdict(
                frozenset({"fear"}),
                _combatant(),
                frozenset(),
            )


class CombatEvasionIntegrationTests(unittest.TestCase):
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
    def creature(
        engine,
        controller: str,
        name: str,
        *,
        keywords=(),
        colors=(),
        power: int = 2,
        artifact: bool = False,
    ):
        ref = engine.create_token(
            controller,
            name=name,
            characteristics={
                "type_line": (
                    "Token Artifact Creature — Test"
                    if artifact
                    else "Token Creature — Test"
                ),
                "colors": list(colors),
                "power": str(power),
                "toughness": "4",
                "keywords": list(keywords),
            },
        )[0]
        return engine._resolve_object(
            controller,
            ref,
            zones={"battlefield"},
        )

    def prepare_skulk_intimidate_block(self, session):
        engine = session.engine
        attacker = self.creature(
            engine,
            "A",
            "Current evasion attacker",
            keywords=("Intimidate", "Skulk", "INTIMIDATE"),
            colors=("G",),
            power=2,
        )
        legal = self.creature(
            engine,
            "C",
            "Legal current blocker",
            colors=("G",),
            power=2,
        )
        too_large = self.creature(
            engine,
            "C",
            "Large current blocker",
            colors=("G",),
            power=3,
        )
        wrong_color = self.creature(
            engine,
            "C",
            "Wrong-color current blocker",
            colors=("B",),
            power=1,
        )
        attacker.attacking = "C"
        engine.state.combat = CombatState(
            attackers_declared=True,
            had_attacking_creature=True,
            attackers={attacker.object_id: "C"},
            defending_players=["C"],
        )
        engine._begin_blocker_decisions()
        return attacker, legal, too_large, wrong_color

    def test_offer_and_command_share_cumulative_legality_and_rollback(self):
        session = self.make_session(702_118_001)
        attacker, legal, too_large, wrong_color = (
            self.prepare_skulk_intimidate_block(session)
        )
        decision = session.packet("pilot:C", full=True)["decision"]
        self.assertEqual([attacker.ref], decision["ctx"]["legal_blocks"][legal.ref])
        self.assertNotIn(too_large.ref, decision["ctx"]["legal_blocks"])
        self.assertNotIn(wrong_color.ref, decision["ctx"]["legal_blocks"])
        for hidden_seat in ("A", "B", "D"):
            self.assertIsNone(
                session.packet(f"pilot:{hidden_seat}", full=True)["decision"]
            )

        before = authoritative_state_hash(session.state)
        rejected = session.act(
            "pilot:C",
            {"a": "block", "blk": {too_large.ref: attacker.ref}},
        )
        self.assertFalse(rejected.ok)
        self.assertIn("skulk", rejected.summary)
        self.assertEqual(before, authoritative_state_hash(session.state))

    def test_legal_block_replays_exactly_in_four_player_combat(self):
        session = self.make_session(702_118_002)
        attacker, legal, _, _ = self.prepare_skulk_intimidate_block(session)
        session.initial_checkpoint = checkpoint_envelope(session.state)

        accepted = session.act(
            "pilot:C",
            {"a": "block", "blk": {legal.ref: attacker.ref}},
        )
        self.assertTrue(accepted.ok, accepted.summary)
        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "combat-evasion"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(1, replay["commands"])


if __name__ == "__main__":
    unittest.main()
