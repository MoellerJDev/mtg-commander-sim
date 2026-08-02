from __future__ import annotations

import json
from pathlib import Path
import random
import tempfile
import unittest

from common import ROOT, keep_all, make_session
from scripts.build_test_database import build_fixture_database
from mtg_commander_sim.carddb import CardDatabase
from mtg_commander_sim.damage import (
    commit_prepared_damage_batch,
    damage_proposal,
    DamageEvent,
    DamageError,
    DamageRecipientSnapshot,
    prepare_damage_batch,
)
from mtg_commander_sim.deck import DeckLoader
from mtg_commander_sim.engine import GameRuleError
from mtg_commander_sim.model import CardInstance, StackItem
from mtg_commander_sim.projection import StateProjector
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)
from mtg_commander_sim.replacement_effects import (
    ReplacementChoiceRequired,
    resolve_replacements,
)
from mtg_commander_sim.semantic_runtime import (
    DamageQuantityReplacementHandler,
    DamageReplacementSourceContext,
    FixedDamagePreventionHandler,
    SemanticNodeError,
    default_damage_replacement_registry,
)
from mtg_commander_sim.semantics import SemanticProgram


def damage_condition(
    *,
    source_controller_relation: str = "any",
    target_controller_relation: str = "any",
    target_kinds: list[str] | None = None,
    source_types_all: list[str] | None = None,
    target_types_all: list[str] | None = None,
    combat: bool | None = None,
) -> dict:
    return {
        "source_controller_relation": source_controller_relation,
        "target_controller_relation": target_controller_relation,
        "target_kinds": list(target_kinds or []),
        "source_types_all": list(source_types_all or []),
        "target_types_all": list(target_types_all or []),
        "combat": combat,
    }


def quantity_descriptor(
    *,
    multiplier: int = 2,
    additional: int = 0,
    condition: dict | None = None,
) -> dict:
    return {
        "handler_id": "replacement.damage.quantity.v1",
        "schema_version": 1,
        "event": "damage",
        "condition": condition or damage_condition(),
        "modification": {
            "multiplier": multiplier,
            "additional": additional,
        },
    }


def prevention_descriptor(
    *,
    amount: int = 1,
    condition: dict | None = None,
) -> dict:
    return {
        "handler_id": "prevention.damage.fixed.v1",
        "schema_version": 1,
        "event": "damage",
        "condition": condition or damage_condition(),
        "modification": {"amount": amount},
    }


