from __future__ import annotations

import unittest

from common import keep_all, load_assets, make_session
from mtg_commander_sim.attachments import attach_objects
from mtg_commander_sim.abilities import ActivatedAbility
from mtg_commander_sim.ability_fragments import (
    AbilityFragmentError,
    GrantedActivatedAbilitySpec,
    GrantedTriggeredAbilitySpec,
    ProtectionQualityKind,
    ProtectionSpec,
    ability_fragment_from_dict,
    ability_fragment_to_dict,
    canonical_ability_fragments,
    parse_protection_line,
)
from mtg_commander_sim.aura import (
    LinkedGraveyardCreatureEnchantSpec,
    SimpleEnchantSpec,
    enchant_spec_from_dict,
    enchant_spec_to_dict,
)
from mtg_commander_sim.carddb import CardRecord
from mtg_commander_sim.compiler.continuous_templates import (
    attached_fixed_characteristics_handler,
)
from mtg_commander_sim.continuous_effect_model import (
    ContinuousEffect,
    ContinuousEffectOrigin,
    ContinuousOperation,
    Layer,
)
from mtg_commander_sim.continuous_effects import (
    CharacteristicState,
    evaluate_continuous_effects,
)
from mtg_commander_sim.model import CardInstance
from mtg_commander_sim.oracle_ir import compile_oracle_card
from mtg_commander_sim.protection import (
    ProtectionSource,
    ProtectionVerdict,
    protection_verdict,
)
from mtg_commander_sim.rules.activation.query import activated_abilities
from mtg_commander_sim.rules.capabilities import (
    load_default_capability_registry,
)
from mtg_commander_sim.semantic_runtime.ability_fragments import (
    default_ability_fragment_registry,
    fragments_from_descriptors,
)
from mtg_commander_sim.targets import TargetGroup


def wrapped(fragment):
    return ability_fragment_to_dict(fragment)


def card_record(
    oracle_id: str,
    *,
    type_line: str,
    oracle_text: str,
    keywords: tuple[str, ...],
) -> CardRecord:
    return CardRecord(
        oracle_id=oracle_id,
        name="Typed Static Keywords",
        mana_cost="{1}{W}",
        mana_value=2,
        type_line=type_line,
        oracle_text=oracle_text,
        power="2" if "Creature" in type_line else None,
        toughness="2" if "Creature" in type_line else None,
        loyalty=None,
        defense=None,
        colors=("W",),
        color_identity=("W",),
        keywords=keywords,
        produced_mana=(),
        layout="normal",
        released_at="2026-01-01",
        legalities={"commander": "legal"},
        faces=(),
        raw={},
    )


