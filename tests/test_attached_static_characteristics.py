from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from common import keep_all, load_assets, make_session
from mtg_commander_sim.abilities import parse_activated_abilities
from mtg_commander_sim.attachments import (
    AttachmentRelationError,
    attach_objects,
    attached_object_identity,
    detach_object,
)
from mtg_commander_sim.compiler.continuous_templates import (
    attached_fixed_characteristics_handler,
)
from mtg_commander_sim.continuous_effect_model import (
    ContinuousEffect,
    ContinuousEffectError,
    ContinuousEffectRelation,
    ContinuousObjectIdentity,
)
from mtg_commander_sim.continuous_effects import (
    CharacteristicState,
    evaluate_continuous_effects,
)
from mtg_commander_sim.errors import GameRuleError
from mtg_commander_sim.model import CardInstance
from mtg_commander_sim.model import StackItem
from mtg_commander_sim.oracle_ir import compile_oracle_card
from mtg_commander_sim.record import checkpoint_envelope, replay_record
from mtg_commander_sim.rules.capabilities import (
    load_default_capability_registry,
)
from mtg_commander_sim.semantic_runtime import (
    AttachedFixedCharacteristicsHandler,
    ContinuousEffectSourceContext,
    SemanticNodeError,
)
from mtg_commander_sim.semantics import SemanticProgram


def descriptor(line: str) -> dict:
    compiled = attached_fixed_characteristics_handler(line)
    if compiled is None:
        raise AssertionError(f"fixture did not compile: {line}")
    return copy.deepcopy(dict(compiled[1]))


def card(
    object_id: str,
    *,
    zone: str = "battlefield",
    controller: str = "A",
    zone_change_counter: int = 0,
    zone_timestamp: int = 1,
) -> CardInstance:
    return CardInstance(
        object_id=object_id,
        ref=object_id,
        oracle_id=f"oracle:{object_id}",
        printed_name=object_id,
        owner=controller,
        controller=controller,
        zone=zone,
        zone_change_counter=zone_change_counter,
        zone_timestamp=zone_timestamp,
    )


class AttachmentRelationTests(unittest.TestCase):
    def test_attach_reattach_and_detach_own_reciprocal_timestamped_relation(self):
        source = card("equipment", zone_timestamp=3)
        first = card("first")
        second = card("second")
        cards = {value.object_id: value for value in (source, first, second)}

        first_transition = attach_objects(
            cards, source, first, source_timestamp=7
        )
        self.assertTrue(first_transition.changed)
        self.assertEqual(7, source.zone_timestamp)
        self.assertEqual(first.object_id, source.attached_to)
        self.assertEqual([source.object_id], first.attachments)
        self.assertEqual(
            ContinuousObjectIdentity(
                object_id=first.object_id,
                logical_object_id=first.logical_object_id,
            ),
            attached_object_identity(cards, source),
        )

        second_transition = attach_objects(
            cards, source, second, source_timestamp=11
        )
        self.assertEqual(first.object_id, second_transition.previous_target_id)
        self.assertEqual(11, source.zone_timestamp)
        self.assertEqual([], first.attachments)
        self.assertEqual([source.object_id], second.attachments)

        detached = detach_object(cards, source)
        self.assertTrue(detached.changed)
        self.assertIsNone(source.attached_to)
        self.assertEqual([], second.attachments)
        self.assertEqual(11, source.zone_timestamp)

    def test_reattaching_to_same_object_preserves_timestamp(self):
        source = card("aura", zone_timestamp=3)
        target = card("target")
        cards = {source.object_id: source, target.object_id: target}
        attach_objects(cards, source, target, source_timestamp=7)
        transition = attach_objects(
            cards, source, target, source_timestamp=99
        )
        self.assertFalse(transition.changed)
        self.assertEqual(7, source.zone_timestamp)

    def test_malformed_relation_fails_before_mutation(self):
        source = card("equipment")
        previous = card("previous")
        target = card("target")
        cards = {value.object_id: value for value in (source, previous, target)}
        source.attached_to = previous.object_id
        before = {
            key: value.to_dict() for key, value in cards.items()
        }
        with self.assertRaisesRegex(
            AttachmentRelationError, "not reciprocal"
        ):
            attach_objects(cards, source, target, source_timestamp=9)
        self.assertEqual(
            before, {key: value.to_dict() for key, value in cards.items()}
        )

    def test_identity_requires_live_reciprocal_phased_in_battlefield_objects(self):
        source = card("aura")
        target = card("target")
        cards = {source.object_id: source, target.object_id: target}
        source.attached_to = target.object_id
        self.assertIsNone(attached_object_identity(cards, source))
        target.attachments.append(source.object_id)
        self.assertIsNotNone(attached_object_identity(cards, source))
        target.phased_out = True
        self.assertIsNone(attached_object_identity(cards, source))


