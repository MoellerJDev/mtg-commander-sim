from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from mtg_commander_sim import CardDatabase, CommanderSession, GameConfig
from mtg_commander_sim.carddb import build_card_database
from mtg_commander_sim.compiler.continuous_templates import (
    basic_land_type_addition_handler,
)
from mtg_commander_sim.continuous_effects import (
    CharacteristicState,
    evaluate_continuous_effects,
)
from mtg_commander_sim.deck import DeckDefinition, DeckEntry
from mtg_commander_sim.record import checkpoint_envelope, replay_record
from mtg_commander_sim.rules.capabilities import (
    load_default_capability_registry,
)
from mtg_commander_sim.semantic_runtime import (
    AddBasicLandTypeHandler,
    ContinuousEffectSourceContext,
    SemanticNodeError,
)
from mtg_commander_sim.util import stable_json


def _card(
    oracle_id: str,
    name: str,
    *,
    mana_cost: str = "",
    cmc: float = 0,
    type_line: str,
    oracle_text: str,
    colors=(),
    color_identity=(),
    keywords=(),
    produced_mana=(),
    power=None,
    toughness=None,
    layout="normal",
    card_faces=(),
):
    value = {
        "oracle_id": oracle_id,
        "name": name,
        "mana_cost": mana_cost,
        "cmc": cmc,
        "type_line": type_line,
        "oracle_text": oracle_text,
        "colors": list(colors),
        "color_identity": list(color_identity),
        "keywords": list(keywords),
        "produced_mana": list(produced_mana),
        "power": power,
        "toughness": toughness,
        "layout": layout,
        "released_at": "2026-08-14",
        "legalities": {"commander": "legal"},
    }
    if card_faces:
        value["card_faces"] = list(card_faces)
    return value


CARDS = (
    _card(
        "db6174d7-211d-4817-b8e4-8384594c83f9",
        "Urborg, Tomb of Yawgmoth",
        type_line="Legendary Land",
        oracle_text=(
            "Each land is a Swamp in addition to its other land types."
        ),
        produced_mana=("B",),
    ),
    _card(
        "8dc067bf-f78f-4ac4-b6e7-b305c42cf0bc",
        "Darksteel Citadel",
        type_line="Artifact Land",
        oracle_text="Indestructible\n{T}: Add {C}.",
        keywords=("Indestructible",),
        produced_mana=("C",),
    ),
    _card(
        "a7dc2e62-1c50-4ed7-b71f-2d782a447a5e",
        "Cauldron Familiar",
        mana_cost="{B}",
        cmc=1,
        type_line="Creature — Cat",
        oracle_text=(
            "When this creature enters, each opponent loses 1 life and "
            "you gain 1 life.\nSacrifice a Food: Return this card from "
            "your graveyard to the battlefield."
        ),
        colors=("B",),
        color_identity=("B",),
        power="1",
        toughness="1",
    ),
    _card(
        "562d71b9-1646-474e-9293-55da6947a758",
        "Agadeem's Awakening // Agadeem, the Undercrypt",
        mana_cost="{X}{B}{B}{B} // ",
        cmc=3,
        type_line="Sorcery // Land",
        oracle_text=(
            "Agadeem's Awakening: Return from your graveyard to the "
            "battlefield any number of target creature cards that each "
            "have a different mana value X or less.\n//\nAgadeem, the "
            "Undercrypt: As this land enters, you may pay 3 life. If you "
            "don't, it enters tapped.\n{T}: Add {B}."
        ),
        color_identity=("B",),
        produced_mana=("B",),
        layout="modal_dfc",
        card_faces=(
            {
                "name": "Agadeem's Awakening",
                "mana_cost": "{X}{B}{B}{B}",
                "type_line": "Sorcery",
                "oracle_text": (
                    "Return from your graveyard to the battlefield any "
                    "number of target creature cards that each have a "
                    "different mana value X or less."
                ),
                "colors": ["B"],
            },
            {
                "name": "Agadeem, the Undercrypt",
                "mana_cost": "",
                "type_line": "Land",
                "oracle_text": (
                    "As this land enters, you may pay 3 life. If you "
                    "don't, it enters tapped.\n{T}: Add {B}."
                ),
                "colors": [],
            },
        ),
    ),
    _card(
        "e3a665f9-6e51-4e0d-923b-e9552d5978a4",
        "The Sackville-Bagginses",
        mana_cost="{1}{B}",
        cmc=2,
        type_line="Legendary Creature — Halfling Citizen",
        oracle_text=(
            "When The Sackville-Bagginses enter, you may sacrifice "
            "another creature or artifact. If you do, draw a card and "
            "create a Treasure token.\nWhenever you sacrifice a token, "
            "target opponent loses 1 life."
        ),
        colors=("B",),
        color_identity=("B",),
        keywords=("Treasure",),
        power="2",
        toughness="2",
    ),
    _card(
        "56719f6a-1a6c-4c0a-8d21-18f7d7350b68",
        "Swamp",
        type_line="Basic Land — Swamp",
        oracle_text="({T}: Add {B}.)",
        color_identity=("B",),
        produced_mana=("B",),
    ),
)


class BasicLandTypeManaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        root = Path(cls.temporary.name)
        oracle = root / "cards.jsonl"
        rulings = root / "rulings.jsonl"
        oracle.write_text(
            "\n".join(stable_json(card) for card in CARDS) + "\n",
            encoding="utf-8",
        )
        rulings.write_text("", encoding="utf-8")
        cls.database_path = root / "cards.sqlite3"
        build_card_database(oracle, rulings, cls.database_path)
        cls.db = CardDatabase(cls.database_path)
        cls.deck = DeckDefinition(
            name="Sackville Urborg regression",
            commanders=["The Sackville-Bagginses"],
            entries=[
                DeckEntry(
                    "The Sackville-Bagginses",
                    board="commander",
                ),
                DeckEntry("Urborg, Tomb of Yawgmoth"),
                DeckEntry("Darksteel Citadel"),
                DeckEntry("Cauldron Familiar"),
                DeckEntry(
                    "Agadeem's Awakening // Agadeem, the Undercrypt"
                ),
                DeckEntry("Swamp", quantity=95),
            ],
        )

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls.temporary.cleanup()

    def session(self, seed: int) -> CommanderSession:
        session = CommanderSession.create(
            self.db,
            {"A": self.deck, "B": self.deck},
            first_player="A",
            seed=seed,
            config=GameConfig(
                seed=seed,
                semantic_policy="trusted_only",
                auto_pass_empty_priority=False,
                manual_active_main_phase=True,
            ),
        )
        while (
            session.state.pending_decision
            and session.state.pending_decision.kind == "mulligan.declare"
        ):
            for principal in list(session.pending_principals()):
                result = session.act(principal, {"a": "keep"})
                self.assertTrue(result.ok, result.summary)
        return session

    @staticmethod
    def named(engine, seat: str, name: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == seat and card.printed_name == name
        )

    def prepare_main(self, session: CommanderSession):
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.active_player = "A"
        engine.state.priority_player = None
        engine.state.priority_passes = []
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.players["A"].land_plays_remaining = 1
        engine._grant_priority("A")
        engine._issue_priority("A")
        return engine

    def test_urborg_adds_swamp_and_intrinsic_black_mana_to_darksteel_citadel(self):
        session = self.session(3056001)
        engine = session.engine
        urborg = self.named(engine, "A", "Urborg, Tomb of Yawgmoth")
        citadel = self.named(engine, "A", "Darksteel Citadel")
        familiar = self.named(engine, "A", "Cauldron Familiar")
        engine.move_card(urborg.object_id, "battlefield", controller="A")
        citadel = engine.move_card(
            citadel.object_id, "battlefield", controller="A"
        )
        engine.move_card(familiar.object_id, "hand")
        self.prepare_main(session)

        effective = engine._effective_card_data(citadel)
        self.assertIn("Swamp", effective["type_line"])
        self.assertIn("Artifact", effective["type_line"])
        self.assertIn("Indestructible", effective["oracle_text"])
        source = next(
            source
            for source in engine.available_mana_sources("A")
            if source.object_id == citadel.object_id
        )
        bundles = {
            tuple(sorted((key, amount) for key, amount in mode.bundle.items() if amount))
            for mode in source.modes
        }
        self.assertIn((("B", 1),), bundles)
        self.assertIn((("C", 1),), bundles)
        abilities = engine._activated_abilities(citadel)
        self.assertTrue(
            any(
                ability.ability_id == "intrinsic_swamp"
                and ability.mana_ability
                for ability in abilities
            )
        )
        hints = engine._priority_action_hints("A")
        self.assertIn(familiar.ref, hints["cast"])

    def test_additive_basic_land_type_preserves_existing_types_text_and_mana(self):
        descriptor = basic_land_type_addition_handler(
            "Each land is a Swamp in addition to its other land types."
        )[1]
        effect = AddBasicLandTypeHandler().lower(
            descriptor,
            ContinuousEffectSourceContext(
                source_object_id="source",
                source_ref="U1",
                source_controller="A",
                source_timestamp=1,
                component_id="component",
            ),
        )
        result = evaluate_continuous_effects(
            CharacteristicState(
                name="Darksteel Citadel",
                controller="B",
                text="Indestructible\n{T}: Add {C}.",
                card_types={"Artifact", "Land"},
                abilities=["Indestructible", "{T}: Add {C}."],
            ),
            effect,
        ).characteristics
        self.assertEqual(["Artifact", "Land"], result["card_types"])
        self.assertEqual("Indestructible\n{T}: Add {C}.", result["text"])
        self.assertEqual(["swamp"], result["subtypes"])

    def test_basic_land_type_component_applies_to_every_players_lands(self):
        session = self.session(3056002)
        engine = session.engine
        urborg = self.named(engine, "A", "Urborg, Tomb of Yawgmoth")
        own_land = self.named(engine, "A", "Darksteel Citadel")
        opposing_land = self.named(engine, "B", "Darksteel Citadel")
        engine.move_card(urborg.object_id, "battlefield", controller="A")
        own_land = engine.move_card(
            own_land.object_id, "battlefield", controller="A"
        )
        opposing_land = engine.move_card(
            opposing_land.object_id, "battlefield", controller="B"
        )
        self.assertIn("Swamp", engine._effective_card_data(own_land)["type_line"])
        self.assertIn(
            "Swamp", engine._effective_card_data(opposing_land)["type_line"]
        )

    def test_basic_land_type_component_rejects_malformed_descriptors(self):
        descriptor = dict(
            basic_land_type_addition_handler(
                "Each land is a Swamp in addition to its other land types."
            )[1]
        )
        descriptor["modifier"] = {"basic_land_type": "locus"}
        with self.assertRaisesRegex(SemanticNodeError, "basic land type"):
            AddBasicLandTypeHandler().validate(descriptor)
        self.assertIsNone(
            basic_land_type_addition_handler(
                "Each artifact is a Swamp in addition to its other types."
            )
        )

    def test_agadeem_land_mana_and_sackville_commander_are_castable(self):
        session = self.session(3056003)
        engine = session.engine
        citadel = self.named(engine, "A", "Darksteel Citadel")
        agadeem = self.named(
            engine,
            "A",
            "Agadeem's Awakening // Agadeem, the Undercrypt",
        )
        commander = self.named(engine, "A", "The Sackville-Bagginses")
        citadel = engine.move_card(
            citadel.object_id, "battlefield", controller="A"
        )
        agadeem = engine.move_card(
            agadeem.object_id,
            "battlefield",
            controller="A",
            enter_face="Agadeem, the Undercrypt",
        )
        self.prepare_main(session)

        agadeem_source = next(
            source
            for source in engine.available_mana_sources("A")
            if source.object_id == agadeem.object_id
        )
        self.assertTrue(
            any(mode.bundle["B"] == 1 for mode in agadeem_source.modes)
        )
        hints = engine._priority_action_hints("A")
        self.assertIn(commander.ref, hints["cast"])
        result = session.act(
            "pilot:A",
            {
                "action": "cast",
                "card": commander.ref,
                "from": "command",
                "auto_pay": True,
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual("stack", commander.zone)
        self.assertTrue(citadel.tapped)
        self.assertTrue(agadeem.tapped)

    def test_urborg_intrinsic_black_mana_replays_exactly(self):
        session = self.session(3056004)
        engine = session.engine
        urborg = self.named(engine, "A", "Urborg, Tomb of Yawgmoth")
        citadel = self.named(engine, "A", "Darksteel Citadel")
        familiar = self.named(engine, "A", "Cauldron Familiar")
        engine.move_card(urborg.object_id, "battlefield", controller="A")
        urborg.tapped = True
        citadel = engine.move_card(
            citadel.object_id, "battlefield", controller="A"
        )
        familiar = engine.move_card(familiar.object_id, "hand")
        self.prepare_main(session)
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()

        result = session.act(
            "pilot:A",
            {
                "action": "cast",
                "card": familiar.ref,
                "from": "hand",
                "auto_pay": True,
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertTrue(citadel.tapped)
        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "urborg-replay"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)

    def test_urborg_granted_black_mana_can_be_manually_undone(self):
        session = self.session(3056006)
        engine = session.engine
        urborg = self.named(engine, "A", "Urborg, Tomb of Yawgmoth")
        citadel = self.named(engine, "A", "Darksteel Citadel")
        engine.move_card(urborg.object_id, "battlefield", controller="A")
        urborg.tapped = True
        citadel = engine.move_card(
            citadel.object_id, "battlefield", controller="A"
        )
        self.prepare_main(session)

        legal = engine.state.pending_decision.payload_by_actor["A"]["legal"]
        activate = next(
            action
            for action in legal["actions"]
            if action.get("source") == citadel.ref
            and action.get("ability") == "intrinsic_swamp"
        )
        result = session.act("pilot:A", {"action_id": activate["id"]})
        self.assertTrue(result.ok, result.summary)
        self.assertTrue(citadel.tapped)
        self.assertEqual(1, engine.state.players["A"].mana_pool["B"])

        legal = engine.state.pending_decision.payload_by_actor["A"]["legal"]
        undo = next(
            action
            for action in legal["actions"]
            if action.get("action") == "undo_mana"
        )
        result = session.act("pilot:A", {"action_id": undo["id"]})
        self.assertTrue(result.ok, result.summary)
        self.assertFalse(citadel.tapped)
        self.assertEqual(0, engine.state.players["A"].mana_pool["B"])

    def test_manual_mana_activation_and_undo_replay_exactly(self):
        session = self.session(3056005)
        engine = session.engine
        swamp = self.named(engine, "A", "Swamp")
        swamp = engine.move_card(
            swamp.object_id, "battlefield", controller="A"
        )
        self.prepare_main(session)
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()

        legal = engine.state.pending_decision.payload_by_actor["A"]["legal"]
        activate = next(
            action
            for action in legal["actions"]
            if action.get("source") == swamp.ref
            and action.get("mana_ability") is True
        )
        result = session.act(
            "pilot:A", {"action_id": activate["id"]}
        )
        self.assertTrue(result.ok, result.summary)
        self.assertTrue(swamp.tapped)
        self.assertEqual(1, engine.state.players["A"].mana_pool["B"])

        legal = engine.state.pending_decision.payload_by_actor["A"]["legal"]
        undo = next(
            action
            for action in legal["actions"]
            if action.get("action") == "undo_mana"
        )
        result = session.act("pilot:A", {"action_id": undo["id"]})
        self.assertTrue(result.ok, result.summary)
        self.assertFalse(swamp.tapped)
        self.assertEqual(0, engine.state.players["A"].mana_pool["B"])

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "mana-undo-replay"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(2, replay["commands"])


if __name__ == "__main__":
    unittest.main()
