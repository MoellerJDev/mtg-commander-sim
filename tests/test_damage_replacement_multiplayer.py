from __future__ import annotations

import json
from pathlib import Path
import random
import tempfile
import unittest

from common import ROOT, keep_all, make_session
from scripts.build_test_database import build_fixture_database
from quorune.carddb import CardDatabase
from quorune.damage import (
    commit_prepared_damage_batch,
    damage_proposal,
    DamageEvent,
    DamageError,
    DamageRecipientSnapshot,
    prepare_damage_batch,
)
from quorune.deck import DeckLoader
from quorune.engine import GameRuleError
from quorune.model import CardInstance, StackItem
from quorune.projection import StateProjector
from quorune.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)
from quorune.replacement_effects import (
    ReplacementChoiceRequired,
    resolve_replacements,
)
from quorune.semantic_runtime import (
    DamageQuantityReplacementHandler,
    DamageReplacementSourceContext,
    FixedDamagePreventionHandler,
    SemanticNodeError,
    default_damage_replacement_registry,
)
from quorune.semantics import SemanticProgram


from damage_replacement_support import (
    DamageReplacementPipelineBase,
    damage_condition,
    prevention_descriptor,
    quantity_descriptor,
)


class DamageReplacementMultiplayerTests(DamageReplacementPipelineBase):
    """Focused CR 120/614/615/616 damage transaction witnesses."""

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



if __name__ == "__main__":
    unittest.main()
