from __future__ import annotations

import unittest

from common import keep_all, load_assets, make_session
from mtg_commander_sim.model import StackItem
from mtg_commander_sim.preflight import card_semantic_status


class ExactMishraClosureTests(unittest.TestCase):
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
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        return session

    @staticmethod
    def card(engine, owner: str, name: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == owner and card.printed_name == name
        )

    @staticmethod
    def resolve_top(engine):
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine._prepare_stack_resolution()

    @staticmethod
    def prepare_main(engine, seat: str = "A"):
        engine.state.active_player = seat
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.stack.clear()
        engine.state.priority_player = seat

    def test_emry_mills_and_grants_exact_graveyard_cast_permission(self):
        session = self.make_session(1100)
        engine = session.engine
        emry = self.card(engine, "A", "Emry, Lurker of the Loch")
        target = self.card(engine, "A", "Sol Ring")
        engine.move_card(
            emry.object_id,
            "battlefield",
            controller="A",
            semantic_events=True,
        )
        before_library = len(engine.state.players["A"].zones["library"])
        self.assertFalse(engine._stabilize())
        self.resolve_top(engine)
        self.assertEqual(
            before_library - 4,
            len(engine.state.players["A"].zones["library"]),
        )

        engine.move_card(target.object_id, "graveyard")
        emry.acquired_control_turn_count = -1
        engine.state.priority_player = "A"
        engine._activate(
            "A",
            {
                "source": emry.ref,
                "ability": "ab3",
                "targets": [target.ref],
            },
        )
        self.resolve_top(engine)
        permission = target.annotations["temporary_play_permission"]
        self.assertEqual("A", permission["player"])
        self.assertEqual("graveyard", permission["zone"])
        self.assertFalse(permission["without_mana_cost"])

        self.prepare_main(engine)
        engine.state.players["A"].mana_pool["C"] = 1
        self.assertIn(
            target.ref,
            engine._priority_action_hints("A")["cast"],
        )

    def test_master_transmuter_pays_return_cost_and_puts_artifact(self):
        session = self.make_session(1101)
        engine = session.engine
        transmuter = self.card(engine, "A", "Master Transmuter")
        returned = self.card(engine, "A", "Sol Ring")
        deployed = self.card(engine, "A", "Portal to Phyrexia")
        for card in (transmuter, returned):
            engine.move_card(
                card.object_id,
                "battlefield",
                controller="A",
            )
        transmuter.acquired_control_turn_count = -1
        engine.move_card(deployed.object_id, "hand")
        engine.state.players["A"].mana_pool["U"] = 1
        engine.state.priority_player = "A"
        engine._activate(
            "A",
            {
                "source": transmuter.ref,
                "ability": "ab1",
                "cost_cards": [returned.ref],
                "pay": "manual",
                "payment": {"U": 1},
            },
        )
        self.assertEqual("hand", returned.zone)
        self.resolve_top(engine)
        self.assertEqual(
            "semantic.choice", engine.state.pending_decision.kind
        )
        result = session.act(
            "pilot:A",
            {
                "action_id": "choose",
                "card": deployed.ref,
                "plan": "DEVELOP_BOARD",
                "reason": "Put the selected artifact onto the battlefield.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual("battlefield", deployed.zone)

    def test_loki_scepter_temporary_control_untap_type_and_haste(self):
        session = self.make_session(1102)
        engine = session.engine
        scepter = self.card(engine, "A", "Loki's Scepter")
        victim = self.card(engine, "B", "Zimone and Dina")
        engine.move_card(
            victim.object_id,
            "battlefield",
            controller="B",
        )
        victim.tapped = True
        engine.move_card(
            scepter.object_id,
            "battlefield",
            controller="A",
            semantic_events=True,
        )
        self.assertTrue(engine._stabilize())
        self.assertEqual(
            "semantic.target", engine.state.pending_decision.kind
        )
        result = session.act(
            "pilot:A",
            {
                "action_id": "choose",
                "targets": [victim.ref],
                "plan": "TEMPORARY_THEFT",
                "reason": "Take the opposing creature for the turn.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.resolve_top(engine)
        self.assertEqual("A", victim.controller)
        self.assertFalse(victim.tapped)
        data = engine._effective_card_data(victim)
        self.assertIn("villain", engine._type_parts(data["type_line"])[1])
        self.assertIn("Haste", data["keywords"])

        engine._finish_cleanup()
        self.assertEqual("B", victim.controller)
        self.assertNotIn(
            "villain",
            engine._type_parts(
                engine._effective_card_data(victim)["type_line"]
            )[1],
        )

    def test_shuri_reduces_artifact_spells_and_copies_nonlegendary(self):
        session = self.make_session(1103)
        engine = session.engine
        shuri = self.card(engine, "A", "Shuri, Wakandan Inventor")
        signet = self.card(engine, "A", "Arcane Signet")
        source = self.card(engine, "A", "Strionic Resonator")
        copied = self.card(engine, "A", "The Mightstone and Weakstone")
        engine.move_card(shuri.object_id, "battlefield", controller="A")
        shuri.acquired_control_turn_count = -1
        engine.move_card(signet.object_id, "hand")
        self.prepare_main(engine)
        engine.state.players["A"].mana_pool["C"] = 1
        self.assertIn(
            signet.ref,
            engine._priority_action_hints("A")["cast"],
        )

        for card in (source, copied):
            engine.move_card(
                card.object_id,
                "battlefield",
                controller="A",
            )
        engine.state.players["A"].mana_pool["C"] = 1
        engine.state.priority_player = "A"
        engine._activate(
            "A",
            {
                "source": shuri.ref,
                "ability": "ab2",
                "targets": [
                    {"group": "copying", "ref": source.ref},
                    {"group": "copied", "ref": copied.ref},
                ],
                "pay": "manual",
                "payment": {"C": 1},
            },
        )
        self.resolve_top(engine)
        data = engine._effective_card_data(source)
        self.assertEqual(
            "The Mightstone and Weakstone", data["name"]
        )
        self.assertNotIn("legendary", data["type_line"].casefold())
        engine._finish_cleanup()
        self.assertEqual(
            "Strionic Resonator",
            engine._effective_card_data(source)["name"],
        )

    def test_simulacrum_synthesizer_scry_and_construct_trigger(self):
        session = self.make_session(1104)
        engine = session.engine
        synthesizer = self.card(engine, "A", "Simulacrum Synthesizer")
        portal = self.card(engine, "A", "The Stasis Coffin")
        engine.move_card(
            synthesizer.object_id,
            "battlefield",
            controller="A",
            semantic_events=True,
        )
        self.assertFalse(engine._stabilize())
        self.resolve_top(engine)
        self.assertEqual(
            "semantic.choice", engine.state.pending_decision.kind
        )
        result = session.act(
            "pilot:A",
            {
                "action_id": "choose",
                "cards": [],
                "plan": "CARD_SELECTION",
                "reason": "Keep both cards on top.",
            },
        )
        self.assertTrue(result.ok, result.summary)

        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.move_card(
            portal.object_id,
            "battlefield",
            controller="A",
            semantic_events=True,
        )
        self.assertFalse(engine._stabilize())
        self.resolve_top(engine)
        constructs = [
            card
            for card in engine.state.cards.values()
            if card.is_token
            and card.printed_name == "Construct"
            and card.controller == "A"
            and card.zone == "battlefield"
        ]
        self.assertEqual(1, len(constructs))
        artifact_count = sum(
            1
            for object_id in engine.state.players["A"].zones[
                "battlefield"
            ]
            if "artifact"
            in engine._type_parts(
                engine._effective_card_data(object_id)["type_line"]
            )[0]
        )
        self.assertEqual(
            artifact_count,
            engine._numeric_stat(constructs[0].object_id, "power"),
        )

    def test_stridehangar_adds_thopter_and_applies_anthem(self):
        session = self.make_session(1105)
        engine = session.engine
        automaton = self.card(engine, "A", "Stridehangar Automaton")
        engine.move_card(
            automaton.object_id,
            "battlefield",
            controller="A",
        )
        created = engine.create_token(
            "A",
            name="Treasure",
            characteristics={
                "type_line": "Token Artifact — Treasure",
            },
            reason="replacement characterization",
        )
        self.assertEqual(2, len(created))
        thopter = next(
            engine._resolve_object("A", ref)
            for ref in created
            if engine._resolve_object("A", ref).printed_name == "Thopter"
        )
        self.assertEqual(
            2, engine._numeric_stat(thopter.object_id, "power")
        )
        self.assertEqual(
            2, engine._numeric_stat(thopter.object_id, "toughness")
        )

    def test_worldwalker_adds_map_copies_token_and_map_explores(self):
        session = self.make_session(1106)
        engine = session.engine
        helm = self.card(engine, "A", "Worldwalker Helm")
        creature = self.card(engine, "A", "Goblin Engineer")
        land = self.card(engine, "A", "Island")
        engine.move_card(helm.object_id, "battlefield", controller="A")
        engine.move_card(creature.object_id, "battlefield", controller="A")
        created = engine.create_token(
            "A",
            name="Treasure",
            characteristics={
                "type_line": "Token Artifact — Treasure",
            },
            reason="replacement characterization",
        )
        self.assertEqual(2, len(created))
        treasure = next(
            engine._resolve_object("A", ref)
            for ref in created
            if engine._resolve_object("A", ref).printed_name == "Treasure"
        )
        first_map = next(
            engine._resolve_object("A", ref)
            for ref in created
            if engine._resolve_object("A", ref).printed_name == "Map"
        )

        helm.acquired_control_turn_count = -1
        self.prepare_main(engine)
        engine.state.players["A"].mana_pool.update({"C": 1, "U": 1})
        engine._activate(
            "A",
            {
                "source": helm.ref,
                "ability": "ab2",
                "targets": [treasure.ref],
                "pay": "manual",
                "payment": {"C": 1, "U": 1},
            },
        )
        self.resolve_top(engine)
        maps = [
            card
            for card in engine.state.cards.values()
            if card.is_token
            and card.printed_name == "Map"
            and card.zone == "battlefield"
        ]
        self.assertEqual(2, len(maps))

        engine.move_card(land.object_id, "library")
        library = engine.state.players["A"].zones["library"]
        library.remove(land.object_id)
        library.append(land.object_id)
        engine.state.players["A"].mana_pool["C"] = 1
        engine.state.priority_player = "A"
        engine._activate(
            "A",
            {
                "source": first_map.ref,
                "ability": "ab1",
                "targets": [creature.ref],
                "pay": "manual",
                "payment": {"C": 1},
            },
        )
        self.assertEqual("outside", first_map.zone)
        self.resolve_top(engine)
        self.assertEqual("hand", land.zone)

    @staticmethod
    def stack_item(
        engine,
        *,
        ref: str,
        kind: str,
        controller: str,
        label: str,
        semantic_key: str,
        source_object_id: str | None = None,
        card_object_id: str | None = None,
        targets: list[str] | None = None,
    ) -> StackItem:
        item = StackItem(
            stack_id=engine._stable_runtime_id("stack", ref),
            ref=ref,
            kind=kind,
            controller=controller,
            label=label,
            semantic_key=semantic_key,
            source_object_id=source_object_id,
            card_object_id=card_object_id,
            targets=list(targets or []),
            visibility=list(engine.seats),
            context={
                "target_groups": (
                    {"target_0": list(targets or [])}
                    if targets
                    else {}
                ),
                "target_snapshots": {
                    target: engine._target_snapshot(target)
                    for target in targets or []
                },
                "targets_revalidated": False,
                "targets_chosen_at_creation": True,
            },
        )
        engine.state.stack.append(item)
        return item

    def test_lithoform_engine_copies_abilities_spells_and_permanent_spells(
        self,
    ):
        with self.subTest(kind="ability"):
            session = self.make_session(1108)
            engine = session.engine
            lithoform = self.card(engine, "A", "Lithoform Engine")
            synthesizer = self.card(
                engine, "A", "Simulacrum Synthesizer"
            )
            for card in (lithoform, synthesizer):
                engine.move_card(
                    card.object_id,
                    "battlefield",
                    controller="A",
                )
            target = self.stack_item(
                engine,
                ref="S-copy-ability",
                kind="triggered_ability",
                controller="A",
                label="Synthetic artifact trigger",
                semantic_key=(
                    f"{synthesizer.oracle_id}:trigger:artifact-enter"
                ),
                source_object_id=synthesizer.object_id,
            )
            engine.state.players["A"].mana_pool["C"] = 2
            engine.state.priority_player = "A"
            engine._activate(
                "A",
                {
                    "source": lithoform.ref,
                    "ability": "ab1",
                    "targets": [target.ref],
                    "pay": "manual",
                    "payment": {"C": 2},
                },
            )
            self.resolve_top(engine)
            self.assertTrue(
                any(
                    item.context.get("copied_from_stack") == target.ref
                    for item in engine.state.stack
                )
            )

        with self.subTest(kind="instant"):
            session = self.make_session(1109)
            engine = session.engine
            lithoform = self.card(engine, "A", "Lithoform Engine")
            chaos_warp = self.card(engine, "A", "Chaos Warp")
            first_target = self.card(engine, "B", "Zimone and Dina")
            second_target = self.card(engine, "B", "Deathrite Shaman")
            engine.move_card(
                lithoform.object_id,
                "battlefield",
                controller="A",
            )
            for card in (first_target, second_target):
                engine.move_card(
                    card.object_id,
                    "battlefield",
                    controller="B",
                )
            engine.move_card(chaos_warp.object_id, "hand")
            engine.state.players["A"].mana_pool["R"] = 1
            engine.state.players["A"].mana_pool["C"] = 2
            engine.state.priority_player = "A"
            engine._cast(
                "A",
                {
                    "card": chaos_warp.ref,
                    "targets": [first_target.ref],
                    "pay": "manual",
                    "payment": {"R": 1, "C": 2},
                },
            )
            original = engine.state.stack[-1]
            lithoform.tapped = False
            engine.state.players["A"].mana_pool["C"] = 3
            engine.state.priority_player = "A"
            engine._activate(
                "A",
                {
                    "source": lithoform.ref,
                    "ability": "ab2",
                    "targets": [original.ref],
                    "pay": "manual",
                    "payment": {"C": 3},
                },
            )
            self.resolve_top(engine)
            self.assertEqual(
                "semantic.choice", engine.state.pending_decision.kind
            )
            result = session.act(
                "pilot:A",
                {
                    "action_id": "choose",
                    "targets": [second_target.ref],
                    "plan": "COPY_INTERACTION",
                    "reason": "Retarget the copied spell.",
                },
            )
            self.assertTrue(result.ok, result.summary)
            copied = next(
                item
                for item in engine.state.stack
                if item.context.get("copied_from_stack")
                == original.ref
            )
            self.assertEqual([second_target.ref], copied.targets)

        with self.subTest(kind="permanent"):
            session = self.make_session(1110)
            engine = session.engine
            lithoform = self.card(engine, "A", "Lithoform Engine")
            sol_ring = self.card(engine, "A", "Sol Ring")
            engine.move_card(
                lithoform.object_id,
                "battlefield",
                controller="A",
            )
            engine.move_card(sol_ring.object_id, "hand")
            self.prepare_main(engine)
            engine.state.players["A"].mana_pool["C"] = 1
            engine._cast(
                "A",
                {
                    "card": sol_ring.ref,
                    "pay": "manual",
                    "payment": {"C": 1},
                },
            )
            original = engine.state.stack[-1]
            lithoform.tapped = False
            engine.state.players["A"].mana_pool["C"] = 4
            engine.state.priority_player = "A"
            engine._activate(
                "A",
                {
                    "source": lithoform.ref,
                    "ability": "ab3",
                    "targets": [original.ref],
                    "pay": "manual",
                    "payment": {"C": 4},
                },
            )
            self.resolve_top(engine)
            copy_item = engine.state.stack[-1]
            self.assertTrue(copy_item.context["copy_permanent_spell"])
            self.resolve_top(engine)
            rings = [
                card
                for card in engine.state.cards.values()
                if card.printed_name == "Sol Ring"
                and card.zone == "battlefield"
                and card.controller == "A"
            ]
            self.assertEqual(1, len(rings))
            self.assertTrue(rings[0].is_token)

    def test_scientist_supreme_copies_artifact_ability_once_on_own_turn(
        self,
    ):
        session = self.make_session(1111)
        engine = session.engine
        scientist = self.card(
            engine, "A", "Scientist Supreme of A.I.M."
        )
        synthesizer = self.card(
            engine, "A", "Simulacrum Synthesizer"
        )
        for card in (scientist, synthesizer):
            engine.move_card(
                card.object_id,
                "battlefield",
                controller="A",
            )
        self.prepare_main(engine)
        target = self.stack_item(
            engine,
            ref="S-scientist-target",
            kind="triggered_ability",
            controller="A",
            label="Artifact-source trigger",
            semantic_key=(
                f"{synthesizer.oracle_id}:trigger:artifact-enter"
            ),
            source_object_id=synthesizer.object_id,
        )
        before_life = engine.state.players["A"].life
        engine.state.priority_player = "A"
        engine._activate(
            "A",
            {
                "source": scientist.ref,
                "ability": "ab1",
                "targets": [target.ref],
            },
        )
        self.resolve_top(engine)
        self.assertEqual(before_life - 2, engine.state.players["A"].life)
        ability = next(
            ability
            for ability in engine._activated_abilities(scientist)
            if ability.ability_id == "ab1"
        )
        self.assertEqual(
            "unavailable",
            engine._ability_availability("A", scientist, ability)[0],
        )
        self.assertTrue(
            any(
                item.context.get("copied_from_stack") == target.ref
                for item in engine.state.stack
            )
        )

    def test_strionic_resonator_only_copies_controlled_trigger(self):
        session = self.make_session(1112)
        engine = session.engine
        resonator = self.card(engine, "A", "Strionic Resonator")
        synthesizer = self.card(
            engine, "A", "Simulacrum Synthesizer"
        )
        for card in (resonator, synthesizer):
            engine.move_card(
                card.object_id,
                "battlefield",
                controller="A",
            )
        trigger = self.stack_item(
            engine,
            ref="S-strionic-trigger",
            kind="triggered_ability",
            controller="A",
            label="Controlled trigger",
            semantic_key=(
                f"{synthesizer.oracle_id}:trigger:artifact-enter"
            ),
            source_object_id=synthesizer.object_id,
        )
        activated = self.stack_item(
            engine,
            ref="S-strionic-activated",
            kind="activated_ability",
            controller="A",
            label="Controlled activated ability",
            semantic_key=(
                f"{synthesizer.oracle_id}:trigger:artifact-enter"
            ),
            source_object_id=synthesizer.object_id,
        )
        engine.state.players["A"].mana_pool["C"] = 2
        engine.state.priority_player = "A"
        hints = engine._priority_action_hints("A")
        action = next(
            row
            for row in hints["actions"]
            if row["id"] == f"activate:{resonator.ref}:ab1"
        )
        self.assertIn(trigger.ref, action["target_schema"]["legal_refs"])
        self.assertNotIn(
            activated.ref, action["target_schema"]["legal_refs"]
        )
        engine._activate(
            "A",
            {
                "source": resonator.ref,
                "ability": "ab1",
                "targets": [trigger.ref],
                "pay": "manual",
                "payment": {"C": 2},
            },
        )
        self.resolve_top(engine)
        self.assertTrue(
            any(
                item.context.get("copied_from_stack") == trigger.ref
                for item in engine.state.stack
            )
        )

    def test_promoted_mishra_cards_preflight_fully(self):
        engine = self.make_session(1107).engine
        for name in (
            "Emry, Lurker of the Loch",
            "Loki's Scepter",
            "Master Transmuter",
            "Shuri, Wakandan Inventor",
            "Simulacrum Synthesizer",
            "Stridehangar Automaton",
            "Strionic Resonator",
            "Lithoform Engine",
            "Scientist Supreme of A.I.M.",
            "Worldwalker Helm",
        ):
            with self.subTest(card=name):
                row = card_semantic_status(
                    self.db.lookup(name),
                    engine.semantics,
                    db=self.db,
                )
                self.assertEqual("fully_playable", row["status"], row)


if __name__ == "__main__":
    unittest.main()