class AbilityFragmentModelTests(unittest.TestCase):
    def test_linked_graveyard_enchant_descriptor_is_closed_and_round_trips(
        self,
    ):
        spec = LinkedGraveyardCreatureEnchantSpec("linked_creature")
        serialized = enchant_spec_to_dict(spec)
        self.assertEqual(spec, enchant_spec_from_dict(serialized))
        self.assertEqual(
            ["graveyard"],
            spec.target_schema()["zones"],
        )
        source = CardInstance(
            object_id="aura",
            ref="A01",
            oracle_id="fixture:linked-aura",
            owner="A",
            controller="A",
            printed_name="Linked Aura",
            zone="battlefield",
            annotations={"linked_creature": "creature"},
        )
        self.assertEqual(
            ["battlefield"],
            spec.target_schema(source)["zones"],
        )
        self.assertEqual("creature", spec.linked_target_object_id(source))
        with self.assertRaisesRegex(ValueError, "exactly kind and value"):
            enchant_spec_from_dict({**serialized, "unknown": True})

    def test_round_trip_is_strict_immutable_and_preserves_multiplicity(self):
        mana = {"GENERIC": 2}
        activated = GrantedActivatedAbilitySpec(
            ability_id="granted:damage",
            semantic_key="fixture:granted:damage",
            cost_text="{2}, {T}",
            effect_text="This creature deals 1 damage to any target",
            mana=mana,
            tap_source=True,
        )
        mana["GENERIC"] = 9
        self.assertEqual({"GENERIC": 2}, activated.mana_bundle)
        values = (
            ProtectionSpec(ProtectionQualityKind.COLOR, "R"),
            activated,
            GrantedTriggeredAbilitySpec(
                ability_id="granted:untap",
                semantic_key="fixture:granted:untap",
                event="creature.dies",
                label="Whenever a creature dies, untap this creature.",
            ),
            SimpleEnchantSpec("creature"),
            LinkedGraveyardCreatureEnchantSpec("linked_creature"),
        )
        for value in values:
            with self.subTest(value=type(value).__name__):
                serialized = wrapped(value)
                self.assertEqual(
                    value,
                    ability_fragment_from_dict(serialized),
                )
                with self.assertRaises(AbilityFragmentError):
                    ability_fragment_from_dict(
                        {**serialized, "unknown": True}
                    )
        duplicated = canonical_ability_fragments(
            (values[2], values[0], values[2])
        )
        reordered = canonical_ability_fragments(
            (values[2], values[2], values[0])
        )
        self.assertEqual(duplicated, reordered)
        self.assertEqual(2, duplicated.count(values[2]))

    def test_static_handler_descriptors_are_closed_and_typed(self):
        descriptors = [
            {
                "handler_id": "ability.static.enchant.v1",
                "schema_version": 1,
                "event": "continuous",
                "fragment": wrapped(SimpleEnchantSpec("creature")),
            },
            {
                "handler_id": "ability.static.protection.v1",
                "schema_version": 1,
                "event": "continuous",
                "fragment": wrapped(
                    ProtectionSpec(ProtectionQualityKind.COLOR, "U")
                ),
            },
            {
                "handler_id": (
                    "ability.enchant.linked_graveyard_creature.v1"
                ),
                "schema_version": 1,
                "event": "resolve",
                "fragment": wrapped(
                    LinkedGraveyardCreatureEnchantSpec("linked_creature")
                ),
            },
        ]
        self.assertEqual(
            canonical_ability_fragments(
                (
                    SimpleEnchantSpec("creature"),
                    ProtectionSpec(ProtectionQualityKind.COLOR, "U"),
                    LinkedGraveyardCreatureEnchantSpec("linked_creature"),
                )
            ),
            canonical_ability_fragments(
                fragments_from_descriptors(descriptors)
            ),
        )
        self.assertEqual(
            3,
            len(default_ability_fragment_registry().inventory()),
        )
        with self.assertRaisesRegex(ValueError, "unknown"):
            fragments_from_descriptors(
                [{**descriptors[0], "unknown": True}]
            )

    def test_compiler_emits_exact_typed_enchant_and_protection_handlers(self):
        registry = load_default_capability_registry()
        record = card_record(
            "fixture:typed-static-keywords",
            type_line="Enchantment — Aura",
            oracle_text="Enchant creature\nProtection from red",
            keywords=("Enchant", "Protection"),
        )
        compiled = compile_oracle_card(
            record,
            capability_registry=registry,
            capability_profile="commander_review",
        )
        handlers = [
            handler
            for node in compiled.faces[0].nodes
            for handler in node.handlers
        ]
        self.assertEqual(
            {
                "ability.static.enchant.v1",
                "ability.static.protection.v1",
            },
            {handler["handler_id"] for handler in handlers},
        )
        self.assertFalse(compiled.faces[0].residuals)
        self.assertTrue(
            all(node.exact for node in compiled.faces[0].nodes)
        )
        unsupported = card_record(
            "fixture:unsupported-protection",
            type_line="Creature — Test",
            oracle_text="Protection from modified creatures",
            keywords=("Protection",),
        )
        unsupported_ir = compile_oracle_card(
            unsupported,
            capability_registry=registry,
            capability_profile="commander_review",
        )
        self.assertFalse(unsupported_ir.faces[0].nodes[0].exact)
        self.assertEqual(
            "unsupported_protection_quality",
            unsupported_ir.faces[0].residuals[-1].kind,
        )