class AttachedContinuousModelTests(unittest.TestCase):
    @staticmethod
    def context(
        *, logical_object_id: str = "target@0"
    ) -> ContinuousEffectSourceContext:
        return ContinuousEffectSourceContext(
            source_object_id="source",
            source_ref="S1",
            source_controller="A",
            source_timestamp=5,
            component_id="test:attached:0",
            attached_object=ContinuousObjectIdentity(
                object_id="target",
                logical_object_id=logical_object_id,
            ),
        )

    @staticmethod
    def base() -> CharacteristicState:
        return CharacteristicState(
            name="Target",
            controller="B",
            card_types={"Creature"},
            subtypes={"Human"},
            abilities=[],
            power=1,
            toughness=1,
        )

    def test_fixed_modifier_and_keyword_apply_only_to_exact_logical_object(self):
        effects = AttachedFixedCharacteristicsHandler().lower(
            descriptor(
                "Equipped creature gets +2/+1 and has flying and vigilance."
            ),
            self.context(),
        )
        applied = evaluate_continuous_effects(
            self.base(),
            effects,
            context={
                "object_id": "target",
                "logical_object_id": "target@0",
                "zone": "battlefield",
                "owner": "B",
            },
        )
        self.assertEqual(3, applied.characteristics["power"])
        self.assertEqual(2, applied.characteristics["toughness"])
        self.assertEqual(
            {"Flying", "Vigilance"},
            set(applied.characteristics["abilities"]),
        )

        returned = evaluate_continuous_effects(
            self.base(),
            effects,
            context={
                "object_id": "target",
                "logical_object_id": "target@1",
                "zone": "battlefield",
                "owner": "B",
            },
        )
        self.assertEqual(1, returned.characteristics["power"])
        self.assertFalse(returned.applied_effects)

    def test_type_and_ability_removal_use_their_canonical_layers(self):
        type_effect = AttachedFixedCharacteristicsHandler().lower(
            descriptor(
                "Enchanted creature is a Zombie in addition to its other types."
            ),
            self.context(),
        )
        removal = AttachedFixedCharacteristicsHandler().lower(
            descriptor("Enchanted creature loses flying."),
            ContinuousEffectSourceContext(
                source_object_id="second-source",
                source_ref="S2",
                source_controller="C",
                source_timestamp=8,
                component_id="test:attached:1",
                attached_object=self.context().attached_object,
            ),
        )
        base = self.base()
        base.abilities.append("Flying")
        result = evaluate_continuous_effects(
            base,
            (*type_effect, *removal),
            context={
                "object_id": "target",
                "logical_object_id": "target@0",
                "zone": "battlefield",
                "owner": "B",
            },
        )
        self.assertEqual({"human", "zombie"}, {
            value.casefold() for value in result.characteristics["subtypes"]
        })
        self.assertNotIn("Flying", result.characteristics["abilities"])

    def test_relation_round_trip_is_canonical_and_legacy_shape_stays_stable(self):
        effect = AttachedFixedCharacteristicsHandler().lower(
            descriptor("Enchanted creature gets -1/-0."),
            self.context(),
        )[0]
        payload = effect.to_dict()
        self.assertEqual(
            "source_attached_to_object", payload["relation"]
        )
        restored = ContinuousEffect.from_dict(payload)
        self.assertEqual(effect.fingerprint, restored.fingerprint)

        legacy = dict(payload)
        legacy.pop("relation")
        legacy.pop("related_object")
        legacy["origin"] = "object"
        legacy_effect = ContinuousEffect.from_dict(legacy)
        self.assertEqual(legacy, legacy_effect.to_dict())

    def test_relation_model_and_descriptor_fail_closed(self):
        effect = AttachedFixedCharacteristicsHandler().lower(
            descriptor("Equipped creature has shroud."),
            self.context(),
        )[0]
        malformed = effect.to_dict()
        malformed["related_object"] = None
        with self.assertRaises(ContinuousEffectError):
            ContinuousEffect.from_dict(malformed)

        bad_descriptor = descriptor("Equipped creature has shroud.")
        bad_descriptor["modifier"]["power"] = True
        with self.assertRaisesRegex(SemanticNodeError, "integers"):
            AttachedFixedCharacteristicsHandler().validate(bad_descriptor)

        unrelated = copy.deepcopy(effect.to_dict())
        unrelated["relation"] = ContinuousEffectRelation.NONE.value
        with self.assertRaisesRegex(
            ContinuousEffectError, "cannot name a related object"
        ):
            ContinuousEffect.from_dict(unrelated)

    def test_unattached_source_lowers_no_effect(self):
        effects = AttachedFixedCharacteristicsHandler().lower(
            descriptor("Equipped creature has haste."),
            ContinuousEffectSourceContext(
                source_object_id="source",
                source_ref="S1",
                source_controller="A",
                source_timestamp=5,
                component_id="test:unattached",
            ),
        )
        self.assertEqual((), effects)


class AttachedContinuousCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, _, _ = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_compiler_lowers_fixed_attached_characteristic_families(self):
        fixtures = {
            "Enchanted creature gets +1/+1.": (1, 1, [], []),
            "Equipped creature has haste and shroud.": (
                0,
                0,
                ["Haste", "Shroud"],
                [],
            ),
            "Fortified land loses indestructible.": (
                0,
                0,
                [],
                ["Indestructible"],
            ),
        }
        for line, expected in fixtures.items():
            with self.subTest(line=line):
                value = descriptor(line)["modifier"]
                self.assertEqual(expected[0], value["power"])
                self.assertEqual(expected[1], value["toughness"])
                self.assertEqual(expected[2], value["add_abilities"])
                self.assertEqual(expected[3], value["remove_abilities"])

    def test_compiler_rejects_dynamic_conditional_and_unrepresented_text(self):
        for line in (
            "Equipped creature gets +X/+X.",
            "Equipped creature gets +1/+1 for each artifact you control.",
            "Enchanted creature has protection from red.",
            "Enchanted creature can't attack.",
            'Equipped creature has "{T}: Draw a card."',
            "As long as enchanted creature is red, it gets +1/+1.",
        ):
            with self.subTest(line=line):
                self.assertIsNone(
                    attached_fixed_characteristics_handler(line)
                )

    def test_fixed_equip_keyword_has_exact_bounded_capability(self):
        greaves = self.db.lookup("Lightning Greaves")
        ir = compile_oracle_card(
            greaves,
            capability_registry=load_default_capability_registry(),
            capability_profile="commander_review",
        )
        equip = next(
            node
            for node in ir.faces[0].nodes
            if node.text.casefold().startswith("equip ")
        )
        self.assertTrue(equip.exact)
        self.assertEqual(
            ("attachment.equip.fixed_mana",),
            equip.capability_dependencies,
        )

        variable = replace(
            greaves, oracle_text="Equip {X}", keywords=("Equip",)
        )
        unresolved = compile_oracle_card(
            variable,
            capability_registry=load_default_capability_registry(),
            capability_profile="commander_review",
        )
        self.assertEqual("partial", unresolved.status)
        self.assertIn(
            "mechanic:equip",
            next(
                residual
                for residual in unresolved.material_residuals
                if residual.text == "Equip {X}"
            ).blockers,
        )

    def test_fixed_equip_parser_exposes_only_executable_target_contract(self):
        ability = parse_activated_abilities(
            card_name="Review Equipment",
            oracle_text="Equip {2}",
            keywords=("Equip",),
        )[0]
        self.assertTrue(ability.compiled_cost)
        self.assertTrue(ability.sorcery_speed)
        self.assertEqual("builtin:equip", ability.builtin_semantic_key)
        self.assertEqual(
            {
                "zones": ("battlefield",),
                "categories": ("permanent",),
                "controller": "you",
                "creature": True,
                "count": 1,
            },
            dict(ability.target_schema),
        )

        variable = parse_activated_abilities(
            card_name="Unresolved Equipment",
            oracle_text="Equip {X}",
            keywords=("Equip",),
        )[0]
        self.assertFalse(variable.compiled_cost)


class AttachedStaticEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def session(self, seed: int, *, players: int = 2):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=players,
            seed=seed,
            auto_pass_empty=False,
        )
        keep_all(session)
        return session

    @staticmethod
    def find(engine, seat: str, name: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == seat and card.printed_name == name
        )

    def put_on_battlefield(self, engine, *cards):
        for value in cards:
            engine.move_card(
                value.object_id,
                "battlefield",
                controller=value.controller,
                log=False,
            )

    @staticmethod
    def resolve_top(engine):
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine._prepare_stack_resolution()

    def test_generic_fixed_equip_activation_attaches_and_applies_characteristics(self):
        session = self.session(6131000)
        engine = session.engine
        greaves = self.find(engine, "A", "Lightning Greaves")
        mishra = self.find(engine, "A", "Mishra, Eminent One")
        opponent = self.find(engine, "B", "Zimone and Dina")
        self.put_on_battlefield(engine, greaves, mishra, opponent)
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.priority_player = "A"

        with self.assertRaisesRegex(GameRuleError, "target"):
            engine._activate(
                "A",
                {
                    "source": greaves.ref,
                    "ability": "ab2",
                    "targets": [opponent.ref],
                },
            )
        self.assertIsNone(greaves.attached_to)

        engine._activate(
            "A",
            {
                "source": greaves.ref,
                "ability": "ab2",
                "targets": [mishra.ref],
            },
        )
        self.assertEqual("builtin:equip", engine.state.stack[-1].semantic_key)
        self.resolve_top(engine)
        self.assertEqual(mishra.object_id, greaves.attached_to)
        self.assertEqual(
            {"Haste", "Shroud"},
            {"Haste", "Shroud"}.intersection(
                engine._effective_card_data(mishra)["keywords"]
            ),
        )

    def test_live_generic_equipment_effect_moves_detaches_and_tracks_control(self):
        session = self.session(6131001)
        engine = session.engine
        greaves = self.find(engine, "A", "Lightning Greaves")
        mishra = self.find(engine, "A", "Mishra, Eminent One")
        engineer = self.find(engine, "A", "Goblin Engineer")
        self.put_on_battlefield(engine, greaves, mishra, engineer)

        attach_objects(
            engine.state.cards,
            greaves,
            mishra,
            source_timestamp=engine._next_zone_timestamp(),
        )
        self.assertEqual(
            {"Haste", "Shroud"},
            {"Haste", "Shroud"}.intersection(
                engine._effective_card_data(mishra)["keywords"]
            ),
        )
        engine.change_control(
            mishra.object_id, "B", reason="attached target control witness"
        )
        self.assertIn(
            "Shroud", engine._effective_card_data(mishra)["keywords"]
        )
        engine.change_control(
            greaves.object_id, "B", reason="attachment control witness"
        )
        self.assertIn(
            "Shroud", engine._effective_card_data(mishra)["keywords"]
        )

        first_timestamp = greaves.zone_timestamp
        attach_objects(
            engine.state.cards,
            greaves,
            engineer,
            source_timestamp=engine._next_zone_timestamp(),
        )
        self.assertGreater(greaves.zone_timestamp, first_timestamp)
        self.assertNotIn(
            "Shroud", engine._effective_card_data(mishra)["keywords"]
        )
        self.assertIn(
            "Shroud", engine._effective_card_data(engineer)["keywords"]
        )
        detach_object(engine.state.cards, greaves)
        self.assertNotIn(
            "Shroud", engine._effective_card_data(engineer)["keywords"]
        )

    def test_animate_dead_and_bestow_modifiers_use_generic_attached_handler(self):
        session = self.session(6131002)
        engine = session.engine
        aura = self.find(engine, "B", "Animate Dead")
        nantuko = self.find(engine, "B", "Springheart Nantuko")
        target = self.find(engine, "B", "Birds of Paradise")
        self.put_on_battlefield(engine, nantuko, target)
        # Animate Dead's graveyard-card restriction is intentionally outside
        # the bounded simple-object Aura grammar.  Preserve this legacy
        # semantic-component fixture by supplying its already-selected target.
        aura.annotations["pending_aura_target"] = target.ref
        self.put_on_battlefield(engine, aura)
        nantuko.annotations["bestowed"] = True

        attach_objects(
            engine.state.cards,
            aura,
            target,
            source_timestamp=engine._next_zone_timestamp(),
        )
        attach_objects(
            engine.state.cards,
            nantuko,
            target,
            source_timestamp=engine._next_zone_timestamp(),
        )
        self.assertEqual(0, engine._numeric_stat(target.object_id, "power"))
        self.assertEqual(2, engine._numeric_stat(target.object_id, "toughness"))

        aura.phased_out = True
        self.assertEqual(1, engine._numeric_stat(target.object_id, "power"))
        target.phased_out = True
        self.assertIsNone(
            attached_object_identity(engine.state.cards, nantuko)
        )

    def test_target_departure_and_source_departure_end_effect_without_stale_identity(self):
        session = self.session(6131003)
        engine = session.engine
        greaves = self.find(engine, "A", "Lightning Greaves")
        target = self.find(engine, "A", "Goblin Engineer")
        self.put_on_battlefield(engine, greaves, target)
        attach_objects(
            engine.state.cards,
            greaves,
            target,
            source_timestamp=engine._next_zone_timestamp(),
        )
        self.assertIn(
            "Haste", engine._effective_card_data(target)["keywords"]
        )
        engine.move_card(target.object_id, "graveyard", log=False)
        engine.move_card(
            target.object_id, "battlefield", controller="A", log=False
        )
        self.assertIsNone(greaves.attached_to)
        self.assertNotIn(
            "Haste", engine._effective_card_data(target)["keywords"]
        )
        attach_objects(
            engine.state.cards,
            greaves,
            target,
            source_timestamp=engine._next_zone_timestamp(),
        )
        engine.move_card(greaves.object_id, "graveyard", log=False)
        self.assertNotIn(
            "Haste", engine._effective_card_data(target)["keywords"]
        )

    def test_multiple_sources_apply_independently_in_four_player_game(self):
        session = self.session(6131004, players=4)
        engine = session.engine
        greaves = self.find(engine, "A", "Lightning Greaves")
        skullclamp = self.find(engine, "D", "Skullclamp")
        target = self.find(engine, "B", "Zimone and Dina")
        self.put_on_battlefield(engine, greaves, skullclamp, target)
        for source in (greaves, skullclamp):
            attach_objects(
                engine.state.cards,
                source,
                target,
                source_timestamp=engine._next_zone_timestamp(),
            )
        data = engine._effective_card_data(target)
        self.assertEqual("4", data["power"])
        self.assertEqual("3", data["toughness"])
        self.assertIn("Shroud", data["keywords"])

    def test_projection_hides_relation_identity_and_replay_is_exact(self):
        session = self.session(6131005)
        engine = session.engine
        greaves = self.find(engine, "A", "Lightning Greaves")
        target = self.find(engine, "A", "Mishra, Eminent One")
        self.put_on_battlefield(engine, greaves, target)
        program = SemanticProgram(
            key="test:attached-replay",
            label="Attach replay witness",
            effects=[
                {
                    "op": "attach",
                    "equipment": greaves.ref,
                    "creature": target.ref,
                }
            ],
            trust_level="provisional",
        )
        engine.semantics.put(program)
        engine.state.stack.append(
            StackItem(
                stack_id="attached-replay",
                ref="S-attached-replay",
                kind="activated_ability",
                controller="A",
                label=program.label,
                semantic_key=program.key,
                source_object_id=greaves.object_id,
                visibility=["A", "B"],
            )
        )
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.state.priority_passes = []
        engine._grant_priority("A")
        engine._issue_priority("A")
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()
        for principal in ("pilot:A", "pilot:B"):
            result = session.act(principal, {"action_id": "pass"})
            self.assertTrue(result.ok, result.summary)
        self.assertEqual(target.object_id, greaves.attached_to)
        projected = session.projector._snapshot("pilot:B")
        rendered = json.dumps(projected, sort_keys=True)
        self.assertNotIn("continuous_effects", rendered)
        self.assertNotIn(target.object_id, rendered)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "attached-static-replay"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(2, replay["commands"])


if __name__ == "__main__":
    unittest.main()