class DamageReplacementPipelineTests(unittest.TestCase):
    """CR 120.4b/614/615/616 typed damage transaction witnesses."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        database = Path(cls.temporary.name) / "damage-replacements.sqlite3"
        build_fixture_database(
            [
                ROOT / "tests" / "fixtures" / "scryfall-exact-lists.json",
                ROOT
                / "tests"
                / "fixtures"
                / "damage-replacement-cards.json",
            ],
            database,
        )
        cls.db = CardDatabase(database)
        loader = DeckLoader(cls.db)
        cls.mishra = loader.load(
            ROOT / "examples" / "mishra-eminent-one.txt",
            commander="Mishra, Eminent One",
            deck_name="Mishra",
        )
        cls.zimone = loader.load(
            ROOT / "examples" / "zimone-and-dina.txt",
            commander="Zimone and Dina",
            deck_name="Zimone",
        )

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls.temporary.cleanup()

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
        engine.state.priority_player = None
        engine.state.priority_passes = []
        session.commands.clear()
        session.decisions.clear()
        return session

    def add_permanent(
        self,
        engine,
        *,
        seat: str,
        name: str,
        ref: str,
    ) -> CardInstance:
        record = self.db.lookup(name)
        card = CardInstance(
            object_id=f"fixture:{ref}",
            ref=ref,
            oracle_id=record.oracle_id,
            printed_name=record.name,
            owner=seat,
            controller=seat,
            zone="battlefield",
            zone_timestamp=engine.state.event_sequence + 1,
            known_to=list(engine.seats),
            revealed_to=list(engine.seats),
        )
        engine.state.cards[card.object_id] = card
        engine.state.players[seat].zones["battlefield"].append(card.object_id)
        return card

    def stage_sources(self, engine):
        furnace = self.add_permanent(
            engine,
            seat="A",
            name="Furnace of Rath",
            ref="a-furnace",
        )
        defender = self.add_permanent(
            engine,
            seat="B",
            name="Daunting Defender",
            ref="b-defender",
        )
        # Keep this witness on the battlefield after Furnace raises the final
        # damage amount above Daunting Defender's printed toughness.
        defender.counters["+1/+1"] = 5
        source = self.add_permanent(
            engine,
            seat="A",
            name="Mishra, Eminent One",
            ref="a-source",
        )
        return furnace, defender, source

    def proposal(
        self,
        engine,
        *,
        source: CardInstance,
        target: CardInstance | str,
        amount: int = 3,
        event_id: str = "damage:test",
        unpreventable: bool = False,
        combat: bool = False,
    ):
        return damage_proposal(
            engine,
            proposal_id=event_id,
            actor=source.controller,
            source_ref=source.ref,
            target=target.ref if isinstance(target, CardInstance) else target,
            amount=amount,
            combat=combat,
            reason="damage replacement test",
            unpreventable=unpreventable,
        )

    def test_runtime_components_validate_exact_bounded_shapes(self):
        quantity = DamageQuantityReplacementHandler()
        prevention = FixedDamagePreventionHandler()
        context = DamageReplacementSourceContext(
            source_ref="replacement-source",
            source_controller="A",
        )

        doubled = quantity.replacement_effect(quantity_descriptor(), context)
        self.assertEqual("damage", doubled.event_kind)
        self.assertEqual(
            ({"op": "multiply", "field": "amount", "factor": 2},),
            doubled.operations,
        )
        fixed = prevention.replacement_effect(
            prevention_descriptor(amount=2), context
        )
        self.assertEqual(({"op": "prevent", "amount": 2},), fixed.operations)

        with self.assertRaisesRegex(SemanticNodeError, "positive integer"):
            quantity.validate(quantity_descriptor(multiplier=0))
        with self.assertRaisesRegex(SemanticNodeError, "positive integer"):
            prevention.validate(prevention_descriptor(amount=0))
        malformed = quantity_descriptor()
        malformed["condition"]["combat"] = "sometimes"
        with self.assertRaisesRegex(SemanticNodeError, "boolean or null"):
            quantity.validate(malformed)
        malformed = prevention_descriptor()
        malformed["condition"]["unknown"] = True
        with self.assertRaisesRegex(SemanticNodeError, "unknown fields"):
            prevention.validate(malformed)

        inventory = default_damage_replacement_registry().inventory()
        self.assertEqual(
            [
                "prevention.damage.fixed.v1",
                "replacement.damage.quantity.v1",
            ],
            sorted(item["handler_id"] for item in inventory),
        )

    def test_damage_value_objects_reject_unknown_recipient_kinds(self):
        with self.assertRaisesRegex(DamageError, "player or permanent"):
            DamageRecipientSnapshot(  # type: ignore[arg-type]
                ref="B",
                kind="battlefield",
                controller="B",
            )
        with self.assertRaisesRegex(ValueError, "player or permanent"):
            DamageEvent(  # type: ignore[arg-type]
                source="source",
                source_object_id="source-object",
                source_logical_object_id="source-incarnation",
                source_controller="A",
                source_owner="A",
                source_types=(),
                source_subtypes=(),
                source_colors=(),
                source_keywords=(),
                source_is_commander=False,
                target="B",
                target_kind="battlefield",
                target_object_id=None,
                target_controller="B",
                target_types=(),
                target_subtypes=(),
                assigned_amount=1,
                dealt_amount=1,
                prevented_amount=0,
                combat=False,
            )

    def test_prevention_to_zero_ends_the_damage_replacement_event(self):
        context = DamageReplacementSourceContext(
            source_ref="replacement-source",
            source_controller="A",
        )
        multiply = DamageQuantityReplacementHandler().replacement_effect(
            quantity_descriptor(multiplier=2), context
        )
        prevent = FixedDamagePreventionHandler().replacement_effect(
            prevention_descriptor(amount=1), context
        )

        resolved = resolve_replacements(
            self._property_event(1, 1208001),
            (multiply, prevent),
            selections=(prevent.effect_id,),
        )

        self.assertEqual(0, resolved.payload["amount"])
        self.assertEqual(1, resolved.payload["prevented"])
        self.assertEqual((prevent.effect_id,), resolved.applied_effects)

    def test_furnace_and_daunting_order_changes_final_damage(self):
        session = self.session(120461501)
        engine = session.engine
        _furnace, defender, source = self.stage_sources(engine)
        proposal = self.proposal(engine, source=source, target=defender)

        with self.assertRaises(ReplacementChoiceRequired) as required:
            prepare_damage_batch(engine, (proposal,))
        self.assertEqual("B", required.exception.pending.choice.chooser)
        options = required.exception.pending.choice.options
        furnace = next(value for value in options if "quantity" in value)
        prevention = next(value for value in options if "fixed" in value)

        prepared = prepare_damage_batch(
            engine,
            (proposal,),
            selections=(prevention,),
        )
        result = commit_prepared_damage_batch(engine, prepared)
        self.assertEqual(4, result.events[0].dealt_amount)
        self.assertEqual(1, result.events[0].prevented_amount)
        self.assertEqual(3, result.events[0].assigned_amount)
        self.assertEqual(4, defender.marked_damage)

        defender.marked_damage = 0
        prepared = prepare_damage_batch(
            engine,
            (proposal,),
            selections=(furnace,),
        )
        result = commit_prepared_damage_batch(engine, prepared)
        self.assertEqual(5, result.events[0].dealt_amount)
        self.assertEqual(1, result.events[0].prevented_amount)
        self.assertEqual(5, defender.marked_damage)

    def test_static_prevention_applies_to_each_simultaneous_event(self):
        session = self.session(120461502)
        engine = session.engine
        defender = self.add_permanent(
            engine,
            seat="B",
            name="Daunting Defender",
            ref="b-defender",
        )
        defender.counters["+1/+1"] = 5
        source = self.add_permanent(
            engine,
            seat="A",
            name="Mishra, Eminent One",
            ref="a-source",
        )
        proposals = (
            self.proposal(
                engine,
                source=source,
                target=defender,
                event_id="damage:one",
            ),
            self.proposal(
                engine,
                source=source,
                target=defender,
                event_id="damage:two",
            ),
        )

        prepared = prepare_damage_batch(engine, proposals)
        result = commit_prepared_damage_batch(engine, prepared)
        self.assertEqual([2, 2], [event.dealt_amount for event in result.events])
        self.assertEqual([1, 1], [event.prevented_amount for event in result.events])
        self.assertEqual(4, defender.marked_damage)

    def test_four_player_each_opponent_damage_uses_one_typed_batch(self):
        session = self.session(120461511, players=4)
        engine = session.engine
        self.add_permanent(
            engine,
            seat="A",
            name="Furnace of Rath",
            ref="a-furnace",
        )
        source = self.add_permanent(
            engine,
            seat="A",
            name="Mishra, Eminent One",
            ref="a-source",
        )

        dealt = engine.apply_effect(
            {
                "op": "damage_each_opponent",
                "source": source.ref,
                "amount": 1,
                "reason": "four-player damage batch witness",
            },
            actor="A",
        )

        self.assertEqual(6, dealt)
        self.assertEqual(
            {"A": 40, "B": 38, "C": 38, "D": 38},
            {
                seat: engine.state.players[seat].life
                for seat in ("A", "B", "C", "D")
            },
        )
        event = next(
            value
            for value in reversed(engine.state.events)
            if value.code == "effect.damage"
        )
        self.assertEqual(
            ["B", "C", "D"],
            [
                value["target"]
                for value in event.details["damage_events"]
            ],
        )
        self.assertEqual(
            [2, 2, 2],
            [
                value["amount"]
                for value in event.details["damage_events"]
            ],
        )

    def test_four_player_damage_replacement_choices_follow_apnap(self):
        session = self.session(120461512, players=4)
        engine = session.engine
        self.add_permanent(
            engine,
            seat="A",
            name="Furnace of Rath",
            ref="a-furnace",
        )
        self.add_permanent(
            engine,
            seat="C",
            name="Furnace of Rath",
            ref="c-furnace",
        )
        source = self.add_permanent(
            engine,
            seat="A",
            name="Mishra, Eminent One",
            ref="a-source",
        )
        proposals = tuple(
            self.proposal(
                engine,
                source=source,
                target=seat,
                amount=1,
                event_id=f"damage:multiplayer:{seat}",
            )
            for seat in ("B", "C", "D")
        )

        selections: list[str] = []
        for expected_chooser in ("B", "C", "D"):
            with self.assertRaises(ReplacementChoiceRequired) as required:
                prepare_damage_batch(
                    engine,
                    proposals,
                    selections=selections,
                )
            pending = required.exception.pending
            self.assertEqual(expected_chooser, pending.choice.chooser)
            selections.append(pending.choice.options[0])

        prepared = prepare_damage_batch(
            engine,
            proposals,
            selections=selections,
        )
        self.assertEqual(
            ["B", "B", "C", "C", "D", "D"],
            [selection.chooser for selection in prepared.journal],
        )
        result = commit_prepared_damage_batch(engine, prepared)
        self.assertEqual([4, 4, 4], [event.dealt_amount for event in result.events])
        self.assertEqual(
            {"B": 36, "C": 36, "D": 36},
            {
                seat: engine.state.players[seat].life
                for seat in ("B", "C", "D")
            },
        )

    def test_four_player_fixed_prevention_applies_per_controller(self):
        session = self.session(120461513, players=4)
        engine = session.engine
        defenders = []
        for seat in ("B", "C", "D"):
            defender = self.add_permanent(
                engine,
                seat=seat,
                name="Daunting Defender",
                ref=f"{seat.casefold()}-defender",
            )
            defender.counters["+1/+1"] = 5
            defenders.append(defender)
        source = self.add_permanent(
            engine,
            seat="A",
            name="Mishra, Eminent One",
            ref="a-source",
        )
        proposals = tuple(
            self.proposal(
                engine,
                source=source,
                target=defender,
                event_id=f"damage:multiplayer:{defender.controller}",
            )
            for defender in defenders
        )

        prepared = prepare_damage_batch(engine, proposals)
        result = commit_prepared_damage_batch(engine, prepared)

        self.assertEqual([2, 2, 2], [event.dealt_amount for event in result.events])
        self.assertEqual(
            [1, 1, 1],
            [event.prevented_amount for event in result.events],
        )
        self.assertEqual([2, 2, 2], [card.marked_damage for card in defenders])

    def test_unpreventable_damage_applies_prevention_without_reducing_damage(self):
        session = self.session(120461503)
        engine = session.engine
        defender = self.add_permanent(
            engine,
            seat="B",
            name="Daunting Defender",
            ref="b-defender",
        )
        source = self.add_permanent(
            engine,
            seat="A",
            name="Mishra, Eminent One",
            ref="a-source",
        )
        prepared = prepare_damage_batch(
            engine,
            (
                self.proposal(
                    engine,
                    source=source,
                    target=defender,
                    unpreventable=True,
                ),
            ),
        )
        result = commit_prepared_damage_batch(engine, prepared)
        event = result.events[0]
        self.assertEqual(3, event.dealt_amount)
        self.assertEqual(0, event.prevented_amount)
        self.assertTrue(event.unpreventable)
        self.assertEqual(1, len(event.applied_effects))

    def test_protection_prevents_player_and_colored_permanent_damage(self):
        session = self.session(120461507)
        engine = session.engine
        source = self.add_permanent(
            engine,
            seat="A",
            name="Mishra, Eminent One",
            ref="a-source",
        )
        unprotected_source = self.add_permanent(
            engine,
            seat="A",
            name="White Knight",
            ref="a-white-source",
        )
        protected = self.add_permanent(
            engine,
            seat="B",
            name="White Knight",
            ref="b-protected",
        )
        engine.state.players["B"].stats[
            "protection_from_everything_until_next_turn"
        ] = True
        life_before = engine.state.players["B"].life

        prepared = prepare_damage_batch(
            engine,
            (
                self.proposal(
                    engine,
                    source=source,
                    target="B",
                    event_id="damage:protected-player",
                ),
                self.proposal(
                    engine,
                    source=source,
                    target=protected,
                    event_id="damage:protected-permanent",
                ),
                self.proposal(
                    engine,
                    source=unprotected_source,
                    target=protected,
                    event_id="damage:unprotected-permanent",
                ),
            ),
        )
        result = commit_prepared_damage_batch(engine, prepared)

        self.assertEqual(
            [0, 0, 3],
            [event.dealt_amount for event in result.events],
        )
        self.assertEqual(
            [3, 3, 0],
            [event.prevented_amount for event in result.events],
        )
        self.assertEqual(life_before, engine.state.players["B"].life)
        self.assertEqual(3, protected.marked_damage)

    def test_noncombat_damage_dispatches_final_damage_event(self):
        session = self.session(120461508)
        engine = session.engine
        monitor_ref = engine.create_token(
            "A",
            name="Damage Monitor",
            characteristics={
                "type_line": "Token Creature — Test",
                "power": "1",
                "toughness": "1",
            },
        )[0]
        monitor = engine._resolve_object(
            "A", monitor_ref, zones={"battlefield"}
        )
        source = self.add_permanent(
            engine,
            seat="A",
            name="Mishra, Eminent One",
            ref="a-source",
        )
        engine.semantics.put(
            SemanticProgram(
                key=f"{monitor.oracle_id}:test:noncombat-damage",
                label="Noncombat damage happened",
                oracle_id=monitor.oracle_id,
                ability_id="test:noncombat-damage",
                active_zone="battlefield",
                event="damage.dealt",
                event_condition={
                    "field": "combat",
                    "op": "eq",
                    "value": False,
                },
                effects=[],
            )
        )

        dealt = engine.apply_effect(
            {
                "op": "damage",
                "source": source.ref,
                "target": "B",
                "amount": 3,
                "reason": "noncombat trigger witness",
            },
            actor="A",
        )

        self.assertEqual(3, dealt)
        trigger = next(
            item
            for batch in engine.state.pending_trigger_batches
            for group in batch["groups"]
            for item in group["items"]
            if item["label"] == "Noncombat damage happened"
        )
        self.assertEqual(3, trigger["context"]["amount"])
        self.assertEqual(source.ref, trigger["context"]["source"])
        self.assertEqual("B", trigger["context"]["target"])
        self.assertFalse(trigger["context"]["combat"])

    def test_spell_damage_placeholder_preserves_its_card_source(self):
        session = self.session(120461514)
        engine = session.engine
        source = self.add_permanent(
            engine,
            seat="A",
            name="Mishra, Eminent One",
            ref="a-spell-source",
        )
        item = StackItem(
            stack_id="spell-damage-source",
            ref="S-spell-damage-source",
            kind="spell",
            controller="A",
            label="Spell damage source",
            card_object_id=source.object_id,
            visibility=["A", "B"],
        )

        self.assertEqual(
            source.ref,
            engine._semantic_value("$source", item),
        )

    def test_damage_fidelity_pause_stops_remaining_resolution_effects(self):
        session = self.session(120461515)
        engine = session.engine
        engine.state.config.semantic_policy = "trusted_only"
        monitor_ref = engine.create_token(
            "A",
            name="Untrusted Damage Monitor",
            characteristics={
                "type_line": "Token Creature — Test",
                "power": "1",
                "toughness": "1",
            },
        )[0]
        monitor = engine._resolve_object(
            "A", monitor_ref, zones={"battlefield"}
        )
        engine.semantics.put(
            SemanticProgram(
                key=f"{monitor.oracle_id}:test:untrusted-damage",
                label="Untrusted damage trigger",
                oracle_id=monitor.oracle_id,
                ability_id="test:untrusted-damage",
                active_zone="battlefield",
                event="damage.dealt",
                effects=[],
                trust_level="provisional",
            )
        )
        source = self.add_permanent(
            engine,
            seat="A",
            name="Mishra, Eminent One",
            ref="a-pause-source",
        )
        item = StackItem(
            stack_id="damage-pause-resolution",
            ref="S-damage-pause-resolution",
            kind="triggered_ability",
            controller="A",
            label="Damage then gain life",
            source_object_id=source.object_id,
            visibility=["A", "B"],
        )
        engine.state.stack.append(item)
        life_before = engine.state.players["B"].life

        engine._continue_resolution(
            stack_ref=item.ref,
            effects=[
                {
                    "op": "damage",
                    "source": "$source",
                    "target": "B",
                    "amount": 1,
                },
                {"op": "life", "player": "B", "delta": 5},
            ],
            destination=None,
            note="fidelity stop witness",
        )

        self.assertEqual(life_before - 1, engine.state.players["B"].life)
        self.assertIsNotNone(engine._semantic_pause_annotation())
        self.assertIn(item, engine.state.stack)

    def test_unsupported_infect_result_rolls_back_entire_batch(self):
        session = self.session(120461509)
        engine = session.engine
        normal_source = self.add_permanent(
            engine,
            seat="A",
            name="Mishra, Eminent One",
            ref="a-normal-source",
        )
        target = self.add_permanent(
            engine,
            seat="B",
            name="White Knight",
            ref="b-target",
        )
        infect_ref = engine.create_token(
            "A",
            name="Infect Source",
            characteristics={
                "type_line": "Token Creature — Test",
                "power": "1",
                "toughness": "1",
                "keywords": ["Infect"],
                "colors": ["G"],
            },
        )[0]
        infect_source = engine._resolve_object(
            "A", infect_ref, zones={"battlefield"}
        )
        life_before = engine.state.players["B"].life
        state_before = authoritative_state_hash(engine.state)
        prepared = prepare_damage_batch(
            engine,
            (
                self.proposal(
                    engine,
                    source=normal_source,
                    target="B",
                    event_id="damage:valid-first",
                ),
                self.proposal(
                    engine,
                    source=infect_source,
                    target=target,
                    amount=1,
                    event_id="damage:unsupported-second",
                ),
            ),
        )

        with self.assertRaisesRegex(DamageError, "Infect and wither"):
            commit_prepared_damage_batch(engine, prepared)
        self.assertEqual(life_before, engine.state.players["B"].life)
        self.assertEqual(0, target.marked_damage)
        self.assertEqual(state_before, authoritative_state_hash(engine.state))

    def test_mana_ability_damage_uses_transaction_or_fails_before_damage(self):
        session = self.session(120461510)
        engine = session.engine
        self.add_permanent(
            engine,
            seat="A",
            name="Furnace of Rath",
            ref="a-furnace-one",
        )
        source = self.add_permanent(
            engine,
            seat="B",
            name="Elves of Deep Shadow",
            ref="b-pain-source",
        )
        life_before = engine.state.players["B"].life

        engine._apply_mana_mode_side_effects(
            "B",
            ({"op": "damage_self", "amount": 1},),
            source=source,
        )
        self.assertEqual(life_before - 2, engine.state.players["B"].life)

        self.add_permanent(
            engine,
            seat="A",
            name="Furnace of Rath",
            ref="a-furnace-two",
        )
        engine.state.active_player = "B"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.priority_player = "B"
        engine.state.priority_passes = []
        engine.state.players["B"].turns_begun = (
            source.acquired_control_turn_count + 1
        )
        ability = next(
            candidate
            for candidate in engine._activated_abilities(source)
            if "Add {B}" in candidate.effect_text
        )
        before_rejected_choice = authoritative_state_hash(engine.state)
        with self.assertRaisesRegex(GameRuleError, "not yet resumable"):
            with engine.transaction():
                engine._activate(
                    "B",
                    {
                        "source": source.ref,
                        "ability": ability.ability_id,
                        "mana_output": {"B": 1},
                    },
                )
        self.assertEqual(
            before_rejected_choice, authoritative_state_hash(engine.state)
        )
        self.assertFalse(engine.state.cards[source.object_id].tapped)
        self.assertEqual(0, engine.state.players["B"].mana_pool["B"])

    def test_validation_failure_is_atomic_before_any_damage_result(self):
        session = self.session(120461504)
        engine = session.engine
        _furnace, defender, source = self.stage_sources(engine)
        before = authoritative_state_hash(engine.state)
        with self.assertRaisesRegex(DamageError, "selections"):
            prepare_damage_batch(
                engine,
                (
                    self.proposal(
                        engine,
                        source=source,
                        target=defender,
                        amount=0,
                    ),
                ),
                selections=("not-applicable",),
            )
        self.assertEqual(before, authoritative_state_hash(engine.state))

    def test_combat_replacement_choice_is_seat_scoped_and_precommit(self):
        session = self.session(120461505)
        engine = session.engine
        _furnace, defender, source = self.stage_sources(engine)
        engine.state.active_player = "A"
        engine.state.phase = "combat"
        engine.state.step = "combat_damage"
        life_before = engine.state.players["B"].life

        waiting = engine._apply_combat_assignments(
            [{"source": source.ref, "target": defender.ref, "amount": 3}]
        )
        self.assertTrue(waiting)
        self.assertEqual(0, defender.marked_damage)
        self.assertEqual(life_before, engine.state.players["B"].life)
        decision = engine.state.pending_decision
        self.assertIsNotNone(decision)
        self.assertEqual("replacement.order", decision.kind)
        self.assertEqual(["B"], decision.actors)

        projector = StateProjector(self.db, engine.state)
        projected_b = projector._decision("pilot:B")
        self.assertIsNotNone(projected_b)
        self.assertIsNone(projector._decision("pilot:A"))
        serialized = json.dumps(projected_b, sort_keys=True)
        self.assertNotIn("replacement_batch", serialized)
        self.assertNotIn("replacement_effects", serialized)
        self.assertNotIn(defender.object_id, serialized)

        selected = next(
            option["id"]
            for option in projected_b["ctx"]["options"]
            if "fixed" in option["id"]
        )
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()
        accepted = session.act(
            "pilot:B",
            {
                "action_id": "choose",
                "choices": {"replacement": selected},
            },
        )
        self.assertTrue(accepted.ok, accepted.summary)
        self.assertEqual(4, defender.marked_damage)
        self.assertIsNotNone(engine.state.pending_decision)
        self.assertEqual("priority", engine.state.pending_decision.kind)
        expected_hash = authoritative_state_hash(engine.state)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "combat-damage-replacement-record"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(expected_hash, replay["final_state_hash"])

    def test_semantic_damage_replacement_choice_replays_exactly(self):
        session = self.session(120461506)
        engine = session.engine
        _furnace, defender, source = self.stage_sources(engine)
        program = SemanticProgram(
            key="test:damage-replacement-replay",
            label="Replay a damage replacement choice",
            effects=[
                {
                    "op": "damage",
                    "source": "$source",
                    "target": defender.ref,
                    "amount": 3,
                }
            ],
            trust_level="provisional",
        )
        engine.semantics.put(program)
        engine.state.stack.append(
            StackItem(
                stack_id="damage-replacement-replay",
                ref="S-damage-replacement-replay",
                kind="triggered_ability",
                controller="A",
                label=program.label,
                source_object_id=source.object_id,
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
        self.assertEqual(
            "replacement.order", engine.state.pending_decision.kind
        )
        projected = StateProjector(self.db, engine.state)._decision("pilot:B")
        selected = next(
            option["id"]
            for option in projected["ctx"]["options"]
            if "fixed" in option["id"]
        )
        result = session.act(
            "pilot:B",
            {
                "action_id": "choose",
                "choices": {"replacement": selected},
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(4, defender.marked_damage)
        expected_hash = authoritative_state_hash(engine.state)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "damage-replacement-record"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(3, replay["commands"])
        self.assertEqual(expected_hash, replay["final_state_hash"])

    def test_damage_amount_pipeline_property_1000_deterministic_transitions(self):
        quantity = DamageQuantityReplacementHandler()
        prevention = FixedDamagePreventionHandler()
        randomizer = random.Random(120461599)
        for index in range(1_000):
            amount = randomizer.randint(1, 20)
            multiplier = randomizer.randint(2, 4)
            prevented = randomizer.randint(1, 8)
            context = DamageReplacementSourceContext(
                source_ref=f"source-{index}",
                source_controller="A",
            )
            multiply = quantity.replacement_effect(
                quantity_descriptor(multiplier=multiplier), context
            )
            prevent = prevention.replacement_effect(
                prevention_descriptor(amount=prevented), context
            )
            event = self._property_event(amount, index)
            first = resolve_replacements(
                event,
                (multiply, prevent),
                selections=(multiply.effect_id, prevent.effect_id),
            )
            second_selections = (
                (prevent.effect_id, multiply.effect_id)
                if prevented < amount
                else (prevent.effect_id,)
            )
            second = resolve_replacements(
                event,
                (multiply, prevent),
                selections=second_selections,
            )
            self.assertEqual(
                max(0, amount * multiplier - prevented),
                first.payload["amount"],
            )
            self.assertEqual(
                max(0, amount - prevented) * multiplier,
                second.payload["amount"],
            )

    @staticmethod
    def _property_event(amount: int, index: int):
        from mtg_commander_sim.replacement_effects import ReplaceableEvent

        return ReplaceableEvent(
            event_id=f"damage:property:{index}",
            kind="damage",
            affected_player="B",
            payload={
                "source_controller": "A",
                "target_controller": "B",
                "target_kind": "player",
                "source_characteristics": [],
                "target_characteristics": [],
                "combat": False,
                "amount": amount,
                "prevented": 0,
                "unpreventable": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