class TypedProtectionTests(unittest.TestCase):
    def test_untyped_and_unsupported_protection_fail_closed(self):
        self.assertIsNone(parse_protection_line("Protection from Goblins"))
        self.assertIsNone(
            parse_protection_line("Protection from red and from white")
        )
        self.assertEqual(
            ProtectionVerdict.UNRESOLVED,
            protection_verdict(
                {"keywords": ["Protection"]},
                ProtectionSource(colors=frozenset({"R"})),
            ),
        )
        self.assertEqual(
            ProtectionVerdict.UNRESOLVED,
            protection_verdict(
                {
                    "keywords": ["Protection"],
                    "ability_fragments": "not-an-array",
                },
                ProtectionSource(colors=frozenset({"R"})),
            ),
        )

    def test_matching_and_nonmatching_typed_protection_verdicts(self):
        protected = {
            "keywords": ["Protection"],
            "ability_fragments": [
                wrapped(
                    ProtectionSpec(ProtectionQualityKind.COLOR, "R")
                )
            ],
        }
        self.assertEqual(
            ProtectionVerdict.BLOCKED,
            protection_verdict(
                protected,
                ProtectionSource(colors=frozenset({"R"})),
            ),
        )
        self.assertEqual(
            ProtectionVerdict.ALLOWED,
            protection_verdict(
                protected,
                ProtectionSource(colors=frozenset({"U"})),
            ),
        )
        self.assertEqual(
            ProtectionVerdict.UNRESOLVED,
            protection_verdict(protected, None),
        )
        for spec, source in (
            (
                ProtectionSpec(
                    ProtectionQualityKind.CARD_TYPE,
                    "artifact",
                ),
                {"type_line": "Artifact Creature — Goblin"},
            ),
            (
                ProtectionSpec(ProtectionQualityKind.SUBTYPE, "aura"),
                {"type_line": "Enchantment — Aura"},
            ),
        ):
            with self.subTest(spec=spec):
                self.assertEqual(
                    ProtectionVerdict.BLOCKED,
                    protection_verdict(
                        {
                            "ability_fragments": [wrapped(spec)],
                            "keywords": ["Protection"],
                        },
                        ProtectionSource.from_characteristics(source),
                    ),
                )

    def test_layer_six_granted_protection_uses_typed_fragment(self):
        fragment = wrapped(
            ProtectionSpec(ProtectionQualityKind.COLOR, "R")
        )
        state = CharacteristicState(
            name="Protected Bear",
            controller="A",
            text="Base text",
            executable_text="Base text",
            card_types={"creature"},
            abilities=[],
        )
        effect = ContinuousEffect(
            effect_id="fixture:grant-protection",
            source_id="fixture:source",
            layer=Layer.ABILITY,
            sublayer="6",
            timestamp=1,
            origin=ContinuousEffectOrigin.STATIC_ABILITY,
            operations=(
                ContinuousOperation("add_ability", "Protection"),
                ContinuousOperation("add_ability_fragment", fragment),
            ),
        )
        evaluated = evaluate_continuous_effects(
            state,
            (effect,),
            context={"zone": "battlefield", "controller": "A"},
        ).characteristics
        self.assertIn("Protection", evaluated["abilities"])
        self.assertEqual([fragment], evaluated["ability_fragments"])
        self.assertEqual(
            ProtectionVerdict.BLOCKED,
            protection_verdict(
                {
                    "keywords": evaluated["abilities"],
                    "ability_fragments": evaluated["ability_fragments"],
                },
                ProtectionSource(colors=frozenset({"R"})),
            ),
        )
        handler = attached_fixed_characteristics_handler(
            "Enchanted creature has protection from red."
        )
        self.assertIsNotNone(handler)
        self.assertEqual(
            [fragment], handler[1]["modifier"]["add_ability_fragments"]
        )

    def test_text_only_grants_are_display_only_and_typed_grants_execute(self):
        typed = wrapped(
            GrantedActivatedAbilitySpec(
                ability_id="granted:damage",
                semantic_key="fixture:granted:damage",
                cost_text="{2}, {T}",
                effect_text="This creature deals 1 damage to any target",
                mana={"GENERIC": 2},
                tap_source=True,
            )
        )

        class Host:
            @staticmethod
            def _type_parts(type_line: str):
                return ({"creature"}, {"test"}, set())

            @staticmethod
            def _effective_card_data(card):
                del card
                return {
                    "name": "Bear",
                    "type_line": "Creature — Test",
                    "oracle_text": (
                        "{2}, {T}: This creature deals 1 damage to any target"
                    ),
                    "executable_oracle_text": "",
                    "keywords": [],
                    "ability_fragments": [typed],
                }

        card = CardInstance(
            object_id="bear-object",
            ref="C1",
            oracle_id="fixture:bear",
            printed_name="Bear",
            owner="A",
            controller="A",
            zone="battlefield",
        )
        discovered = activated_abilities(Host(), card)
        self.assertEqual(1, len(discovered))
        self.assertIsInstance(discovered[0], ActivatedAbility)
        self.assertEqual(
            "fixture:granted:damage",
            discovered[0].builtin_semantic_key,
        )


