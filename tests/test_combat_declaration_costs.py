from __future__ import annotations

from dataclasses import replace
import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from mtg_commander_sim.model import CombatState
from mtg_commander_sim.oracle_ir import compile_oracle_card
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)


class CombatDeclarationCostTests(unittest.TestCase):
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
    ):
        ref = engine.create_token(
            seat,
            name=name,
            characteristics={
                "type_line": "Token Creature — Test",
                "oracle_text": oracle_text,
                "power": power,
                "toughness": "2",
            },
            temporary_keywords=keywords,
        )[0]
        return engine._resolve_object(seat, ref, zones={"battlefield"})

    @staticmethod
    def colorless_land(engine, seat: str, _label: str):
        ref = engine.create_token(
            seat,
            # Ghost Town is present in the compact CI fixture and has an
            # ordinary tap-for-colorless mode. Call-site labels keep multiple
            # sources readable even though token copies share a printed name.
            name="Ghost Town",
            characteristics={
                "type_line": "Token Land",
                "oracle_text": "{T}: Add {C}.",
            },
        )[0]
        return engine._resolve_object(seat, ref, zones={"battlefield"})

    @staticmethod
    def prison(engine, seat: str, name: str, cost: str = "{2}"):
        ref = engine.create_token(
            seat,
            name=name,
            characteristics={
                "type_line": "Token Enchantment",
                "oracle_text": (
                    "Creatures can't attack you unless their controller "
                    f"pays {cost} for each creature they control that's "
                    "attacking you."
                ),
            },
        )[0]
        return engine._resolve_object(seat, ref, zones={"battlefield"})

    @staticmethod
    def attach_tax(engine, seat: str, creature, *, cost: str = "{1}"):
        ref = engine.create_token(
            seat,
            name="Attached Tax",
            characteristics={
                "type_line": "Token Enchantment — Aura",
                "oracle_text": (
                    "Enchanted creature can't attack or block unless its "
                    f"controller pays {cost}."
                ),
            },
        )[0]
        aura = engine._resolve_object(
            seat, ref, zones={"battlefield"}
        )
        aura.attached_to = creature.object_id
        creature.attachments.append(aura.object_id)
        return aura

    def test_prison_tax_is_projected_paid_atomically_and_replays(self):
        session = self.make_combat_session(508010801)
        engine = session.engine
        attacker = self.creature(
            engine, "A", "Taxed Attacker", keywords=("Haste",)
        )
        prison = self.prison(engine, "B", "Generic Prison")
        lands = [
            self.colorless_land(engine, "A", f"Wastes {index}")
            for index in range(2)
        ]
        engine._issue_attackers()
        session.initial_checkpoint = checkpoint_envelope(session.state)

        payload = engine.state.pending_decision.payload_by_actor["A"]
        costs = payload["declaration_costs"]
        self.assertEqual(1, len(costs))
        self.assertEqual(attacker.ref, costs[0]["variable"])
        self.assertEqual("B", costs[0]["option"])
        self.assertEqual({"GENERIC": 2}, costs[0]["mana"])
        self.assertEqual(prison.ref, costs[0]["source"])
        self.assertNotIn(
            {"variable": attacker.ref, "option": "C"},
            payload["declaration_constraints"]["costed_options"],
        )

        result = session.act(
            "pilot:A",
            {
                "a": "attack",
                "atk": {attacker.ref: "B"},
                "pay": "auto",
            },
        )

        self.assertTrue(result.ok, result.summary)
        self.assertTrue(attacker.tapped)
        self.assertTrue(all(land.tapped for land in lands))
        event = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "combat.attack"
        )
        self.assertEqual({"GENERIC": 2}, event.details["requirements"])
        self.assertEqual(2, sum(event.details["payment"].values()))

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "attack-cost-replay"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(1, replay["commands"])

    def test_goad_does_not_force_payment_in_duel(self):
        session = self.make_combat_session(508010802, players=2)
        engine = session.engine
        attacker = self.creature(
            engine, "A", "Goaded Taxpayer", keywords=("Haste",)
        )
        self.prison(engine, "B", "Duel Prison")
        engine.apply_effect(
            {"op": "goad", "card": attacker.ref}, actor="B"
        )
        engine._issue_attackers()

        constraints = engine.state.pending_decision.payload_by_actor["A"][
            "declaration_constraints"
        ]
        self.assertEqual(0, constraints["maximum_requirements"])
        before = authoritative_state_hash(session.state)
        rejected = session.act(
            "pilot:A",
            {
                "a": "attack",
                "atk": {attacker.ref: "B"},
                "pay": "auto",
            },
        )
        self.assertFalse(rejected.ok)
        self.assertEqual(before, authoritative_state_hash(session.state))

        passed = session.act(
            "pilot:A", {"a": "attack", "atk": {}}
        )
        self.assertTrue(passed.ok, passed.summary)
        restored = engine._resolve_object(
            "A", attacker.ref, zones={"battlefield"}
        )
        self.assertFalse(restored.tapped)

    def test_goad_still_requires_a_free_other_player(self):
        session = self.make_combat_session(508010803)
        engine = session.engine
        attacker = self.creature(
            engine, "A", "Goaded Choice", keywords=("Haste",)
        )
        self.prison(engine, "B", "Selective Prison")
        engine.apply_effect(
            {"op": "goad", "card": attacker.ref}, actor="B"
        )
        engine._issue_attackers()

        constraints = engine.state.pending_decision.payload_by_actor["A"][
            "declaration_constraints"
        ]
        self.assertEqual(2, constraints["maximum_requirements"])
        empty = session.act(
            "pilot:A", {"a": "attack", "atk": {}}
        )
        self.assertFalse(empty.ok)
        wrong_defender = session.act(
            "pilot:A",
            {"a": "attack", "atk": {attacker.ref: "B"}},
        )
        self.assertFalse(wrong_defender.ok)

        free_attack = session.act(
            "pilot:A",
            {"a": "attack", "atk": {attacker.ref: "C"}},
        )
        self.assertTrue(free_attack.ok, free_attack.summary)

    def test_stacked_prisons_lock_one_aggregate_cost(self):
        session = self.make_combat_session(508010804)
        engine = session.engine
        attacker = self.creature(
            engine, "A", "Stacked Taxpayer", keywords=("Haste",)
        )
        self.prison(engine, "B", "First Prison", "{1}")
        self.prison(engine, "B", "Second Prison", "{2}")
        lands = [
            self.colorless_land(engine, "A", f"Source {index}")
            for index in range(3)
        ]
        engine._issue_attackers()

        result = session.act(
            "pilot:A",
            {
                "a": "attack",
                "atk": {attacker.ref: "B"},
                "pay": "auto",
            },
        )

        self.assertTrue(result.ok, result.summary)
        self.assertTrue(all(land.tapped for land in lands))
        event = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "combat.attack"
        )
        self.assertEqual({"GENERIC": 3}, event.details["requirements"])
        self.assertEqual(2, len(event.details["costs"]))

    def test_manual_attack_payment_uses_only_the_selected_mana_source(self):
        session = self.make_combat_session(508010405, players=2)
        engine = session.engine
        attacker = self.creature(
            engine, "A", "Manual Taxpayer", keywords=("Haste",)
        )
        self.prison(engine, "B", "Manual Prison", "{1}")
        first = self.colorless_land(engine, "A", "First Source")
        second = self.colorless_land(engine, "A", "Second Source")
        engine._issue_attackers()

        result = session.act(
            "pilot:A",
            {
                "a": "attack",
                "atk": {attacker.ref: "B"},
                "pay": "manual",
                "mana": [
                    {"source": second.ref, "bundle": {"C": 1}}
                ],
                "payment": {"C": 1},
            },
        )

        self.assertTrue(result.ok, result.summary)
        self.assertFalse(first.tapped)
        self.assertTrue(second.tapped)
        event = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "combat.attack"
        )
        self.assertEqual(
            [{"source": second.ref, "bundle": {"C": 1}}],
            event.details["mana_sources"],
        )

    def test_attack_player_tax_does_not_apply_to_a_battle(self):
        session = self.make_combat_session(508010406)
        engine = session.engine
        attacker = self.creature(
            engine, "A", "Battle Attacker", keywords=("Haste",)
        )
        self.prison(engine, "B", "Battle Bystander", "{2}")
        battle_ref = engine.create_token(
            "C",
            name="Protected Siege",
            battle_protector="B",
            characteristics={
                "type_line": "Token Battle — Siege",
                "defense": "3",
            },
        )[0]
        battle = engine._resolve_object(
            "C", battle_ref, zones={"battlefield"}
        )
        engine._issue_attackers()

        payload = engine.state.pending_decision.payload_by_actor["A"]
        self.assertIn(battle.ref, payload["defenders"])
        self.assertNotIn(
            {"variable": attacker.ref, "option": battle.ref},
            payload["declaration_constraints"]["costed_options"],
        )
        result = session.act(
            "pilot:A",
            {"a": "attack", "atk": {attacker.ref: battle.ref}},
        )
        self.assertTrue(result.ok, result.summary)

    def test_untapped_source_condition_controls_attack_tax(self):
        for tapped, expected_costs in ((False, 1), (True, 0)):
            with self.subTest(tapped=tapped):
                session = self.make_combat_session(
                    508010407 + int(tapped), players=2
                )
                engine = session.engine
                self.creature(
                    engine,
                    "A",
                    "Condition Attacker",
                    keywords=("Haste",),
                )
                angel = self.creature(
                    engine,
                    "B",
                    "Conditional Tithe",
                    oracle_text=(
                        "As long as this creature is untapped, creatures "
                        "can't attack you or planeswalkers you control "
                        "unless their controller pays {1} for each of "
                        "those creatures."
                    ),
                )
                angel.tapped = tapped
                engine._issue_attackers()

                payload = engine.state.pending_decision.payload_by_actor["A"]
                self.assertEqual(
                    expected_costs, len(payload["declaration_costs"])
                )

    def test_fixed_attached_attack_cost_uses_existing_attachment_identity(self):
        session = self.make_combat_session(508010409, players=2)
        engine = session.engine
        attacker = self.creature(
            engine, "A", "Enchanted Attacker", keywords=("Haste",)
        )
        aura = self.attach_tax(engine, "B", attacker)
        land = self.colorless_land(engine, "A", "Aura Payment")
        engine._issue_attackers()

        payload = engine.state.pending_decision.payload_by_actor["A"]
        self.assertEqual(aura.ref, payload["declaration_costs"][0]["source"])
        result = session.act(
            "pilot:A",
            {
                "a": "attack",
                "atk": {attacker.ref: "B"},
                "pay": "auto",
            },
        )

        self.assertTrue(result.ok, result.summary)
        self.assertTrue(land.tapped)

    def test_broader_conditional_attack_tax_stops_fail_closed(self):
        session = self.make_combat_session(508010410, players=2)
        engine = session.engine
        self.creature(
            engine, "A", "Conditional Target", keywords=("Haste",)
        )
        self.creature(
            engine,
            "B",
            "Domain Tax",
            oracle_text=(
                "Domain — Creatures can't attack you unless their "
                "controller pays {X} for each creature they control that's "
                "attacking you, where X is the number of basic land types "
                "among lands you control."
            ),
        )

        engine._issue_attackers()

        self.assertIsNone(engine.state.pending_decision)
        pause = engine._semantic_pause_annotation()
        self.assertIsNotNone(pause)
        self.assertIn("combat.attack_cost", pause["event"])

    def test_planeswalker_only_tax_does_not_tax_a_player_attack(self):
        session = self.make_combat_session(508010411, players=2)
        engine = session.engine
        self.creature(
            engine, "A", "Player Attacker", keywords=("Haste",)
        )
        self.creature(
            engine,
            "B",
            "Planeswalker Oathkeeper",
            oracle_text=(
                "Creatures can't attack planeswalkers you control unless "
                "their controller pays {1} for each creature they control "
                "that's attacking a planeswalker you control."
            ),
        )

        engine._issue_attackers()

        payload = engine.state.pending_decision.payload_by_actor["A"]
        self.assertEqual([], payload["declaration_costs"])

    def test_planeswalker_only_tax_is_locked_for_planeswalker_attack(self):
        session = self.make_combat_session(508010412, players=2)
        engine = session.engine
        attacker = self.creature(
            engine, "A", "Walker Tax Attacker", keywords=("Haste",)
        )
        self.creature(
            engine,
            "B",
            "Planeswalker Oathkeeper",
            oracle_text=(
                "Creatures can't attack planeswalkers you control unless "
                "their controller pays {1} for each creature they control "
                "that's attacking a planeswalker you control."
            ),
        )
        walker_ref = engine.create_token(
            "B",
            name="Taxed Walker",
            characteristics={
                "type_line": "Token Planeswalker — Test",
                "loyalty": "4",
            },
        )[0]
        walker = engine._resolve_object(
            "A", walker_ref, zones={"battlefield"}
        )
        land = self.colorless_land(engine, "A", "Tax Payment")

        engine._issue_attackers()

        payload = engine.state.pending_decision.payload_by_actor["A"]
        self.assertEqual(1, len(payload["declaration_costs"]))
        self.assertEqual(walker.ref, payload["declaration_costs"][0]["option"])
        result = session.act(
            "pilot:A",
            {
                "a": "attack",
                "atk": {attacker.ref: walker.ref},
                "pay": "auto",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertTrue(land.tapped)

    def test_player_and_planeswalker_tax_covers_both_target_kinds(self):
        session = self.make_combat_session(508010413, players=2)
        engine = session.engine
        attacker = self.creature(
            engine, "A", "Combined Tax Attacker", keywords=("Haste",)
        )
        self.creature(
            engine,
            "B",
            "Combined Tithe",
            oracle_text=(
                "Creatures can't attack you or planeswalkers you control "
                "unless their controller pays {1} for each of those creatures."
            ),
        )
        walker_ref = engine.create_token(
            "B",
            name="Combined Tax Walker",
            characteristics={
                "type_line": "Token Planeswalker — Test",
                "loyalty": "4",
            },
        )[0]
        walker = engine._resolve_object(
            "A", walker_ref, zones={"battlefield"}
        )

        engine._issue_attackers()

        costs = engine.state.pending_decision.payload_by_actor["A"][
            "declaration_costs"
        ]
        self.assertEqual(
            {(attacker.ref, "B"), (attacker.ref, walker.ref)},
            {(cost["variable"], cost["option"]) for cost in costs},
        )

    def test_nonvigilant_attacker_cannot_fund_its_own_attack_cost(self):
        session = self.make_combat_session(508010805, players=2)
        engine = session.engine
        attacker = self.creature(
            engine,
            "A",
            "Mana Attacker",
            oracle_text=(
                "This creature can't attack unless you pay {1}.\n"
                "{T}: Add one mana of any type."
            ),
            keywords=("Haste",),
        )
        engine._issue_attackers()
        before = authoritative_state_hash(session.state)

        result = session.act(
            "pilot:A",
            {
                "a": "attack",
                "atk": {attacker.ref: "B"},
                "pay": "auto",
            },
        )

        self.assertFalse(result.ok)
        self.assertEqual(before, authoritative_state_hash(session.state))

    def test_vigilant_attacker_may_activate_mana_while_cost_is_paid(self):
        session = self.make_combat_session(508010806, players=2)
        engine = session.engine
        attacker = self.creature(
            engine,
            "A",
            "Vigilant Mana Attacker",
            oracle_text=(
                "This creature can't attack unless you pay {1}.\n"
                "{T}: Add one mana of any type."
            ),
            keywords=("Haste", "Vigilance"),
        )
        engine._issue_attackers()

        result = session.act(
            "pilot:A",
            {
                "a": "attack",
                "atk": {attacker.ref: "B"},
                "pay": "auto",
            },
        )

        self.assertTrue(result.ok, result.summary)
        self.assertTrue(attacker.tapped)
        self.assertEqual("B", attacker.attacking)

    def test_sacrificed_mana_source_does_not_become_an_attacker(self):
        session = self.make_combat_session(5080108061, players=2)
        engine = session.engine
        attacker = self.creature(
            engine,
            "A",
            "Sacrificed Attacker",
            oracle_text=(
                "This creature can't attack unless you pay {1}.\n"
                "{T}, Sacrifice this creature: Add one mana of any type."
            ),
            keywords=("Haste", "Vigilance"),
        )
        engine._issue_attackers()

        result = session.act(
            "pilot:A",
            {
                "a": "attack",
                "atk": {attacker.ref: "B"},
                "pay": "auto",
            },
        )

        self.assertTrue(result.ok, result.summary)
        self.assertNotIn(
            attacker.object_id, engine.state.combat.attackers
        )
        self.assertFalse(engine.state.combat.had_attacking_creature)

    def test_complex_attack_tax_pauses_fail_closed(self):
        session = self.make_combat_session(508010807, players=2)
        engine = session.engine
        self.creature(
            engine, "A", "Potential Attacker", keywords=("Haste",)
        )
        self.prison(engine, "B", "Phyrexian Prison", "{W/P}")

        engine._issue_attackers()

        self.assertIsNone(engine.state.pending_decision)
        pause = engine._semantic_pause_annotation()
        self.assertIsNotNone(pause)
        self.assertEqual("Phyrexian Prison", pause["label"])
        self.assertIn("combat.attack_cost", pause["event"])

    def test_attacking_archangel_taxes_each_declared_blocker(self):
        session = self.make_combat_session(509010401, players=2)
        engine = session.engine
        attacker = self.creature(
            engine,
            "A",
            "Attacking Tithe Angel",
            oracle_text=(
                "As long as this creature is attacking, creatures can't "
                "block unless their controller pays {1} for each of those "
                "creatures."
            ),
            keywords=("Haste",),
        )
        blocker = self.creature(engine, "B", "Taxed Blocker")
        land = self.colorless_land(engine, "B", "Block Payment")
        engine.state.phase_index = 6
        engine.state.step = "declare_blockers"
        engine.state.combat = CombatState(
            attackers={attacker.object_id: "B"},
            attackers_declared=True,
            defending_players=["B"],
            blocker_cursor=0,
        )
        attacker.attacking = "B"
        engine._issue_next_blocker()
        session.initial_checkpoint = checkpoint_envelope(session.state)

        payload = engine.state.pending_decision.payload_by_actor["B"]
        self.assertEqual(1, len(payload["declaration_costs"]))
        result = session.act(
            "pilot:B",
            {
                "a": "block",
                "blocks": {blocker.ref: attacker.ref},
                "pay": "auto",
            },
        )

        self.assertTrue(result.ok, result.summary)
        self.assertTrue(land.tapped)
        self.assertEqual(attacker.object_id, blocker.blocking)
        event = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "combat.block"
        )
        self.assertEqual({"GENERIC": 1}, event.details["requirements"])

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "block-cost-replay"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(1, replay["commands"])

    def test_intrinsic_attack_or_block_cost_is_paid_to_block(self):
        session = self.make_combat_session(509010402, players=2)
        engine = session.engine
        attacker = self.creature(
            engine, "A", "Ordinary Attacker", keywords=("Haste",)
        )
        blocker = self.creature(
            engine,
            "B",
            "Costed Blocker",
            oracle_text=(
                "This creature can't attack or block unless you pay {1}."
            ),
        )
        land = self.colorless_land(engine, "B", "Block Source")
        engine.state.phase_index = 6
        engine.state.step = "declare_blockers"
        engine.state.combat = CombatState(
            attackers={attacker.object_id: "B"},
            attackers_declared=True,
            defending_players=["B"],
        )
        attacker.attacking = "B"
        engine._issue_next_blocker()

        payload = engine.state.pending_decision.payload_by_actor["B"]
        self.assertEqual([attacker.ref], payload["legal_blocks"][blocker.ref])
        self.assertEqual(1, len(payload["declaration_costs"]))
        result = session.act(
            "pilot:B",
            {
                "a": "block",
                "blocks": {blocker.ref: attacker.ref},
                "pay": "auto",
            },
        )

        self.assertTrue(result.ok, result.summary)
        self.assertTrue(land.tapped)
        self.assertEqual(attacker.object_id, blocker.blocking)

    def test_fixed_attached_block_cost_is_paid_to_block(self):
        session = self.make_combat_session(509010403, players=2)
        engine = session.engine
        attacker = self.creature(
            engine, "A", "Aura Attack", keywords=("Haste",)
        )
        blocker = self.creature(engine, "B", "Enchanted Blocker")
        aura = self.attach_tax(engine, "A", blocker)
        land = self.colorless_land(engine, "B", "Aura Block Source")
        engine.state.phase_index = 6
        engine.state.step = "declare_blockers"
        engine.state.combat = CombatState(
            attackers={attacker.object_id: "B"},
            attackers_declared=True,
            defending_players=["B"],
        )
        attacker.attacking = "B"
        engine._issue_next_blocker()

        payload = engine.state.pending_decision.payload_by_actor["B"]
        self.assertEqual(aura.ref, payload["declaration_costs"][0]["source"])
        result = session.act(
            "pilot:B",
            {
                "a": "block",
                "blocks": {blocker.ref: attacker.ref},
                "pay": "auto",
            },
        )

        self.assertTrue(result.ok, result.summary)
        self.assertTrue(land.tapped)

    def test_broader_conditional_block_cost_stops_fail_closed(self):
        session = self.make_combat_session(509010404, players=2)
        engine = session.engine
        attacker = self.creature(
            engine,
            "A",
            "Large Attacker",
            keywords=("Haste",),
            power="4",
        )
        self.creature(
            engine,
            "B",
            "Conditional Blocker",
            oracle_text=(
                "This creature can't block creatures with power 3 or "
                "greater unless you pay {1}."
            ),
        )
        engine.state.phase_index = 6
        engine.state.step = "declare_blockers"
        engine.state.combat = CombatState(
            attackers={attacker.object_id: "B"},
            attackers_declared=True,
            defending_players=["B"],
        )
        attacker.attacking = "B"

        engine._issue_next_blocker()

        self.assertIsNone(engine.state.pending_decision)
        pause = engine._semantic_pause_annotation()
        self.assertIsNotNone(pause)
        self.assertIn("combat.block_cost", pause["event"])

    def test_sacrificed_mana_source_does_not_become_a_blocker(self):
        session = self.make_combat_session(509010405, players=2)
        engine = session.engine
        attacker = self.creature(
            engine, "A", "Sacrifice Attack", keywords=("Haste",)
        )
        blocker = self.creature(
            engine,
            "B",
            "Sacrificed Blocker",
            oracle_text=(
                "This creature can't block unless you pay {1}.\n"
                "{T}, Sacrifice this creature: Add one mana of any type."
            ),
            keywords=("Haste",),
        )
        engine.state.phase_index = 6
        engine.state.step = "declare_blockers"
        engine.state.combat = CombatState(
            attackers={attacker.object_id: "B"},
            attackers_declared=True,
            defending_players=["B"],
        )
        attacker.attacking = "B"
        engine._issue_next_blocker()

        result = session.act(
            "pilot:B",
            {
                "a": "block",
                "blocks": {blocker.ref: attacker.ref},
                "pay": "auto",
            },
        )

        self.assertTrue(result.ok, result.summary)
        self.assertEqual({}, engine.state.combat.blockers)

    def test_oracle_ir_uses_the_runtime_declaration_cost_grammar(self):
        base = self.db.lookup("Arcum Dagsson")
        exact = replace(
            base,
            type_line="Enchantment",
            oracle_text=(
                "Creatures can't attack you unless their controller pays "
                "{2} for each creature they control that's attacking you."
            ),
        )
        trusted = {"cr-508-declare-attackers-step"}

        ir = compile_oracle_card(exact, trusted_mechanics=trusted)

        self.assertEqual("exact", ir.status)
        node = ir.faces[0].nodes[0]
        self.assertEqual(
            "source-controller-fixed-mana-attack-tax-player-v1",
            node.template_id,
        )
        self.assertEqual({"GENERIC": 2}, node.cost["mana"])

        attached = compile_oracle_card(
            replace(
                exact,
                oracle_text=(
                    "Enchanted creature can't attack or block unless its "
                    "controller pays {3}."
                ),
            ),
            trusted_mechanics={
                "cr-508-declare-attackers-step",
                "cr-509-declare-blockers-step",
            },
        )
        self.assertEqual("exact", attached.status)
        self.assertEqual(
            "attached-fixed-mana-attack-block-cost-v1",
            attached.faces[0].nodes[0].template_id,
        )

        for suffix in (
            ", then draw a card.",
            "",  # The complex symbol alone must remain unresolved.
        ):
            with self.subTest(suffix=suffix):
                oracle = (
                    exact.oracle_text.rstrip(".") + suffix
                    if suffix
                    else exact.oracle_text.replace("{2}", "{W/P}")
                )
                unresolved = compile_oracle_card(
                    replace(exact, oracle_text=oracle),
                    trusted_mechanics=trusted,
                )
                self.assertTrue(unresolved.material_residuals)
                self.assertEqual(
                    "declaration_cost",
                    unresolved.material_residuals[0].kind,
                )


if __name__ == "__main__":
    unittest.main()
