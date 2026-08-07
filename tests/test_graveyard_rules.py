from __future__ import annotations

import copy
import json
import inspect
import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from quorune.engine import StateInvariantError
from quorune.model import StackItem
from quorune.replacement_effects import (
    ReplacementChoiceRequired,
    ReplacementEventBatch,
)
from quorune.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)
from quorune.semantics import SemanticProgram, SemanticRegistry
from quorune.projection import StateProjector
from quorune.semantic_runtime import SemanticNodeError
from quorune.semantic_runtime.zone_replacements import (
    ZoneDestinationReplacementHandler,
    ZoneReplacementError,
    capture_zone_change_replacement_snapshot,
    collect_zone_change_replacement_effects,
    prepare_zone_change_replacement,
    prepare_zone_change_replacement_snapshot,
)


class GraveyardRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_session(self, seed: int, *, players: int = 2):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=players,
            seed=seed,
            auto_pass_empty=False,
        )
        keep_all(session)
        session.engine.permissions.invalidate_current()
        session.engine.state.pending_decision = None
        session.engine.state.priority_player = None
        session.engine.state.priority_passes = []
        return session

    @staticmethod
    def card(engine, owner: str, name: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == owner
            and card.is_card_object
            and card.printed_name == name
        )

    def stage_spell(
        self,
        engine,
        owner: str,
        name: str,
        *,
        ref: str,
    ) -> StackItem:
        card = self.card(engine, owner, name)
        engine._remove_from_zone(card)
        engine._reset_zone_change(card, "stack")
        card.zone = "stack"
        card.controller = owner
        card.known_to = list(engine.seats)
        card.revealed_to = list(engine.seats)
        item = StackItem(
            stack_id=engine._stable_runtime_id("stack", ref),
            ref=ref,
            kind="spell",
            controller=owner,
            label=name,
            card_object_id=card.object_id,
            default_destination=(
                "battlefield"
                if self.db.lookup(name).is_permanent_spell
                else "graveyard"
            ),
            visibility=list(engine.seats),
            context={"dynamic_effects": []},
        )
        engine.state.stack.append(item)
        return item

    def test_contract_traces_every_cr_404_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root / "mechanics" / "contracts" / "graveyard.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {"404", "404.1", "404.2", "404.3"},
            {
                rule_id
                for rule_id in contract["rule_references"]
                if str(rule_id).startswith("404")
            },
        )

    def test_graveyards_start_empty_and_common_causes_use_owner_top(self):
        session = self.make_session(40401, players=4)
        engine = session.engine
        self.assertTrue(
            all(
                not player.zones["graveyard"]
                for player in engine.state.players.values()
            )
        )

        destroyed = self.card(engine, "A", "Sol Ring")
        engine.move_card(
            destroyed.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        engine.apply_effect(
            {
                "op": "destroy",
                "card": destroyed.ref,
                "reason": "CR 404.1 destroy witness",
            },
            actor="B",
        )

        discarded = self.card(engine, "A", "Lightning Greaves")
        engine.move_card(discarded.object_id, "hand", log=False)
        engine.apply_effect(
            {
                "op": "discard",
                "card": discarded.ref,
                "reason": "CR 404.1 discard witness",
            },
            actor="A",
        )

        sacrificed = self.card(engine, "A", "Panharmonicon")
        engine.move_card(
            sacrificed.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        engine.apply_effect(
            {
                "op": "sacrifice",
                "card": sacrificed.ref,
                "reason": "CR 404.1 sacrifice witness",
            },
            actor="A",
        )

        countered_item = self.stage_spell(
            engine,
            "A",
            "Sensei's Divining Top",
            ref="S-404-countered",
        )
        countered = engine.state.cards[countered_item.card_object_id]
        engine._counter_stack_item(
            countered_item.ref,
            reason="CR 404.1 counter witness",
            countered_by="B",
        )

        resolved_item = self.stage_spell(
            engine,
            "A",
            "Chaos Warp",
            ref="S-404-resolved",
        )
        resolved = engine.state.cards[resolved_item.card_object_id]
        engine._begin_resolve_item(
            resolved_item,
            [],
            "graveyard",
            note="CR 404.1 instant resolution witness",
        )

        self.assertEqual(
            [
                destroyed.object_id,
                discarded.object_id,
                sacrificed.object_id,
                countered.object_id,
                resolved.object_id,
            ],
            engine.state.players["A"].zones["graveyard"],
        )
        self.assertTrue(
            all(
                card.zone == "graveyard"
                and card.owner == "A"
                and card.controller == "A"
                for card in (
                    destroyed,
                    discarded,
                    sacrificed,
                    countered,
                    resolved,
                )
            )
        )
        self.assertNotIn(
            destroyed.object_id,
            engine.state.players["B"].zones["graveyard"],
        )

    def test_rules_countered_permanent_spell_uses_graveyard_not_resolution_destination(
        self,
    ):
        session = self.make_session(40402)
        engine = session.engine
        aura = self.card(engine, "B", "Animate Dead")
        creature = self.card(engine, "A", "Goblin Engineer")
        engine.move_card(creature.object_id, "graveyard", log=False)

        item = self.stage_spell(
            engine,
            "B",
            "Animate Dead",
            ref="S-404-aura",
        )
        program = engine.semantics.get(
            f"{aura.oracle_id}:spell:front"
        )
        self.assertIsNotNone(program)
        selected, grouped = engine._validate_semantic_targets(
            "B",
            program,
            [creature.ref],
            source_ref=item.ref,
        )
        item.semantic_key = program.key
        item.targets = selected
        item.context.update(
            {
                "target_groups": grouped,
                "target_snapshots": {
                    creature.ref: engine._target_snapshot(creature.ref)
                },
                "targets_revalidated": False,
            }
        )

        engine.move_card(
            creature.object_id,
            "hand",
            reason="remove the only Aura target",
            log=False,
        )
        engine._prepare_stack_resolution()

        self.assertEqual("graveyard", aura.zone)
        self.assertIn(
            aura.object_id,
            engine.state.players["B"].zones["graveyard"],
        )
        self.assertNotIn(
            aura.object_id,
            engine.state.players["B"].zones["battlefield"],
        )
        counter_event = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "stack.counter"
            and event.details.get("stack") == item.ref
        )
        self.assertEqual("rules", counter_event.details["counter_kind"])
        self.assertEqual(
            "graveyard",
            counter_event.details["destination"],
        )

    def test_graveyard_is_face_up_public_ordered_and_not_reordered_by_same_zone_move(
        self,
    ):
        session = self.make_session(40403, players=4)
        engine = session.engine
        first = self.card(engine, "A", "Sol Ring")
        second = self.card(engine, "A", "Sensei's Divining Top")
        first.face_down = True
        first.known_to = ["A"]
        first.revealed_to = []

        engine.move_card(first.object_id, "graveyard", log=False)
        engine.move_card(second.object_id, "graveyard", log=False)
        before_hash = authoritative_state_hash(engine.state)
        engine.move_card(first.object_id, "graveyard", log=False)

        self.assertEqual(before_hash, authoritative_state_hash(engine.state))
        self.assertFalse(first.face_down)
        self.assertEqual(list(engine.seats), first.known_to)
        self.assertEqual(list(engine.seats), first.revealed_to)
        packet = session.packet("pilot:D", full=True)
        graveyard = packet["state"]["players"]["A"]["gy"]
        self.assertEqual(
            [first.ref, second.ref],
            [item["id"] for item in graveyard],
        )
        self.assertEqual(
            [first.printed_name, second.printed_name],
            [item["n"] for item in graveyard],
        )

    def test_graveyard_owner_index_is_an_authoritative_invariant(self):
        session = self.make_session(40404)
        engine = session.engine
        card = self.card(engine, "A", "Sol Ring")
        engine.move_card(card.object_id, "graveyard", log=False)
        engine.state.players["A"].zones["graveyard"].remove(
            card.object_id
        )
        engine.state.players["B"].zones["graveyard"].append(
            card.object_id
        )

        with self.assertRaisesRegex(
            StateInvariantError,
            "indexed under B but owned by A",
        ):
            engine._assert_invariants()

    def test_graveyard_replacement_is_decided_before_the_move(self):
        session = self.make_session(40405)
        engine = session.engine
        voidwalker = self.card(engine, "B", "Dauthi Voidwalker")
        engine.move_card(
            voidwalker.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        opponent_card = self.card(
            engine,
            "A",
            "Goblin Engineer",
        )

        engine.move_card(
            opponent_card.object_id,
            "graveyard",
            reason="CR 404/614 replacement witness",
            log=False,
        )

        self.assertEqual("exile", opponent_card.zone)
        self.assertNotIn(
            opponent_card.object_id,
            engine.state.players["A"].zones["graveyard"],
        )
        self.assertEqual(1, opponent_card.counters["void"])

        token_ref = engine.create_token(
            "A",
            name="Replacement Witness",
            characteristics={"type_line": "Token Creature"},
        )[0]
        token = next(
            card
            for card in engine.state.cards.values()
            if card.ref == token_ref
        )
        engine.move_card(
            token.object_id,
            "graveyard",
            reason="Dauthi does not replace token movement",
            log=False,
        )
        self.assertEqual("graveyard", token.zone)

    def test_dauthi_does_not_replace_tokens_or_its_controllers_cards(self):
        session = self.make_session(40407)
        engine = session.engine
        voidwalker = self.card(engine, "B", "Dauthi Voidwalker")
        engine.move_card(
            voidwalker.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        own_card = self.card(engine, "B", "Sol Ring")
        engine.move_card(own_card.object_id, "graveyard", log=False)
        token_ref = engine.create_token(
            "A",
            name="Dauthi token witness",
            characteristics={"type_line": "Token Creature"},
        )[0]
        token = next(
            card
            for card in engine.state.cards.values()
            if card.ref == token_ref
        )
        engine.move_card(token.object_id, "graveyard", log=False)

        self.assertEqual("graveyard", own_card.zone)
        self.assertEqual("graveyard", token.zone)
        self.assertNotIn("void", own_card.counters)
        self.assertNotIn("void", token.counters)

    def test_zone_replacement_descriptor_rejects_unknown_destinations(self):
        handler = ZoneDestinationReplacementHandler()
        descriptor = {
            "handler_id": handler.handler_id,
            "schema_version": handler.schema_version,
            "event": handler.event,
            "condition": {
                "destination": "graveyard",
                "object_kind": "card",
                "owner_relation": "opponent",
            },
            "destination": "sideboard",
            "counters": {},
        }

        with self.assertRaisesRegex(SemanticNodeError, "supported game zones"):
            handler.validate(descriptor)

    def test_stack_object_controller_chooses_zone_replacement_order(self):
        session = self.make_session(404071)
        engine = session.engine
        voidwalker = self.card(engine, "B", "Dauthi Voidwalker")
        engine.move_card(
            voidwalker.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        engine.create_token(
            "B",
            name="",
            copy_of=voidwalker.ref,
            reason="stack-controller replacement witness",
        )
        victim = self.card(engine, "A", "Goblin Engineer")
        engine.move_card(victim.object_id, "hand", log=False)
        engine._remove_from_zone(victim)
        engine._reset_zone_change(victim, "stack")
        victim.zone = "stack"
        victim.controller = "B"

        with self.assertRaises(ReplacementChoiceRequired) as required:
            engine.move_card(victim.object_id, "graveyard", log=False)

        self.assertEqual("B", required.exception.pending.choice.chooser)
        self.assertEqual("stack", victim.zone)
        self.assertEqual("B", victim.controller)

    def test_simultaneous_replacement_uses_the_sources_pre_move_controller(self):
        session = self.make_session(40410)
        engine = session.engine
        voidwalker = self.card(engine, "B", "Dauthi Voidwalker")
        engine.move_card(
            voidwalker.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        engine.change_control(
            voidwalker.object_id,
            "A",
            reason="simultaneous replacement LKI witness",
        )
        victim = self.card(engine, "B", "Sol Ring")

        engine._move_cards_simultaneously(
            [
                (voidwalker.object_id, "graveyard"),
                (victim.object_id, "graveyard"),
            ],
            reason="simultaneous replacement LKI witness",
            log=False,
        )

        self.assertEqual("exile", voidwalker.zone)
        self.assertEqual("exile", victim.zone)
        self.assertEqual(1, voidwalker.counters["void"])
        self.assertEqual(1, victim.counters["void"])

    def test_simultaneous_competing_replacements_follow_four_player_apnap(self):
        session = self.make_session(40412, players=4)
        engine = session.engine
        voidwalker = self.card(engine, "B", "Dauthi Voidwalker")
        engine.move_card(
            voidwalker.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        engine.create_token(
            "B",
            name="",
            copy_of=voidwalker.ref,
            reason="four-player replacement ordering witness",
        )
        victim_a = self.card(engine, "A", "Sol Ring")
        victim_c = self.card(engine, "C", "Sol Ring")
        changes = (
            (victim_c.object_id, "graveyard"),
            (victim_a.object_id, "graveyard"),
        )
        before = authoritative_state_hash(engine.state)

        with self.assertRaises(ReplacementChoiceRequired) as first:
            engine._move_cards_simultaneously(
                changes,
                reason="four-player replacement ordering witness",
                log=False,
            )

        self.assertEqual("A", first.exception.pending.choice.chooser)
        self.assertEqual(2, len(first.exception.batch.events))
        self.assertEqual(
            first.exception.batch,
            ReplacementEventBatch.from_dict(
                first.exception.batch.to_dict()
            ),
        )
        self.assertEqual(before, authoritative_state_hash(engine.state))
        first_selection = first.exception.pending.choice.options[0]

        with self.assertRaises(ReplacementChoiceRequired) as second:
            engine._move_cards_simultaneously(
                changes,
                reason="four-player replacement ordering witness",
                log=False,
                replacement_selections=(first_selection,),
            )

        self.assertEqual("C", second.exception.pending.choice.chooser)
        self.assertEqual(before, authoritative_state_hash(engine.state))
        second_selection = second.exception.pending.choice.options[0]
        engine._move_cards_simultaneously(
            changes,
            reason="four-player replacement ordering witness",
            log=False,
            replacement_selections=(first_selection, second_selection),
        )

        self.assertEqual("exile", victim_a.zone)
        self.assertEqual("exile", victim_c.zone)
        self.assertEqual(1, victim_a.counters["void"])
        self.assertEqual(1, victim_c.counters["void"])

    def test_zone_replacement_snapshot_mutant_is_killed(self):
        session = self.make_session(40413, players=4)
        engine = session.engine
        voidwalker = self.card(engine, "B", "Dauthi Voidwalker")
        engine.move_card(
            voidwalker.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        victim = self.card(engine, "A", "Sol Ring")
        victim_origin = victim.zone
        sources = [
            copy.deepcopy(source)
            for source in engine._semantic_event_sources()
        ]
        source_zones = {
            source.object_id: source.zone for source in sources
        }
        snapshot = capture_zone_change_replacement_snapshot(
            engine,
            ((victim.object_id, "graveyard"),),
            sources=sources,
            source_zones=source_zones,
        )
        reordered = capture_zone_change_replacement_snapshot(
            engine,
            ((victim.object_id, "graveyard"),),
            sources=tuple(reversed(sources)),
            source_zones=source_zones,
        )
        self.assertEqual(snapshot, reordered)

        for source in sources:
            source.zone = "outside"
            source.controller = "D"
        prepared = prepare_zone_change_replacement_snapshot(snapshot)

        self.assertEqual(victim_origin, victim.zone)
        self.assertEqual("exile", prepared[victim.object_id].destination)
        self.assertEqual(1, len(prepared[victim.object_id].counter_events))

    def test_zone_replacement_preflight_rejects_malformed_and_stale_moves(self):
        session = self.make_session(40414)
        engine = session.engine
        victim = self.card(engine, "A", "Sol Ring")
        before = authoritative_state_hash(engine.state)

        for changes, message in (
            (
                (
                    (victim.object_id, "graveyard"),
                    (victim.object_id, "exile"),
                ),
                "repeat one object",
            ),
            (((victim.object_id, "sideboard"),), "supported destination"),
            ((("missing-object", "graveyard"),), "unknown object"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(ZoneReplacementError, message):
                    capture_zone_change_replacement_snapshot(engine, changes)
                self.assertEqual(before, authoritative_state_hash(engine.state))

        prepared = prepare_zone_change_replacement(
            engine,
            victim,
            "graveyard",
        )
        stale_card = copy.deepcopy(victim)
        stale_card.zone_change_counter += 1
        with self.assertRaisesRegex(
            ZoneReplacementError,
            "does not match the proposed move",
        ):
            prepare_zone_change_replacement(
                engine,
                stale_card,
                "graveyard",
                prepared=prepared,
            )
        self.assertEqual(before, authoritative_state_hash(engine.state))

    def test_dauthi_replacement_replays_without_oracle_id_dispatch(self):
        session = self.make_session(40408)
        engine = session.engine
        voidwalker = self.card(engine, "B", "Dauthi Voidwalker")
        engine.move_card(
            voidwalker.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        voidwalker.printed_name = "Renamed zone replacement source"
        victim = self.card(engine, "A", "Goblin Engineer")
        program = SemanticProgram(
            key="test:dauthi-zone-replacement-replay",
            label="Move a card to its owner's graveyard",
            effects=[
                {
                    "op": "move",
                    "card": victim.ref,
                    "destination": "graveyard",
                }
            ],
            trust_level="provisional",
        )
        engine.semantics.put(program)
        engine.state.stack.append(
            StackItem(
                stack_id="dauthi-zone-replacement-replay",
                ref="S-dauthi-zone-replacement-replay",
                kind="triggered_ability",
                controller="A",
                label=program.label,
                semantic_key=program.key,
                visibility=["A", "B"],
            )
        )
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine._grant_priority("A")
        engine._issue_priority("A")
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()

        for principal in ("pilot:A", "pilot:B"):
            result = session.act(principal, {"action_id": "pass"})
            self.assertTrue(result.ok, result.summary)

        self.assertEqual("exile", victim.zone)
        self.assertEqual(1, victim.counters["void"])
        replacement_event = next(
            event
            for event in engine.state.events
            if event.code == "replacement.apply"
        )
        self.assertEqual(voidwalker.ref, replacement_event.details["source"])
        self.assertNotIn(
            "f1c2dbe2-fbe0-4058-bdf1-91d1b1832786",
            inspect.getsource(collect_zone_change_replacement_effects),
        )

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "dauthi-replacement-record"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(2, replay["commands"])

    def test_complete_legacy_registry_uses_pinned_zone_compatibility(self):
        with tempfile.TemporaryDirectory() as temporary:
            semantics_path = Path(temporary) / "semantics.json"
            semantics_path.write_text(
                json.dumps(
                    {
                        "schema_version": 3,
                        "include_builtin_packs": False,
                        "programs": {},
                    }
                ),
                encoding="utf-8",
            )
            registry = SemanticRegistry(semantics_path)

        oracle_id = "f1c2dbe2-fbe0-4058-bdf1-91d1b1832786"
        self.assertEqual([], registry.programs_for_oracle(oracle_id))
        programs = registry.runtime_handler_programs_for_oracle(
            oracle_id,
            active_zone="battlefield",
            event="zone.change",
        )
        self.assertEqual(
            [f"{oracle_id}:replacement:graveyard-to-exile"],
            [program.key for program in programs],
        )
        self.assertTrue(
            registry.is_runtime_handler_compatibility_program(programs[0])
        )

        session = self.make_session(40411)
        engine = session.engine
        engine.semantics = registry
        engine._semantic_trust_cache.clear()
        voidwalker = self.card(engine, "B", "Dauthi Voidwalker")
        engine.move_card(
            voidwalker.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        victim = self.card(engine, "A", "Goblin Engineer")
        engine.move_card(victim.object_id, "graveyard", log=False)

        self.assertEqual("exile", victim.zone)
        self.assertEqual(1, victim.counters["void"])

    def test_competing_zone_replacements_suspend_resume_and_replay_exactly(
        self,
    ):
        session = self.make_session(40409)
        engine = session.engine
        voidwalker = self.card(engine, "B", "Dauthi Voidwalker")
        engine.move_card(
            voidwalker.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        copied_source_ref = engine.create_token(
            "B",
            name="",
            copy_of=voidwalker.ref,
            reason="competing zone replacement source",
        )[0]
        victim = self.card(engine, "A", "Goblin Engineer")
        engine.move_card(victim.object_id, "hand", log=False)
        program = SemanticProgram(
            key="test:competing-zone-replacement-replay",
            label="Move a card to its owner's graveyard",
            effects=[
                {
                    "op": "move",
                    "card": victim.ref,
                    "destination": "graveyard",
                }
            ],
            trust_level="provisional",
        )
        engine.semantics.put(program)
        engine.state.stack.append(
            StackItem(
                stack_id="competing-zone-replacement-replay",
                ref="S-competing-zone-replacement-replay",
                kind="triggered_ability",
                controller="A",
                label=program.label,
                semantic_key=program.key,
                visibility=["A", "B"],
            )
        )
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine._grant_priority("A")
        engine._issue_priority("A")
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()

        for principal in ("pilot:A", "pilot:B"):
            result = session.act(principal, {"action_id": "pass"})
            self.assertTrue(result.ok, result.summary)

        decision = engine.state.pending_decision
        self.assertIsNotNone(decision)
        self.assertEqual("replacement.order", decision.kind)
        self.assertEqual(["A"], decision.actors)
        projector = StateProjector(self.db, engine.state)
        projected_a = projector._decision("pilot:A")
        projected_b = projector._decision("pilot:B")
        self.assertIsNotNone(projected_a)
        self.assertIsNone(projected_b)
        self.assertNotIn("replacement_batch", json.dumps(projected_a))
        self.assertNotIn("replacement_effects", json.dumps(projected_a))
        options = projected_a["ctx"]["options"]
        self.assertEqual(2, len(options))
        selected = options[0]["id"]

        result = session.act(
            "pilot:A",
            {
                "action_id": "choose",
                "replacement": selected,
            },
        )

        self.assertTrue(result.ok, result.summary)
        self.assertEqual("exile", victim.zone)
        self.assertEqual(1, victim.counters["void"])
        self.assertNotIn(
            victim.object_id,
            engine.state.players["A"].zones["graveyard"],
        )
        replacement_event = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "replacement.apply"
            and event.details.get("object") == victim.ref
        )
        self.assertIn(
            replacement_event.details["source"],
            {voidwalker.ref, copied_source_ref},
        )

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "replacement-choice-record"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(3, replay["commands"])

    def test_simultaneous_same_owner_order_is_still_caller_determined(self):
        session = self.make_session(40406)
        engine = session.engine
        first = self.card(engine, "A", "Sol Ring")
        second = self.card(engine, "A", "Sensei's Divining Top")

        engine._move_cards_simultaneously(
            [
                (second.object_id, "graveyard"),
                (first.object_id, "graveyard"),
            ],
            reason="CR 404.3 blocked ordering witness",
            log=False,
        )

        self.assertEqual(
            [second.object_id, first.object_id],
            engine.state.players["A"].zones["graveyard"],
        )
        self.assertIsNone(engine.state.pending_decision)


if __name__ == "__main__":
    unittest.main()