class TypedProtectionEngineTests(unittest.TestCase):
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
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.stack.clear()
        return session

    @staticmethod
    def creature(
        engine,
        seat: str,
        name: str,
        *,
        colors: tuple[str, ...] = (),
        protection: str | None = None,
    ):
        characteristics = {
            "type_line": "Token Creature — Test",
            "power": "2",
            "toughness": "2",
            "colors": list(colors),
        }
        if protection is not None:
            characteristics.update(
                {
                    "oracle_text": f"Protection from {protection}",
                    "keywords": ["Protection"],
                    "ability_fragments": [
                        wrapped(
                            ProtectionSpec(
                                ProtectionQualityKind.COLOR,
                                protection,
                            )
                        )
                    ],
                }
            )
        ref = engine.create_token(
            seat,
            name=name,
            characteristics=characteristics,
        )[0]
        return engine._resolve_object(
            seat,
            ref,
            zones={"battlefield"},
        )

    def test_typed_protection_blocks_target_attachment_and_block_operations(
        self,
    ):
        engine = self.session(7021601).engine
        protected = self.creature(
            engine,
            "B",
            "Protected Bear",
            protection="R",
        )
        red_source = self.creature(
            engine,
            "A",
            "Red Source",
            colors=("R",),
        )
        group = TargetGroup.from_mapping(
            {
                "zones": ["battlefield"],
                "categories": ["permanent"],
                "types_all": ["creature"],
                "count": 1,
            }
        )
        row = next(
            row
            for row in engine._target_candidate_rows("A", group)
            if row["ref"] == protected.ref
        )
        self.assertFalse(
            engine._target_row_matches(
                "A",
                group,
                row,
                source_ref=red_source.ref,
            )
        )
        self.assertFalse(engine._can_block(protected, red_source)[0])

        equipment_ref = engine.create_token(
            "A",
            name="Red Equipment",
            characteristics={
                "type_line": "Token Artifact — Equipment",
                "colors": ["R"],
            },
        )[0]
        equipment = engine._resolve_object(
            "A", equipment_ref, zones={"battlefield"}
        )
        attach_objects(
            engine.state.cards,
            equipment,
            protected,
            source_timestamp=engine._next_zone_timestamp(),
        )
        self.assertFalse(
            engine._attachment_is_legal(
                equipment,
                subtypes={"equipment"},
            )
        )

        before = set(engine.state.cards)
        aura_refs = engine.create_token(
            "A",
            name="Red Aura",
            characteristics={
                "type_line": "Token Enchantment — Aura",
                "colors": ["R"],
                "oracle_text": "Enchant creature",
                "ability_fragments": [
                    wrapped(SimpleEnchantSpec("creature"))
                ],
            },
            aura_target_ref=protected.ref,
        )
        self.assertEqual([], aura_refs)
        self.assertEqual(before, set(engine.state.cards))

    def test_four_player_protection_uses_the_actual_source(self):
        engine = self.session(7021602, players=4).engine
        protected = self.creature(
            engine,
            "C",
            "Protected Witness",
            protection="R",
        )
        red = self.creature(
            engine, "A", "Red Witness", colors=("R",)
        )
        blue = self.creature(
            engine, "D", "Blue Witness", colors=("U",)
        )
        group = TargetGroup.from_mapping(
            {
                "zones": ["battlefield"],
                "categories": ["permanent"],
                "types_all": ["creature"],
                "count": 1,
            }
        )
        row = next(
            row
            for row in engine._target_candidate_rows("A", group)
            if row["ref"] == protected.ref
        )
        self.assertFalse(
            engine._target_row_matches(
                "A", group, row, source_ref=red.ref
            )
        )
        self.assertTrue(
            engine._target_row_matches(
                "D", group, row, source_ref=blue.ref
            )
        )


if __name__ == "__main__":
    unittest.main()
