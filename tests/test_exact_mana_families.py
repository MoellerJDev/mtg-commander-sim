from __future__ import annotations

import unittest

from common import keep_all, load_assets, make_session


class ExactManaFamilyTests(unittest.TestCase):
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
            players=2,
            seed=seed,
        )
        keep_all(session)
        session.engine.permissions.invalidate_current()
        session.state.pending_decision = None
        session.state.priority_player = None
        return session

    @staticmethod
    def card(engine, owner: str, name: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == owner and card.printed_name == name
        )

    def test_ashnods_altar_sacrifices_exactly_one_creature_for_two_colorless(
        self,
    ):
        session = self.make_session(870)
        engine = session.engine
        altar = self.card(engine, "A", "Ashnod's Altar")
        creature = self.card(engine, "A", "Goblin Engineer")
        for card in (altar, creature):
            engine.move_card(
                card.object_id,
                "battlefield",
                controller="A",
                log=False,
            )
        engine.state.priority_player = "A"
        engine._activate(
            "A",
            {
                "source": altar.ref,
                "ability": "ab1",
                "cost_cards": [creature.ref],
            },
        )
        self.assertEqual("graveyard", creature.zone)
        self.assertEqual(2, engine.state.players["A"].mana_pool["C"])
        self.assertFalse(engine.state.stack)

    def test_mana_confluence_pays_life_and_produces_selected_color(self):
        session = self.make_session(871)
        engine = session.engine
        confluence = self.card(engine, "A", "Mana Confluence")
        engine.move_card(
            confluence.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        before_life = engine.state.players["A"].life
        engine.state.priority_player = "A"
        engine._activate(
            "A",
            {
                "source": confluence.ref,
                "ability": "ab1",
                "mana_choice": "G",
            },
        )
        self.assertEqual(before_life - 1, engine.state.players["A"].life)
        self.assertEqual(1, engine.state.players["A"].mana_pool["G"])
        self.assertTrue(confluence.tapped)

    def test_fellwar_stone_and_exotic_orchard_use_live_opponent_land_colors(
        self,
    ):
        session = self.make_session(872)
        engine = session.engine
        stone = self.card(engine, "A", "Fellwar Stone")
        orchard = self.card(engine, "A", "Exotic Orchard")
        island = self.card(engine, "B", "Island")
        forest = self.card(engine, "B", "Forest")
        for card, controller in (
            (stone, "A"),
            (orchard, "A"),
            (island, "B"),
        ):
            engine.move_card(
                card.object_id,
                "battlefield",
                controller=controller,
                log=False,
            )
        engine.state.priority_player = "A"
        engine._activate(
            "A",
            {
                "source": stone.ref,
                "ability": "ab1",
                "mana_choice": "U",
            },
        )
        self.assertEqual(1, engine.state.players["A"].mana_pool["U"])

        engine.move_card(
            forest.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        engine.state.priority_player = "A"
        engine._activate(
            "A",
            {
                "source": orchard.ref,
                "ability": "ab1",
                "mana_choice": "G",
            },
        )
        self.assertEqual(1, engine.state.players["A"].mana_pool["G"])

    def test_spire_of_industry_requires_an_artifact_and_pays_life(self):
        session = self.make_session(873)
        engine = session.engine
        spire = self.card(engine, "A", "Spire of Industry")
        artifact = self.card(engine, "A", "Sol Ring")
        engine.move_card(
            spire.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        ability = next(
            ability
            for ability in engine._activated_abilities(spire)
            if ability.ability_id == "ab2"
        )
        self.assertEqual(
            "unavailable",
            engine._activation_condition_status("A", ability)[0],
        )
        engine.move_card(
            artifact.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        self.assertEqual(
            "payable",
            engine._activation_condition_status("A", ability)[0],
        )
        before_life = engine.state.players["A"].life
        engine.state.priority_player = "A"
        engine._activate(
            "A",
            {
                "source": spire.ref,
                "ability": "ab2",
                "mana_choice": "R",
            },
        )
        self.assertEqual(before_life - 1, engine.state.players["A"].life)
        self.assertEqual(1, engine.state.players["A"].mana_pool["R"])

    def test_bloom_tender_derives_one_mana_for_each_controlled_color(self):
        session = self.make_session(874)
        engine = session.engine
        tender = self.card(engine, "B", "Bloom Tender")
        zimone = self.card(engine, "B", "Zimone and Dina")
        for card in (tender, zimone):
            engine.move_card(
                card.object_id,
                "battlefield",
                controller="B",
                log=False,
            )
        tender.acquired_control_turn_count = (
            engine.state.players["B"].turns_begun - 1
        )
        engine.state.priority_player = "B"
        engine._activate(
            "B",
            {"source": tender.ref, "ability": "ab1"},
        )
        self.assertEqual(
            {"B": 1, "G": 1, "U": 1},
            {
                color: amount
                for color, amount in engine.state.players["B"].mana_pool.items()
                if amount
            },
        )
        self.assertFalse(engine.state.stack)


if __name__ == "__main__":
    unittest.main()
