from __future__ import annotations

from dataclasses import replace
import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from mtg_commander_sim.declaration_restrictions import (
    parse_declaration_restriction_line,
)
from mtg_commander_sim.model import CombatState
from mtg_commander_sim.oracle_ir import compile_oracle_card
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)


class CombatDeclarationRestrictionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_combat_session(self, seed: int, *, players: int = 3):
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
        engine.state.priority_player = None
        engine.state.priority_passes = []
        engine.state.phase_index = 5
        engine.state.phase = "combat"
        engine.state.step = "declare_attackers"
        engine.state.combat = CombatState()
        session.commands.clear()
        session.decisions.clear()
        return session

    @staticmethod
    def creature(
        engine,
        seat: str,
        name: str,
        *,
        oracle_text: str = "",
        keywords: tuple[str, ...] = (),
        power: str = "2",
        toughness: str = "2",
        subtype: str = "Test",
        colors: tuple[str, ...] = (),
    ):
        ref = engine.create_token(
            seat,
            name=name,
            characteristics={
                "type_line": f"Token Creature — {subtype}",
                "oracle_text": oracle_text,
                "power": power,
                "toughness": toughness,
                "colors": list(colors),
            },
            temporary_keywords=keywords,
        )[0]
        return engine._resolve_object(seat, ref, zones={"battlefield"})

    @staticmethod
    def static_source(engine, seat: str, name: str, oracle_text: str):
        ref = engine.create_token(
            seat,
            name=name,
            characteristics={
                "type_line": "Token Enchantment",
                "oracle_text": oracle_text,
            },
        )[0]
        return engine._resolve_object(seat, ref, zones={"battlefield"})

    def set_block_step(self, engine, attackers):
        engine.state.phase_index = 6
        engine.state.step = "declare_blockers"
        engine.state.combat = CombatState(
            attackers={card.object_id: defender for card, defender in attackers},
            attackers_declared=True,
            defending_players=sorted({defender for _, defender in attackers}),
        )
        for card, defender in attackers:
            card.attacking = defender

    def test_shared_parser_is_anchored_and_classifies_exact_families(self):
        cases = {
            "This creature can't attack or block.": (
                "intrinsic-attack-block-prohibition-v1",
                ("attack", "block"),
            ),
            "Enchanted creature can't attack or block.": (
                "attached-attack-block-prohibition-v1",
                ("attack", "block"),
            ),
            "This creature can't attack or block alone.": (
                "intrinsic-attack-block-not-alone-v1",
                ("attack", "block"),
            ),
            "No more than one creature can attack each combat.": (
                "global-maximum-1-attack-v1",
                ("attack",),
            ),
            "Creatures with power less than this creature's power can't block it.": (
                "source-power-evasion-v1",
                ("block",),
            ),
            "This creature can't be blocked.": (
                "intrinsic-unblockable-v1",
                ("block",),
            ),
            "This creature can't be blocked by more than one creature.": (
                "intrinsic-maximum-blockers-v1",
                ("block",),
            ),
            "This creature can't be blocked except by three or more creatures.": (
                "intrinsic-minimum-blockers-v1",
                ("block",),
            ),
            "This creature can block only creatures with flying.": (
                "intrinsic-block-only-keyword-v1",
                ("block",),
            ),
        }
        for text, (template_id, declarations) in cases.items():
            with self.subTest(text=text):
                parsed = parse_declaration_restriction_line(text)
                self.assertTrue(parsed.exact)
                self.assertEqual(template_id, parsed.template.template_id)
                self.assertEqual(declarations, parsed.declarations)

        triggered = parse_declaration_restriction_line(
            "Whenever this creature attacks, target creature can't block this turn."
        )
        self.assertFalse(triggered.recognized)

        unsupported = parse_declaration_restriction_line(
            "This creature can't attack unless you control another artifact."
        )
        self.assertTrue(unsupported.recognized)
        self.assertFalse(unsupported.exact)
        self.assertEqual(("attack",), unsupported.declarations)

    def test_absolute_self_and_attached_restrictions_remove_domains(self):
        session = self.make_combat_session(508010901, players=2)
        engine = session.engine
        self.creature(
            engine,
            "A",
            "Grounded",
            oracle_text="This creature can't attack.",
            keywords=("Haste",),
        )
        attached = self.creature(
            engine, "A", "Pacified", keywords=("Haste",)
        )
        aura = self.static_source(
            engine,
            "B",
            "Exact Aura",
            "Enchanted creature can't attack or block.",
        )
        aura.attached_to = attached.object_id
        attached.attachments.append(aura.object_id)
        free = self.creature(engine, "A", "Free", keywords=("Haste",))

        engine._issue_attackers()

        payload = engine.state.pending_decision.payload_by_actor["A"]
        self.assertEqual(
            {free.ref},
            set(payload["declaration_constraints"]["domains"]),
        )
        self.assertEqual([free.ref], [item["id"] for item in payload["candidates"]])

        attacker = self.creature(engine, "B", "Opponent")
        self.assertEqual(
            (
                False,
                "declaration_restriction:attached-attack-block-prohibition-v1",
            ),
            engine._can_block(attacker, attached),
        )

    def test_attack_or_block_alone_allows_different_defenders_and_replays(self):
        session = self.make_combat_session(508010902)
        engine = session.engine
        flunky = self.creature(
            engine,
            "A",
            "Group Attacker",
            oracle_text="This creature can't attack or block alone.",
            keywords=("Haste",),
        )
        ally = self.creature(engine, "A", "Ally", keywords=("Haste",))
        engine._issue_attackers()
        session.initial_checkpoint = checkpoint_envelope(session.state)

        before = authoritative_state_hash(session.state)
        rejected = session.act(
            "pilot:A",
            {"a": "attack", "atk": {flunky.ref: "B"}},
        )
        self.assertFalse(rejected.ok)
        self.assertEqual(before, authoritative_state_hash(session.state))

        accepted = session.act(
            "pilot:A",
            {
                "a": "attack",
                "atk": {flunky.ref: "B", ally.ref: "C"},
            },
        )
        self.assertTrue(accepted.ok, accepted.summary)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "not-alone-replay"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(1, replay["commands"])

    def test_block_alone_allows_other_blocker_on_different_attacker(self):
        session = self.make_combat_session(509010901, players=2)
        engine = session.engine
        first = self.creature(engine, "A", "First", keywords=("Haste",))
        second = self.creature(engine, "A", "Second", keywords=("Haste",))
        hulk = self.creature(
            engine,
            "B",
            "Group Blocker",
            oracle_text="This creature can't block alone.",
        )
        ally = self.creature(engine, "B", "Other Blocker")
        self.set_block_step(engine, [(first, "B"), (second, "B")])
        engine._issue_next_blocker()

        rejected = session.act(
            "pilot:B",
            {"a": "block", "blocks": {hulk.ref: first.ref}},
        )
        self.assertFalse(rejected.ok)

        accepted = session.act(
            "pilot:B",
            {
                "a": "block",
                "blocks": {hulk.ref: first.ref, ally.ref: second.ref},
            },
        )
        self.assertTrue(accepted.ok, accepted.summary)

    def test_global_maximum_constrains_requirement_solver(self):
        session = self.make_combat_session(508010903, players=2)
        engine = session.engine
        attackers = [
            self.creature(
                engine,
                "A",
                f"Required {index}",
                oracle_text="This creature attacks each combat if able.",
                keywords=("Haste",),
            )
            for index in range(2)
        ]
        self.static_source(
            engine,
            "B",
            "Exact Arbiter",
            "No more than one creature can attack each combat.",
        )
        engine._issue_attackers()

        constraints = engine.state.pending_decision.payload_by_actor["A"][
            "declaration_constraints"
        ]
        self.assertEqual(1, constraints["maximum_requirements"])
        self.assertFalse(
            session.act(
                "pilot:A",
                {
                    "a": "attack",
                    "atk": {card.ref: "B" for card in attackers},
                },
            ).ok
        )
        self.assertTrue(
            session.act(
                "pilot:A",
                {"a": "attack", "atk": {attackers[0].ref: "B"}},
            ).ok
        )

    def test_goaded_opponent_creature_cannot_block(self):
        session = self.make_combat_session(509010902, players=2)
        engine = session.engine
        attacker = self.creature(engine, "A", "Attacker", keywords=("Haste",))
        goaded = self.creature(engine, "B", "Goaded Blocker")
        free = self.creature(engine, "B", "Free Blocker")
        self.creature(
            engine,
            "A",
            "Restriction Source",
            oracle_text="Goaded creatures your opponents control can't block.",
        )
        engine.apply_effect({"op": "goad", "card": goaded.ref}, actor="A")
        self.set_block_step(engine, [(attacker, "B")])
        engine._issue_next_blocker()

        domains = engine.state.pending_decision.payload_by_actor["B"][
            "declaration_constraints"
        ]["domains"]
        self.assertNotIn(goaded.ref, domains)
        self.assertIn(free.ref, domains)

    def test_keyword_filtered_global_attack_restriction(self):
        session = self.make_combat_session(508010904, players=2)
        engine = session.engine
        grounded = self.creature(engine, "A", "Grounded", keywords=("Haste",))
        flying = self.creature(
            engine, "A", "Flying", keywords=("Haste", "Flying")
        )
        islandwalk = self.creature(
            engine, "A", "Walker", keywords=("Haste", "Islandwalk")
        )
        self.static_source(
            engine,
            "B",
            "Exact Tide",
            "Creatures without flying or islandwalk can't attack.",
        )
        engine._issue_attackers()

        domains = engine.state.pending_decision.payload_by_actor["A"][
            "declaration_constraints"
        ]["domains"]
        self.assertNotIn(grounded.ref, domains)
        self.assertIn(flying.ref, domains)
        self.assertIn(islandwalk.ref, domains)

    def test_power_color_and_subtype_block_restrictions_are_cumulative(self):
        session = self.make_combat_session(509010903, players=2)
        engine = session.engine
        wolf = self.creature(
            engine,
            "A",
            "Power Evasion",
            oracle_text=(
                "Creatures with power less than this creature's power "
                "can't block it."
            ),
            keywords=("Haste",),
            power="3",
            subtype="Warrior",
            colors=("B",),
        )
        small = self.creature(engine, "B", "Small", power="2")
        equal = self.creature(engine, "B", "Equal", power="3")
        color_limited = self.creature(
            engine,
            "B",
            "Color Limited",
            oracle_text="This creature can't block black creatures.",
            power="4",
        )
        coward = self.creature(
            engine, "B", "Coward", power="4", subtype="Coward"
        )
        self.static_source(
            engine,
            "A",
            "Subtype Rule",
            "Cowards can't block Warriors.",
        )
        self.set_block_step(engine, [(wolf, "B")])
        engine._issue_next_blocker()

        domains = engine.state.pending_decision.payload_by_actor["B"][
            "declaration_constraints"
        ]["domains"]
        self.assertNotIn(small.ref, domains)
        self.assertIn(equal.ref, domains)
        self.assertNotIn(color_limited.ref, domains)
        self.assertNotIn(coward.ref, domains)

    def test_numeric_power_block_restriction_uses_effective_power(self):
        session = self.make_combat_session(509010904, players=2)
        engine = session.engine
        small = self.creature(
            engine, "A", "Small Attack", keywords=("Haste",), power="1"
        )
        large = self.creature(
            engine, "A", "Large Attack", keywords=("Haste",), power="2"
        )
        blocker = self.creature(
            engine,
            "B",
            "Numeric Blocker",
            oracle_text="This creature can't block creatures with power 2 or greater.",
        )
        self.set_block_step(engine, [(small, "B"), (large, "B")])
        engine._issue_next_blocker()

        domains = engine.state.pending_decision.payload_by_actor["B"][
            "declaration_constraints"
        ]["domains"]
        self.assertEqual([small.ref], domains[blocker.ref])

    def test_unblockable_and_blocker_stat_evasion_filter_domains(self):
        session = self.make_combat_session(509010905, players=2)
        engine = session.engine
        unblockable = self.creature(
            engine,
            "A",
            "Unblockable",
            oracle_text="This creature can't be blocked.",
            keywords=("Haste",),
        )
        limited = self.creature(
            engine,
            "A",
            "Stat Evasion",
            oracle_text=(
                "This creature can't be blocked by creatures with power 3 "
                "or greater."
            ),
            keywords=("Haste",),
        )
        small = self.creature(engine, "B", "Small Blocker", power="2")
        large = self.creature(engine, "B", "Large Blocker", power="3")
        self.set_block_step(
            engine, [(unblockable, "B"), (limited, "B")]
        )
        engine._issue_next_blocker()

        domains = engine.state.pending_decision.payload_by_actor["B"][
            "declaration_constraints"
        ]["domains"]
        self.assertEqual([limited.ref], domains[small.ref])
        self.assertNotIn(large.ref, domains)

    def test_only_unblockable_attackers_skip_pass_only_blocker_task(self):
        session = self.make_combat_session(509010909, players=2)
        engine = session.engine
        attacker = self.creature(
            engine,
            "A",
            "No Legal Blocks",
            oracle_text="This creature can't be blocked.",
            keywords=("Haste",),
        )
        self.creature(engine, "B", "Unable Blocker")
        self.set_block_step(engine, [(attacker, "B")])

        engine._issue_next_blocker()

        self.assertTrue(engine.state.combat.blockers_declared)
        self.assertEqual("A", engine.state.priority_player)
        self.assertTrue(
            all(
                decision.kind != "combat.blockers"
                for decision in session.decisions
            )
        )
        event = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "combat.block"
        )
        self.assertTrue(event.details["automatic"])

    def test_minimum_and_maximum_blocker_counts_are_inviolable(self):
        minimum_session = self.make_combat_session(509010906, players=2)
        engine = minimum_session.engine
        attacker = self.creature(
            engine,
            "A",
            "Needs Three",
            oracle_text=(
                "This creature can't be blocked except by three or more creatures."
            ),
            keywords=("Haste",),
        )
        blockers = [
            self.creature(engine, "B", f"Blocker {index}")
            for index in range(3)
        ]
        self.set_block_step(engine, [(attacker, "B")])
        engine._issue_next_blocker()
        self.assertFalse(
            minimum_session.act(
                "pilot:B",
                {
                    "a": "block",
                    "blocks": {
                        blocker.ref: attacker.ref for blocker in blockers[:2]
                    },
                },
            ).ok
        )
        self.assertTrue(
            minimum_session.act(
                "pilot:B",
                {
                    "a": "block",
                    "blocks": {
                        blocker.ref: attacker.ref for blocker in blockers
                    },
                },
            ).ok
        )

        maximum_session = self.make_combat_session(509010907, players=2)
        engine = maximum_session.engine
        attacker = self.creature(
            engine,
            "A",
            "Only One",
            oracle_text=(
                "This creature can't be blocked by more than one creature."
            ),
            keywords=("Haste",),
        )
        blockers = [
            self.creature(engine, "B", f"Max Blocker {index}")
            for index in range(2)
        ]
        self.set_block_step(engine, [(attacker, "B")])
        engine._issue_next_blocker()
        self.assertFalse(
            maximum_session.act(
                "pilot:B",
                {
                    "a": "block",
                    "blocks": {
                        blocker.ref: attacker.ref for blocker in blockers
                    },
                },
            ).ok
        )
        self.assertTrue(
            maximum_session.act(
                "pilot:B",
                {
                    "a": "block",
                    "blocks": {blockers[0].ref: attacker.ref},
                },
            ).ok
        )

    def test_block_only_keyword_filters_opposing_attackers(self):
        session = self.make_combat_session(509010908, players=2)
        engine = session.engine
        ground = self.creature(
            engine, "A", "Ground Attack", keywords=("Haste",)
        )
        flying = self.creature(
            engine,
            "A",
            "Flying Attack",
            keywords=("Haste", "Flying"),
        )
        blocker = self.creature(
            engine,
            "B",
            "Cloud Blocker",
            oracle_text="This creature can block only creatures with flying.",
            keywords=("Flying",),
        )
        self.set_block_step(engine, [(ground, "B"), (flying, "B")])
        engine._issue_next_blocker()

        domains = engine.state.pending_decision.payload_by_actor["B"][
            "declaration_constraints"
        ]["domains"]
        self.assertEqual([flying.ref], domains[blocker.ref])

    def test_relevant_unsupported_condition_pauses_fail_closed(self):
        session = self.make_combat_session(508010905, players=2)
        engine = session.engine
        self.creature(
            engine,
            "A",
            "Conditional",
            oracle_text=(
                "This creature can't attack unless you control another artifact."
            ),
            keywords=("Haste",),
        )

        engine._issue_attackers()

        self.assertIsNone(engine.state.pending_decision)
        pause = engine._semantic_pause_annotation()
        self.assertIsNotNone(pause)
        self.assertIn("combat.attack_restriction", pause["event"])

    def test_triggered_text_is_not_misread_as_a_static_restriction(self):
        session = self.make_combat_session(508010906, players=2)
        engine = session.engine
        attacker = self.creature(
            engine,
            "A",
            "Triggered Text",
            oracle_text=(
                "Whenever this creature attacks, target creature can't block "
                "this turn."
            ),
            keywords=("Haste",),
        )

        engine._issue_attackers()

        domains = engine.state.pending_decision.payload_by_actor["A"][
            "declaration_constraints"
        ]["domains"]
        self.assertIn(attacker.ref, domains)

    def test_oracle_ir_uses_runtime_restriction_grammar(self):
        base = self.db.lookup("Arcum Dagsson")
        exact = replace(
            base,
            type_line="Creature — Goblin",
            oracle_text="This creature can't attack or block alone.",
        )
        ir = compile_oracle_card(
            exact,
            trusted_mechanics={
                "cr-508-declare-attackers-step",
                "cr-509-declare-blockers-step",
            },
        )

        self.assertEqual("exact", ir.status)
        node = ir.faces[0].nodes[0]
        self.assertEqual("intrinsic-attack-block-not-alone-v1", node.template_id)
        self.assertEqual("declaration_restriction", node.effects[0]["op"])

        unresolved = compile_oracle_card(
            replace(
                exact,
                oracle_text=(
                    "This creature can't attack unless you control another artifact."
                ),
            ),
            trusted_mechanics={"cr-508-declare-attackers-step"},
        )
        self.assertTrue(unresolved.material_residuals)
        self.assertEqual(
            "declaration_restriction",
            unresolved.material_residuals[0].kind,
        )


if __name__ == "__main__":
    unittest.main()
