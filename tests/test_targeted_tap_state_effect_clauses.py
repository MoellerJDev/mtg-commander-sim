from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from common import DB_PATH, keep_all, load_assets, make_session
from mtg_commander_sim.carddb import CardDatabase
from mtg_commander_sim.compiler.tap_state_templates import (
    TapStateAction,
    TapStateTarget,
    TargetedTapStateEffectTemplate,
    targeted_tap_state_effect_template,
)
from mtg_commander_sim.model import StackItem
from mtg_commander_sim.oracle_ir import (
    compile_oracle_card,
    register_generated_programs,
)
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)
from mtg_commander_sim.rules.capabilities import (
    capability_dependencies_for_node,
    load_default_capability_registry,
)
from mtg_commander_sim.semantics import SemanticRegistry


class TargetedTapStateTemplateTests(unittest.TestCase):
    def test_targeted_tap_state_template_is_immutable_and_copy_isolated(self):
        template = TargetedTapStateEffectTemplate(
            action=TapStateAction.TAP,
            target=TapStateTarget.CREATURE,
        )

        self.assertEqual("tap-target-creature-v2", template.template_id)
        self.assertEqual(
            ({"op": "tap", "card": "$target.0"},),
            template.effects,
        )
        schema = template.target_schema
        schema["types_any"].append("land")
        effects = template.effects
        effects[0]["op"] = "untap"
        self.assertEqual(["creature"], template.target_schema["types_any"])
        self.assertEqual("tap", template.effects[0]["op"])
        with self.assertRaisesRegex(ValueError, "action"):
            TargetedTapStateEffectTemplate(  # type: ignore[arg-type]
                action="tap",
                target=TapStateTarget.CREATURE,
            )
        with self.assertRaisesRegex(ValueError, "target"):
            TargetedTapStateEffectTemplate(  # type: ignore[arg-type]
                action=TapStateAction.TAP,
                target="creature",
            )

    def test_whole_clause_parser_accepts_only_closed_direct_targets(self):
        for action in TapStateAction:
            for target in TapStateTarget:
                with self.subTest(action=action, target=target):
                    template = targeted_tap_state_effect_template(
                        f"{action.value.title()} target {target.value}."
                    )
                    self.assertIsNotNone(template)
                    assert template is not None
                    self.assertEqual(action, template.action)
                    self.assertEqual(target, template.target)
        for text in (
            "Tap up to two target creatures.",
            "Tap or untap target creature.",
            "You may tap target creature.",
            "Tap target creature. Scry 1.",
            "Tap target creature an opponent controls.",
            "Untap all creatures you control.",
            "Untap another target permanent.",
            "Tap target artifact or creature.",
            "Tap enchanted creature.",
        ):
            with self.subTest(text=text):
                self.assertIsNone(targeted_tap_state_effect_template(text))


class TargetedTapStateCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDatabase(DB_PATH)
        cls.base = cls.db.lookup("Lightning Bolt")
        cls.capabilities = load_default_capability_registry()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def compile(self, oracle_text: str, *, type_line: str = "Instant"):
        return compile_oracle_card(
            replace(
                self.base,
                name="Fixture",
                oracle_text=oracle_text,
                type_line=type_line,
                keywords=(),
                faces=(),
            ),
            capability_registry=self.capabilities,
            capability_profile="commander_review",
        )

    def test_spell_trigger_and_activated_contexts_share_targeted_tap_state_lowering(self):
        contexts = (
            (
                "Tap target creature.",
                "Instant",
                "spell_ability",
                "tap-target-creature-v2",
                "permanent.tap.effect",
            ),
            (
                "When this creature enters, tap target creature.",
                "Creature — Test",
                "triggered_ability",
                "tap-target-creature-v2",
                "permanent.tap.effect",
            ),
            (
                "{B}, {T}: Tap target creature.",
                "Creature — Test",
                "activated_ability",
                "tap-target-creature-v2",
                "permanent.tap.effect",
            ),
            (
                "Untap target permanent.",
                "Instant",
                "spell_ability",
                "untap-target-permanent-v2",
                "permanent.untap.effect",
            ),
            (
                "When this artifact enters, untap target artifact.",
                "Artifact",
                "triggered_ability",
                "untap-target-artifact-v2",
                "permanent.untap.effect",
            ),
            (
                "{1}, {T}: Untap target artifact.",
                "Artifact",
                "activated_ability",
                "untap-target-artifact-v2",
                "permanent.untap.effect",
            ),
        )
        for text, type_line, kind, template_id, capability in contexts:
            with self.subTest(kind=kind, text=text):
                ir = self.compile(text, type_line=type_line)
                node = ir.faces[0].nodes[0]
                self.assertEqual("exact", ir.status)
                self.assertTrue(node.exact)
                self.assertEqual(kind, node.kind)
                self.assertEqual(template_id, node.template_id)
                self.assertEqual(
                    {capability, "target.revalidate_resolution"},
                    set(node.capability_dependencies)
                    - {
                        "trigger.event.normalized_zone_change",
                        "trigger.placement.apnap",
                    },
                )
                self.assertEqual(text, text[node.span.start : node.span.end])

    def test_unsupported_tap_state_variants_remain_material_residuals(self):
        for text in (
            "Tap up to two target creatures.",
            "Tap or untap target creature.",
            "You may tap target creature.",
            "Tap target creature. Scry 1.",
            "Tap target creature an opponent controls.",
            "Untap all creatures you control.",
            "Untap another target permanent.",
            "Tap target artifact or creature.",
        ):
            with self.subTest(text=text):
                ir = self.compile(text)
                self.assertNotEqual("exact", ir.status)
                self.assertTrue(ir.material_residuals)

    def test_targeted_tap_state_shape_mutants_fail_closed(self):
        template = TargetedTapStateEffectTemplate(
            action=TapStateAction.UNTAP,
            target=TapStateTarget.ARTIFACT,
        )
        expected = {
            "permanent.untap.effect",
            "target.revalidate_resolution",
        }
        self.assertEqual(
            expected,
            set(
                capability_dependencies_for_node(
                    effects=template.effects,
                    target_schema=template.target_schema,
                    mechanic_ids=template.mechanics,
                )
            ),
        )
        malformed_effects = (
            ({"op": "untap", "card": "$target.1"},),
            ({"op": "untap", "card": "$target.0", "reason": "open"},),
            ({"op": "untap", "card": "$source"},),
            ({"op": "untap_all_creatures"},),
        )
        for effects in malformed_effects:
            with self.subTest(effects=effects):
                self.assertFalse(
                    capability_dependencies_for_node(
                        effects=effects,
                        target_schema=template.target_schema,
                        mechanic_ids=template.mechanics,
                    )
                )
        malformed_schemas = (
            {**template.target_schema, "zones": ["hand"]},
            {**template.target_schema, "count": 2},
            {**template.target_schema, "types_any": ["artifact", "land"]},
        )
        for schema in malformed_schemas:
            with self.subTest(schema=schema):
                self.assertFalse(
                    capability_dependencies_for_node(
                        effects=template.effects,
                        target_schema=schema,
                        mechanic_ids=template.mechanics,
                    )
                )
        self.assertFalse(
            capability_dependencies_for_node(
                effects=template.effects,
                target_schema=template.target_schema,
                mechanic_ids=("tap-and-untap",),
            )
        )

    def test_generated_direct_target_programs_are_capability_closed(self):
        registry = SemanticRegistry(include_builtin_packs=False)
        result = register_generated_programs(
            self.db,
            registry,
            (self.db.lookup("Rathi Trapper"), self.db.lookup("Voltaic Key")),
            capability_registry=self.capabilities,
            capability_profile="commander_review",
            promote_exact_effect_programs=True,
        )
        programs = [program for program in registry.programs() if program.effects]
        self.assertEqual(2, result["exact_effect_programs_promoted"])
        self.assertEqual({"trusted"}, {program.trust_level for program in programs})
        self.assertEqual(
            {
                "permanent.tap.effect",
                "permanent.untap.effect",
            },
            {
                dependency
                for program in programs
                for dependency in program.capability_dependencies
                if dependency.startswith("permanent.")
            },
        )


class TargetedTapStateRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def session_with_card(self, card_name: str, *, players: int, seed: int):
        deck = copy.deepcopy(self.mishra)
        next(entry for entry in deck.entries if entry.board == "mainboard").name = (
            card_name
        )
        session = make_session(
            self.db,
            deck,
            self.zimone,
            players=players,
            seed=seed,
            auto_pass_empty=False,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.state.priority_passes = []
        session.commands.clear()
        session.decisions.clear()
        return session

    @staticmethod
    def pass_stack(session):
        while session.state.stack:
            principals = session.pending_principals()
            if not principals:
                raise AssertionError("Stack resolution stopped without priority")
            result = session.act(principals[0], {"action_id": "pass"})
            if not result.ok:
                raise AssertionError(result.summary)

    def assert_replays(self, session, label: str):
        expected_hash = authoritative_state_hash(session.state)
        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / label
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(expected_hash, replay["final_state_hash"])

    @staticmethod
    def stage_activation(session, source, *, mana: dict[str, int]):
        engine = session.engine
        engine.move_card(
            source.object_id,
            "battlefield",
            controller="A",
            tapped=False,
            log=False,
        )
        engine.state.players["A"].turns_begun = 1
        source.acquired_control_turn_count = 0
        engine.state.players["A"].mana_pool.update(mana)
        engine._grant_priority("A")
        engine.pump()

    def test_compiled_tap_activation_is_multiplayer_public_and_replays(self):
        session = self.session_with_card(
            "Rathi Trapper",
            players=4,
            seed=7012608,
        )
        engine = session.engine
        source = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "A" and card.printed_name == "Rathi Trapper"
        )
        target_ref = engine.create_token(
            "C",
            name="Public Tap Target",
            characteristics={
                "type_line": "Token Creature — Test",
                "power": "1",
                "toughness": "1",
            },
            reason="targeted tap-state fixture",
        )[0]
        target = engine._resolve_object("A", target_ref, zones={"battlefield"})
        self.stage_activation(session, source, mana={"B": 1})
        packet = session.packet("pilot:A", full=True)
        action = next(
            row
            for row in packet["decision"]["ctx"]["legal"]["actions"]
            if row["id"] == f"activate:{source.ref}:ab1"
        )
        self.assertIn(target.ref, action["target_schema"]["legal_refs"])
        self.assertFalse(
            {"A", "B", "C", "D"}.intersection(
                action["target_schema"]["legal_refs"]
            )
        )
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()

        before = authoritative_state_hash(engine.state)
        rejected = session.act(
            "pilot:A",
            {"action_id": action["id"], "targets": ["C"]},
        )
        self.assertFalse(rejected.ok)
        self.assertEqual(before, authoritative_state_hash(engine.state))
        source = engine.state.cards[source.object_id]
        target = engine.state.cards[target.object_id]

        accepted = session.act(
            "pilot:A",
            {"action_id": action["id"], "targets": [target.ref]},
        )
        self.assertTrue(accepted.ok, accepted.summary)
        self.assertTrue(source.tapped)
        self.pass_stack(session)
        self.assertTrue(target.tapped)
        self.assert_replays(session, "targeted-tap-record")

    def test_compiled_untap_activation_consumes_stun_and_replays(self):
        session = self.session_with_card(
            "Voltaic Key",
            players=2,
            seed=7012609,
        )
        engine = session.engine
        source = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "A" and card.printed_name == "Voltaic Key"
        )
        target_ref = engine.create_token(
            "B",
            name="Stunned Artifact",
            tapped=True,
            characteristics={"type_line": "Token Artifact"},
            reason="targeted untap fixture",
        )[0]
        target = engine._resolve_object("A", target_ref, zones={"battlefield"})
        target.counters["stun"] = 1
        self.stage_activation(session, source, mana={"C": 1})
        packet = session.packet("pilot:A", full=True)
        action = next(
            row
            for row in packet["decision"]["ctx"]["legal"]["actions"]
            if row["id"] == f"activate:{source.ref}:ab1"
        )
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()

        accepted = session.act(
            "pilot:A",
            {"action_id": action["id"], "targets": [target.ref]},
        )
        self.assertTrue(accepted.ok, accepted.summary)
        self.pass_stack(session)
        self.assertTrue(target.tapped)
        self.assertNotIn("stun", target.counters)
        self.assertIn(
            "permanent.untap.replaced",
            [event.code for event in engine.state.events],
        )
        self.assert_replays(session, "targeted-untap-record")


if __name__ == "__main__":
    unittest.main()
