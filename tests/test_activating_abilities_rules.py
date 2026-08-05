from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mtg_commander_sim.abilities import (
    ActivatedAbility,
    parse_activated_abilities,
)

from common import keep_all, load_assets, make_session
from mtg_commander_sim.record import checkpoint_envelope, replay_record


class ActivatingAbilityRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_engine(self, seed: int):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=seed,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = "A"
        engine.state.priority_passes = []
        engine.state.stack.clear()
        return engine

    @staticmethod
    def card(engine, owner: str, name: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == owner
            and card.is_card_object
            and card.printed_name == name
        )

    def test_contract_traces_every_cr_602_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "activating-activated-abilities.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {
                "602",
                "602.1",
                "602.1a",
                "602.1b",
                "602.1c",
                "602.1d",
                "602.1e",
                "602.2",
                "602.2a",
                "602.2b",
                "602.3",
                "602.3a",
                "602.3b",
                "602.4",
                "602.5",
                "602.5a",
                "602.5b",
                "602.5c",
                "602.5d",
                "602.5e",
            },
            {
                rule_id
                for rule_id in contract["rule_references"]
                if str(rule_id).startswith("602")
            },
        )

    def test_only_colon_form_activated_abilities_are_parsed(self):
        self.assertEqual(
            (),
            parse_activated_abilities(
                card_name="Triggered Test",
                oracle_text=(
                    "When this permanent enters, draw a card.\n"
                    "Flying"
                ),
            ),
        )
        abilities = parse_activated_abilities(
            card_name="Activated Test",
            oracle_text="{1}, {T}: Draw a card.",
        )
        self.assertEqual(1, len(abilities))
        self.assertEqual("{1}, {T}", abilities[0].cost_text)
        self.assertEqual("Draw a card.", abilities[0].effect_text)

    def test_untap_symbol_obeys_summoning_sickness_and_haste(self):
        engine = self.make_engine(60201)
        creature = self.card(engine, "A", "Goblin Engineer")
        engine.move_card(
            creature.object_id,
            "battlefield",
            controller="A",
            tapped=True,
            log=False,
        )
        ability = ActivatedAbility(
            ability_id="ab-untap",
            line_index=0,
            oracle_line="{Q}: Draw a card.",
            cost_text="{Q}",
            effect_text="Draw a card.",
            zones=("battlefield",),
            mana={},
            untap_source=True,
        )

        self.assertEqual(
            ("unavailable", "summoning_sickness"),
            engine._ability_availability("A", creature, ability),
        )
        creature.temporary_keywords.extend(("haste", "HASTE"))
        self.assertEqual(
            ("payable", None),
            engine._ability_availability("A", creature, ability),
        )

    def test_sick_mana_creature_requires_haste_or_as_though_permission(self):
        engine = self.make_engine(60214)
        creature = self.card(engine, "B", "Elves of Deep Shadow")
        engine.move_card(
            creature.object_id,
            "battlefield",
            controller="B",
            tapped=False,
            log=False,
        )

        self.assertNotIn(
            creature.object_id,
            {
                source.object_id
                for source in engine.available_mana_sources("B")
            },
        )
        creature.temporary_keywords.append("haste")
        self.assertIn(
            creature.object_id,
            {
                source.object_id
                for source in engine.available_mana_sources("B")
            },
        )

        creature.temporary_keywords.clear()
        with patch.object(
            engine,
            "_may_activate_creature_as_haste",
            return_value=True,
        ):
            self.assertIn(
                creature.object_id,
                {
                    source.object_id
                    for source in engine.available_mana_sources("B")
                },
            )

    def test_haste_activation_is_seat_local_in_four_player_game(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=4,
            seed=60215,
        )
        keep_all(session)
        engine = session.engine
        creature = self.card(engine, "B", "Elves of Deep Shadow")
        engine.move_card(
            creature.object_id,
            "battlefield",
            controller="B",
            tapped=True,
            log=False,
        )
        ability = ActivatedAbility(
            ability_id="ab-four-player-untap",
            line_index=0,
            oracle_line="{Q}: Add {B}.",
            cost_text="{Q}",
            effect_text="Add {B}.",
            zones=("battlefield",),
            mana={},
            untap_source=True,
        )

        self.assertEqual(
            ("unavailable", "summoning_sickness"),
            engine._ability_availability("B", creature, ability),
        )
        creature.temporary_keywords.append("haste")
        self.assertEqual(
            ("payable", None),
            engine._ability_availability("B", creature, ability),
        )

    def test_haste_mana_activation_replays_exactly(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=60216,
        )
        keep_all(session)
        engine = session.engine
        creature = self.card(engine, "B", "Elves of Deep Shadow")
        engine.move_card(
            creature.object_id,
            "battlefield",
            controller="B",
            tapped=False,
            log=False,
        )
        creature.temporary_keywords.append("haste")
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine._grant_priority("B")
        engine.pump()
        ability = next(
            row
            for row in session.packet("pilot:B")["decision"]["ctx"][
                "legal"
            ]["mana_abilities"]
            if row["s"] == creature.ref
        )
        session.initial_checkpoint = checkpoint_envelope(session.state)
        session.commands.clear()
        session.decisions.clear()

        result = session.act(
            "pilot:B",
            {
                "a": "x",
                "source": creature.ref,
                "ability": ability["a"],
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertTrue(creature.tapped)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "haste-mana-replay"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)

    def test_once_per_turn_restriction_survives_control_change(self):
        engine = self.make_engine(60202)
        source = self.card(engine, "A", "Sensei's Divining Top")
        engine.move_card(
            source.object_id,
            "battlefield",
            controller="A",
            tapped=False,
            log=False,
        )
        ability = ActivatedAbility(
            ability_id="ab-once",
            line_index=0,
            oracle_line=(
                "{0}: Draw a card. Activate only once each turn."
            ),
            cost_text="{0}",
            effect_text=(
                "Draw a card. Activate only once each turn."
            ),
            zones=("battlefield",),
            mana={},
        )

        with patch.object(
            engine,
            "_activated_abilities",
            return_value=(ability,),
        ):
            engine._activate(
                "A",
                {
                    "source": source.ref,
                    "ability": ability.ability_id,
                },
            )

        engine.change_control(
            source.object_id,
            "B",
            reason="CR 602.5b control-change witness",
        )
        engine.state.stack.clear()
        engine.state.priority_player = "B"
        self.assertEqual(
            ("unavailable", "already_activated_this_turn"),
            engine._ability_availability("B", source, ability),
        )

        engine.state.turn_sequence += 1
        self.assertEqual(
            ("payable", None),
            engine._ability_availability("B", source, ability),
        )

    def test_sorcery_and_instant_activation_instructions_use_right_timing(self):
        engine = self.make_engine(60203)
        source = self.card(engine, "A", "Sensei's Divining Top")
        engine.move_card(
            source.object_id,
            "battlefield",
            controller="A",
            tapped=False,
            log=False,
        )
        sorcery = parse_activated_abilities(
            card_name="Sorcery-speed Test",
            oracle_text=(
                "{0}: Draw a card. Activate only as a sorcery."
            ),
        )[0]
        instant = parse_activated_abilities(
            card_name="Instant-speed Test",
            oracle_text=(
                "{0}: Draw a card. Activate only as an instant."
            ),
        )[0]
        self.assertTrue(sorcery.sorcery_speed)
        self.assertFalse(instant.sorcery_speed)

        engine.state.active_player = "B"
        engine.state.phase = "combat"
        engine.state.step = "beginning_combat"
        engine.state.priority_player = "A"
        self.assertEqual(
            ("unavailable", "sorcery_timing"),
            engine._ability_availability("A", source, sorcery),
        )
        self.assertEqual(
            ("payable", None),
            engine._ability_availability("A", source, instant),
        )

        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        self.assertEqual(
            ("payable", None),
            engine._ability_availability("A", source, sorcery),
        )


if __name__ == "__main__":
    unittest.main()
