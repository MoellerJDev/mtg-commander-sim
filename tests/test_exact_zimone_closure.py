from __future__ import annotations

import unittest
from types import SimpleNamespace

from common import keep_all, load_assets, make_session
from mtg_commander_sim.model import CombatState, StackItem
from mtg_commander_sim.preflight import card_semantic_status
from mtg_commander_sim.targets import TargetGroup


class ExactZimoneClosureTests(unittest.TestCase):
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

    def prepare_main(self, engine, seat: str) -> None:
        engine.state.active_player = seat
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.stack.clear()
        engine.state.priority_player = seat

    def test_diabolic_intent_requires_and_pays_creature_sacrifice(self):
        session = self.make_session(1000)
        engine = session.engine
        intent = self.card(engine, "B", "Diabolic Intent")
        creature = self.card(engine, "B", "Birds of Paradise")
        engine.move_card(intent.object_id, "hand")
        engine.move_card(creature.object_id, "battlefield", controller="B")
        self.prepare_main(engine, "B")
        engine.state.players["B"].mana_pool.update({"B": 1, "C": 1})

        hints = engine._priority_action_hints("B")
        option = hints["actions"][
            next(
                index
                for index, action in enumerate(hints["actions"])
                if action["id"] == f"cast:{intent.ref}"
            )
        ]["cost_options"][0]
        self.assertIn(
            creature.ref,
            option["choice_schema"]["sacrifice_cards"]["legal_refs"],
        )

        engine._cast(
            "B",
            {
                "card": intent.ref,
                "sacrifice_cards": [creature.ref],
                "pay": "manual",
                "payment": {"B": 1, "C": 1},
            },
        )
        self.assertEqual("graveyard", creature.zone)
        self.resolve_top(engine)
        self.assertEqual("semantic.search", engine.state.pending_decision.kind)

    def test_reclaimer_threshold_and_exact_land_search_cost(self):
        session = self.make_session(1001)
        engine = session.engine
        reclaimer = self.card(engine, "B", "Elvish Reclaimer")
        sacrificed = self.card(engine, "B", "Island")
        searched = self.card(engine, "B", "Boseiju, Who Endures")
        graveyard_lands = [
            self.card(engine, "B", name)
            for name in ("Bayou", "Breeding Pool", "Command Tower")
        ]
        engine.move_card(reclaimer.object_id, "battlefield", controller="B")
        reclaimer.acquired_control_turn_count = -1
        engine.move_card(sacrificed.object_id, "battlefield", controller="B")
        engine.move_card(searched.object_id, "library")
        for land in graveyard_lands:
            engine.move_card(land.object_id, "graveyard")
        self.assertEqual("3", engine._effective_card_data(reclaimer)["power"])
        self.assertEqual(
            "4", engine._effective_card_data(reclaimer)["toughness"]
        )

        engine.state.players["B"].mana_pool["C"] = 2
        engine.state.priority_player = "B"
        engine._activate(
            "B",
            {
                "source": reclaimer.ref,
                "ability": "ab2",
                "cost_cards": [sacrificed.ref],
                "pay": "manual",
                "payment": {"C": 2},
            },
        )
        self.assertEqual("graveyard", sacrificed.zone)
        self.resolve_top(engine)
        self.assertEqual("semantic.search", engine.state.pending_decision.kind)

    def test_wight_counts_graveyard_creatures_and_searches_land(self):
        session = self.make_session(1002)
        engine = session.engine
        wight = self.card(engine, "B", "Wight of the Reliquary")
        sacrifice = self.card(engine, "B", "Birds of Paradise")
        grave_creature = self.card(engine, "B", "Elves of Deep Shadow")
        engine.move_card(wight.object_id, "battlefield", controller="B")
        wight.acquired_control_turn_count = -1
        engine.move_card(sacrifice.object_id, "battlefield", controller="B")
        engine.move_card(grave_creature.object_id, "graveyard")
        self.assertEqual("3", engine._effective_card_data(wight)["power"])
        self.assertEqual("3", engine._effective_card_data(wight)["toughness"])

        engine.state.priority_player = "B"
        engine._activate(
            "B",
            {
                "source": wight.ref,
                "ability": "ab3",
                "cost_cards": [sacrifice.ref],
            },
        )
        self.assertEqual("graveyard", sacrifice.zone)
        self.resolve_top(engine)
        self.assertEqual("semantic.search", engine.state.pending_decision.kind)

    def test_gravecrawler_graveyard_cast_requires_controlled_zombie(self):
        session = self.make_session(1003)
        engine = session.engine
        gravecrawler = self.card(engine, "B", "Gravecrawler")
        zombie = self.card(engine, "B", "Wight of the Reliquary")
        engine.move_card(gravecrawler.object_id, "graveyard")
        self.prepare_main(engine, "B")
        engine.state.players["B"].mana_pool["B"] = 1

        self.assertNotIn(
            gravecrawler.ref,
            engine._priority_action_hints("B")["cast"],
        )
        engine.move_card(zombie.object_id, "battlefield", controller="B")
        self.assertIn(
            gravecrawler.ref,
            engine._priority_action_hints("B")["cast"],
        )
        engine._cast(
            "B",
            {
                "card": gravecrawler.ref,
                "from": "graveyard",
                "pay": "manual",
                "payment": {"B": 1},
            },
        )
        self.assertEqual("stack", gravecrawler.zone)
        self.resolve_top(engine)
        self.assertEqual("battlefield", gravecrawler.zone)

    def test_promoted_exact_cards_preflight_fully(self):
        for name in (
            "Diabolic Intent",
            "Archway of Innovation",
            "Dauthi Voidwalker",
            "Elvish Reclaimer",
            "Endurance",
            "Faerie Mastermind",
            "Gravecrawler",
            "Insidious Roots",
            "Intruder Alarm",
            "Mole Man, Moloid Master",
            "Mistrise Village",
            "Retreat to Coralhelm",
            "Scryb Ranger",
            "Seedborn Muse",
            "Shifting Woodland",
            "Spelunking",
            "Thornbite Staff",
            "Wight of the Reliquary",
            "Veil of Summer",
        ):
            with self.subTest(card=name):
                row = card_semantic_status(
                    self.db.lookup(name),
                    self.make_session(1004).engine.semantics,
                    db=self.db,
                )
                self.assertEqual("fully_playable", row["status"], row)

    def test_dauthi_replaces_graveyard_moves_and_casts_opponent_card_for_free(
        self,
    ):
        session = self.make_session(1019)
        engine = session.engine
        dauthi = self.card(engine, "B", "Dauthi Voidwalker")
        opponent_spell = self.card(engine, "A", "Sol Ring")
        engine.move_card(dauthi.object_id, "battlefield", controller="B")
        dauthi.acquired_control_turn_count = -1

        engine.move_card(
            opponent_spell.object_id,
            "graveyard",
            reason="test discard",
            semantic_events=True,
        )
        self.assertEqual("exile", opponent_spell.zone)
        self.assertEqual(1, opponent_spell.counters.get("void"))
        self.assertFalse(
            any(
                event.code == "permanent.dies"
                and event.details.get("object") == opponent_spell.ref
                for event in engine.state.events
            )
        )

        engine.state.priority_player = "B"
        engine._activate(
            "B",
            {
                "source": dauthi.ref,
                "ability": "ab3",
                "targets": [opponent_spell.ref],
            },
        )
        self.assertEqual("graveyard", dauthi.zone)
        self.resolve_top(engine)

        self.prepare_main(engine, "B")
        action = next(
            action
            for action in engine._priority_action_hints("B")["actions"]
            if action["id"] == f"cast:{opponent_spell.ref}"
        )
        self.assertEqual("exile", action["from"])
        self.assertEqual(
            "without_mana_cost",
            action["cost_options"][0]["id"],
        )
        engine._cast(
            "B",
            {
                "card": opponent_spell.ref,
                "from": "exile",
                "cost_option": "without_mana_cost",
                "pay": "manual",
                "payment": {},
            },
        )
        self.assertEqual("stack", opponent_spell.zone)
        self.assertEqual("B", engine.state.stack[-1].controller)
        self.resolve_top(engine)
        self.assertEqual("battlefield", opponent_spell.zone)
        self.assertEqual("B", opponent_spell.controller)
        self.assertNotIn(
            "temporary_play_permission",
            opponent_spell.annotations,
        )

    def test_endurance_evoke_exiles_green_card_shuffles_target_and_sacrifices(
        self,
    ):
        session = self.make_session(1018)
        engine = session.engine
        endurance = self.card(engine, "B", "Endurance")
        green_card = self.card(engine, "B", "Birds of Paradise")
        grave_one = self.card(engine, "A", "Sol Ring")
        grave_two = self.card(engine, "A", "Panharmonicon")
        engine.move_card(endurance.object_id, "hand")
        engine.move_card(green_card.object_id, "hand")
        engine.move_card(grave_one.object_id, "graveyard")
        engine.move_card(grave_two.object_id, "graveyard")
        engine.state.priority_player = "B"

        action = next(
            action
            for action in engine._priority_action_hints("B")["actions"]
            if action["id"] == f"cast:{endurance.ref}"
        )
        evoke = next(
            option
            for option in action["cost_options"]
            if option["id"] == "evoke"
        )
        self.assertIn(
            green_card.ref,
            evoke["choice_schema"]["exile_card"]["legal_refs"],
        )
        engine._cast(
            "B",
            {
                "card": endurance.ref,
                "cost_option": "evoke",
                "exile_card": green_card.ref,
                "pay": "manual",
                "payment": {},
            },
        )
        self.assertEqual("exile", green_card.zone)
        self.resolve_top(engine)
        self.assertEqual("trigger.order", engine.state.pending_decision.kind)
        triggers = engine.state.pending_decision.payload_by_actor["B"][
            "triggers"
        ]
        enter_ref = next(
            value["id"]
            for value in triggers
            if value["label"] == "Endurance enter trigger"
        )
        evoke_ref = next(
            value["id"]
            for value in triggers
            if "evoke sacrifice" in value["label"]
        )
        result = session.act(
            "pilot:B",
            {
                "action_id": "order",
                "order": [evoke_ref, enter_ref],
                "plan": "RESOLVE_TRIGGERS",
                "reason": "Put the graveyard trigger above evoke.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual("semantic.target", engine.state.pending_decision.kind)
        result = session.act(
            "pilot:B",
            {
                "action_id": "choose",
                "targets": ["A"],
                "plan": "DISRUPT_GRAVEYARD",
                "reason": "Put the opponent's graveyard on the bottom.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.resolve_top(engine)
        self.assertFalse(engine.state.players["A"].zones["graveyard"])
        self.resolve_top(engine)
        self.assertEqual("graveyard", endurance.zone)

    def test_thornbite_staff_grants_damage_death_untap_and_shaman_attach(
        self,
    ):
        session = self.make_session(1017)
        engine = session.engine
        staff = self.card(engine, "B", "Thornbite Staff")
        shaman = self.card(engine, "B", "Deathrite Shaman")
        victim = self.card(engine, "B", "Birds of Paradise")
        engine.move_card(staff.object_id, "battlefield", controller="B")
        engine.move_card(
            shaman.object_id,
            "battlefield",
            controller="B",
            semantic_events=True,
        )
        self.assertFalse(engine._stabilize())
        self.resolve_top(engine)
        result = session.act(
            "pilot:B",
            {
                "action_id": "choose",
                "choice": "attach",
                "plan": "BUILD_ENGINE",
                "reason": "Attach the Staff to the entering Shaman.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(shaman.object_id, staff.attached_to)

        granted = next(
            ability
            for ability in engine._activated_abilities(shaman)
            if "deals 1 damage to any target"
            in ability.effect_text.casefold()
        )
        shaman.acquired_control_turn_count = -1
        before_life = engine.state.players["A"].life
        engine.state.players["B"].mana_pool["C"] = 2
        engine.state.priority_player = "B"
        engine._activate(
            "B",
            {
                "source": shaman.ref,
                "ability": granted.ability_id,
                "targets": ["A"],
                "pay": "manual",
                "payment": {"C": 2},
            },
        )
        self.resolve_top(engine)
        self.assertEqual(before_life - 1, engine.state.players["A"].life)
        self.assertTrue(shaman.tapped)

        engine.move_card(victim.object_id, "battlefield", controller="B")
        engine.move_card(
            victim.object_id,
            "graveyard",
            reason="test creature death",
            semantic_events=True,
        )
        self.assertFalse(engine._stabilize())
        self.resolve_top(engine)
        self.assertFalse(shaman.tapped)

    def test_veil_draws_from_prior_opponent_color_and_protects_targets(
        self,
    ):
        session = self.make_session(1014)
        engine = session.engine
        veil = self.card(engine, "B", "Veil of Summer")
        blue_source = self.card(engine, "A", "Emry, Lurker of the Loch")
        protected = self.card(engine, "B", "Birds of Paradise")
        engine.move_card(protected.object_id, "battlefield", controller="B")
        engine._log(
            "A",
            "stack.cast",
            "A cast a blue spell.",
            {
                "object": blue_source.ref,
                "colors": ["U"],
            },
        )
        before_hand = len(engine.state.players["B"].zones["hand"])
        engine._remove_from_zone(veil)
        veil.zone = "stack"
        item = StackItem(
            stack_id="veil-test",
            ref="S-veil",
            kind="spell",
            controller="B",
            label=veil.printed_name,
            card_object_id=veil.object_id,
            semantic_key=f"{veil.oracle_id}:spell:front",
            default_destination="graveyard",
            visibility=list(engine.seats),
        )
        engine.state.stack.append(item)
        self.resolve_top(engine)
        self.assertEqual(
            before_hand + 1,
            len(engine.state.players["B"].zones["hand"]),
        )
        engine.move_card(
            blue_source.object_id,
            "battlefield",
            controller="A",
        )
        group = TargetGroup.from_mapping(
            {
                "zones": ["battlefield"],
                "categories": ["permanent"],
                "count": 1,
            }
        )
        self.assertNotIn(
            protected.ref,
            engine._target_candidates(
                "A",
                group,
                source_ref=blue_source.ref,
            ),
        )
        test_stack = StackItem(
            stack_id="protected-spell",
            ref="S-protected",
            kind="spell",
            controller="B",
            label="Protected spell",
            visibility=list(engine.seats),
        )
        self.assertFalse(engine._stack_item_can_be_countered(test_stack))

    def test_shifting_woodland_requires_delirium_and_restores_copy(self):
        session = self.make_session(1015)
        engine = session.engine
        woodland = self.card(engine, "B", "Shifting Woodland")
        target = self.card(engine, "B", "Birds of Paradise")
        instant = self.card(engine, "B", "Veil of Summer")
        artifact = self.card(engine, "B", "Sol Ring")
        land = self.card(engine, "B", "Island")
        engine.move_card(
            woodland.object_id, "battlefield", controller="B"
        )
        engine.move_card(target.object_id, "graveyard")
        ability = next(
            ability
            for ability in engine._activated_abilities(woodland)
            if ability.ability_id == "ab3"
        )
        self.assertEqual(
            ("unavailable", "requires_delirium"),
            engine._ability_availability("B", woodland, ability),
        )
        for card in (instant, artifact, land):
            engine.move_card(card.object_id, "graveyard")
        engine.state.players["B"].mana_pool.update({"C": 2, "G": 2})
        engine.state.priority_player = "B"
        engine._activate(
            "B",
            {
                "source": woodland.ref,
                "ability": "ab3",
                "targets": [target.ref],
                "pay": "manual",
                "payment": {"C": 2, "G": 2},
            },
        )
        self.resolve_top(engine)
        self.assertEqual(
            "Birds of Paradise",
            engine._effective_card_data(woodland)["name"],
        )
        engine._finish_cleanup()
        self.assertEqual(
            "Shifting Woodland",
            engine._effective_card_data(woodland)["name"],
        )

    def test_insidious_roots_batches_graveyard_departures_and_grants_token_mana(
        self,
    ):
        session = self.make_session(1016)
        engine = session.engine
        roots = self.card(engine, "B", "Insidious Roots")
        first = self.card(engine, "B", "Birds of Paradise")
        second = self.card(engine, "B", "Elves of Deep Shadow")
        engine.move_card(roots.object_id, "battlefield", controller="B")
        engine.move_card(first.object_id, "graveyard")
        engine.move_card(second.object_id, "graveyard")

        engine._move_cards_simultaneously(
            [
                (first.object_id, "exile"),
                (second.object_id, "hand"),
            ],
            reason="test simultaneous graveyard departure",
        )
        self.assertFalse(engine._stabilize())
        self.assertEqual(1, len(engine.state.stack))
        self.resolve_top(engine)
        plants = [
            card
            for card in engine.state.cards.values()
            if card.is_token
            and card.controller == "B"
            and card.printed_name == "Plant"
            and card.zone == "battlefield"
        ]
        self.assertEqual(1, len(plants))
        self.assertEqual(1, plants[0].counters["+1/+1"])
        plants[0].acquired_control_turn_count = -1
        source = next(
            source
            for source in engine.available_mana_sources("B")
            if source.ref == plants[0].ref
        )
        self.assertEqual(
            {"W", "U", "B", "R", "G"},
            {
                color
                for mode in source.modes
                for color, amount in mode.bundle.items()
                if amount
            },
        )
        engine._activate_mana_plan(
            "B",
            [{"source": plants[0].ref, "bundle": {"G": 1}}],
        )
        self.assertTrue(plants[0].tapped)
        self.assertEqual(1, engine.state.players["B"].mana_pool["G"])

    def test_mistrise_marks_only_the_next_spell_uncounterable(self):
        session = self.make_session(1010)
        engine = session.engine
        village = self.card(engine, "B", "Mistrise Village")
        spell = self.card(engine, "B", "Sol Ring")
        engine.move_card(village.object_id, "battlefield", controller="B")
        engine.move_card(spell.object_id, "hand")
        engine.state.players["B"].mana_pool["U"] = 1
        engine.state.priority_player = "B"
        engine._activate(
            "B",
            {
                "source": village.ref,
                "ability": "ab3",
                "pay": "manual",
                "payment": {"U": 1},
            },
        )
        self.resolve_top(engine)
        self.assertTrue(
            engine.state.players["B"].stats["next_spell_uncounterable"]
        )

        self.prepare_main(engine, "B")
        engine.state.players["B"].mana_pool["C"] = 1
        engine._cast(
            "B",
            {
                "card": spell.ref,
                "pay": "manual",
                "payment": {"C": 1},
            },
        )
        item = engine.state.stack[-1]
        self.assertTrue(item.context["cant_be_countered"])
        self.assertNotIn(
            "next_spell_uncounterable",
            engine.state.players["B"].stats,
        )
        engine._counter_stack_item(
            item.ref,
            reason="test counter",
            countered_by="A",
        )
        self.assertIn(item, engine.state.stack)

    def test_archway_grants_improvise_to_exactly_the_next_spell(self):
        session = self.make_session(1011)
        engine = session.engine
        archway = self.card(engine, "A", "Archway of Innovation")
        artifact = self.card(engine, "A", "Lightning Greaves")
        spell = self.card(engine, "A", "Panharmonicon")
        engine.move_card(archway.object_id, "battlefield", controller="A")
        engine.move_card(artifact.object_id, "battlefield", controller="A")
        engine.move_card(spell.object_id, "hand")
        engine.state.players["A"].mana_pool["U"] = 1
        engine.state.priority_player = "A"
        engine._activate(
            "A",
            {
                "source": archway.ref,
                "ability": "ab3",
                "pay": "manual",
                "payment": {"U": 1},
            },
        )
        self.resolve_top(engine)

        self.prepare_main(engine, "A")
        engine.state.players["A"].mana_pool["C"] = 3
        action = next(
            action
            for action in engine._priority_action_hints("A")["actions"]
            if action["id"] == f"cast:{spell.ref}"
        )
        option = action["cost_options"][0]
        self.assertIn(
            artifact.ref,
            option["choice_schema"]["improvise_cards"]["legal_refs"],
        )
        engine._cast(
            "A",
            {
                "card": spell.ref,
                "improvise_cards": [artifact.ref],
                "pay": "manual",
                "payment": {"C": 3},
            },
        )
        self.assertTrue(artifact.tapped)
        self.assertTrue(engine.state.stack[-1].context["granted_improvise"])
        self.assertNotIn(
            "next_spell_improvise",
            engine.state.players["A"].stats,
        )

    def test_retreat_landfall_exposes_tap_untap_decline_and_scry_modes(
        self,
    ):
        session = self.make_session(1012)
        engine = session.engine
        retreat = self.card(engine, "B", "Retreat to Coralhelm")
        land = self.card(engine, "B", "Island")
        creature = self.card(engine, "B", "Birds of Paradise")
        engine.move_card(retreat.object_id, "battlefield", controller="B")
        engine.move_card(
            creature.object_id, "battlefield", controller="B"
        )
        engine.move_card(
            land.object_id,
            "battlefield",
            controller="B",
            semantic_events=True,
        )
        self.assertTrue(engine._stabilize())
        schema = engine.state.pending_decision.payload_by_actor["B"][
            "target_schema"
        ]
        self.assertEqual(
            {"tap", "untap", "leave", "scry"},
            set(schema["legal_modes"]),
        )
        result = session.act(
            "pilot:B",
            {
                "action_id": "choose",
                "modes": ["scry"],
                "targets": [],
                "plan": "FILTER_DRAW",
                "reason": "Use the scry mode.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.resolve_top(engine)
        self.assertEqual("semantic.choice", engine.state.pending_decision.kind)
        result = session.act(
            "pilot:B",
            {
                "action_id": "choose",
                "cards": [],
                "plan": "KEEP_TOP",
                "reason": "Keep the looked-at card on top.",
            },
        )
        self.assertTrue(result.ok, result.summary)

    def test_scryb_ranger_returns_forest_and_enforces_once_each_turn(self):
        session = self.make_session(1013)
        engine = session.engine
        ranger = self.card(engine, "B", "Scryb Ranger")
        forest = self.card(engine, "B", "Bayou")
        target = self.card(engine, "B", "Birds of Paradise")
        for card in (ranger, forest, target):
            engine.move_card(card.object_id, "battlefield", controller="B")
        target.tapped = True
        engine.state.priority_player = "B"

        engine._activate(
            "B",
            {
                "source": ranger.ref,
                "ability": "ab3",
                "targets": [target.ref],
                "cost_cards": [forest.ref],
            },
        )
        self.assertEqual("hand", forest.zone)
        self.assertEqual(
            ("unavailable", "already_activated_this_turn"),
            engine._ability_availability(
                "B",
                ranger,
                next(
                    ability
                    for ability in engine._activated_abilities(ranger)
                    if ability.ability_id == "ab3"
                ),
            ),
        )
        self.resolve_top(engine)
        self.assertFalse(target.tapped)

    def test_faerie_mastermind_tracks_opponent_second_draw_and_draws_each_player(
        self,
    ):
        session = self.make_session(1005)
        engine = session.engine
        faerie = self.card(engine, "B", "Faerie Mastermind")
        engine.move_card(faerie.object_id, "battlefield", controller="B")
        engine.state.players["A"].stats["cards_drawn_by_turn"] = {}
        before_b = len(engine.state.players["B"].zones["hand"])

        engine.draw("A", 1, reason="first draw")
        self.assertFalse(engine.state.pending_trigger_batches)
        engine.draw("A", 1, reason="second draw")
        self.assertFalse(engine._stabilize())
        self.resolve_top(engine)
        self.assertEqual(
            before_b + 1,
            len(engine.state.players["B"].zones["hand"]),
        )

        engine.state.players["A"].stats["cards_drawn_by_turn"] = {}
        engine.state.players["B"].stats["cards_drawn_by_turn"] = {}
        before = {
            seat: len(engine.state.players[seat].zones["hand"])
            for seat in ("A", "B")
        }
        engine.state.players["B"].mana_pool.update({"U": 1, "C": 3})
        engine.state.priority_player = "B"
        engine._activate(
            "B",
            {
                "source": faerie.ref,
                "ability": "ab4",
                "pay": "manual",
                "payment": {"U": 1, "C": 3},
            },
        )
        self.resolve_top(engine)
        for seat in ("A", "B"):
            self.assertEqual(
                before[seat] + 1,
                len(engine.state.players[seat].zones["hand"]),
            )

    def test_intruder_alarm_suppresses_controller_untap_and_untaps_on_entry(
        self,
    ):
        session = self.make_session(1006)
        engine = session.engine
        alarm = self.card(engine, "B", "Intruder Alarm")
        own_creature = self.card(engine, "B", "Birds of Paradise")
        other_creature = self.card(engine, "A", "Arcum Dagsson")
        entering = self.card(engine, "B", "Elves of Deep Shadow")
        engine.move_card(alarm.object_id, "battlefield", controller="B")
        engine.move_card(
            own_creature.object_id, "battlefield", controller="B"
        )
        engine.move_card(
            other_creature.object_id, "battlefield", controller="A"
        )
        own_creature.tapped = True
        other_creature.tapped = True

        engine.state.active_player = "B"
        engine.state.phase_index = 0
        engine._enter_step()
        self.assertTrue(own_creature.tapped)

        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.move_card(
            entering.object_id,
            "battlefield",
            controller="B",
            semantic_events=True,
        )
        self.assertFalse(engine._stabilize())
        self.resolve_top(engine)
        self.assertFalse(own_creature.tapped)
        self.assertFalse(other_creature.tapped)

    def test_seedborn_muse_untaps_all_permanents_on_opponent_untap(self):
        session = self.make_session(1007)
        engine = session.engine
        muse = self.card(engine, "B", "Seedborn Muse")
        creature = self.card(engine, "B", "Birds of Paradise")
        land = self.card(engine, "B", "Island")
        for card in (muse, creature, land):
            engine.move_card(card.object_id, "battlefield", controller="B")
            card.tapped = True
        engine.state.active_player = "A"
        engine.state.phase_index = 0

        engine._enter_step()

        self.assertFalse(muse.tapped)
        self.assertFalse(creature.tapped)
        self.assertFalse(land.tapped)

    def test_spelunking_draws_puts_optional_land_and_forces_untapped_entry(
        self,
    ):
        session = self.make_session(1008)
        engine = session.engine
        spelunking = self.card(engine, "B", "Spelunking")
        bog = self.card(engine, "B", "Bojuka Bog")
        engine.move_card(bog.object_id, "hand")
        before_hand = len(engine.state.players["B"].zones["hand"])
        engine.move_card(
            spelunking.object_id,
            "battlefield",
            controller="B",
            semantic_events=True,
        )
        self.assertFalse(engine._stabilize())
        self.resolve_top(engine)
        self.assertEqual(
            before_hand + 1,
            len(engine.state.players["B"].zones["hand"]),
        )
        result = session.act(
            "pilot:B",
            {
                "action_id": "choose",
                "card": bog.ref,
                "plan": "DEVELOP_MANA",
                "reason": "Put the optional land onto the battlefield.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual("battlefield", bog.zone)
        self.assertFalse(bog.tapped)
        self.assertFalse(
            engine._land_enters_tapped("B", self.db.lookup("Bojuka Bog"))
        )

    def test_mole_man_plays_graveyard_land_and_moloid_attack_may_mill(
        self,
    ):
        session = self.make_session(1009)
        engine = session.engine
        mole = self.card(engine, "B", "Mole Man, Moloid Master")
        land = self.card(engine, "B", "Island")
        engine.move_card(mole.object_id, "battlefield", controller="B")
        engine.move_card(land.object_id, "graveyard")
        self.prepare_main(engine, "B")
        engine.state.players["B"].land_plays_remaining = 1

        self.assertIn(land.ref, engine._priority_action_hints("B")["lands"])
        engine._play_land("B", {"card": land.ref, "from": "graveyard"})
        self.assertFalse(engine._stabilize())
        self.resolve_top(engine)
        moloid = next(
            card
            for card in engine.state.cards.values()
            if card.is_token
            and card.controller == "B"
            and card.printed_name == "Moloid"
            and card.zone == "battlefield"
        )
        moloid.acquired_control_turn_count = -1

        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.state.active_player = "B"
        engine.state.combat = CombatState()
        before_graveyard = len(engine.state.players["B"].zones["graveyard"])
        engine._complete_attackers(
            SimpleNamespace(
                actors=["B"],
                responses={
                    "B": {"attackers": {moloid.ref: "A"}}
                },
            )
        )
        self.assertFalse(engine._stabilize())
        self.resolve_top(engine)
        result = session.act(
            "pilot:B",
            {
                "action_id": "choose",
                "choice": "mill",
                "plan": "FILL_GRAVEYARD",
                "reason": "Use the optional Moloid mill.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(
            before_graveyard + 1,
            len(engine.state.players["B"].zones["graveyard"]),
        )


if __name__ == "__main__":
    unittest.main()
