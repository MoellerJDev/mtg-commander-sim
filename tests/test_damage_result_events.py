from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common import ROOT, keep_all, make_session
from scripts.build_test_database import build_fixture_database
from mtg_commander_sim.carddb import CardDatabase
from mtg_commander_sim.damage import (
    DamageError,
    commit_prepared_damage_batch,
    damage_proposal,
    prepare_damage_batch,
)
from mtg_commander_sim.damage_results import (
    PreparedDamageResults,
    commit_damage_result_plan,
    plan_damage_result_commit,
    prepare_damage_results,
)
from mtg_commander_sim.deck import DeckLoader
from mtg_commander_sim.model import CardInstance, CombatState, StackItem
from mtg_commander_sim.projection import StateProjector
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)
from mtg_commander_sim.replacement_effects import (
    ReplaceableEvent,
    ReplacementClass,
    ReplacementEffect,
    resolve_replacements,
)
from mtg_commander_sim.semantic_runtime.damage_results import (
    DamageResultReplacementSourceContext,
    LifeGainMultiplierHandler,
    collect_damage_result_replacement_effects,
)
from mtg_commander_sim.semantic_runtime.context import SemanticNodeError
from mtg_commander_sim.semantics import SemanticProgram


def result_effect(
    effect_id: str,
    event_kind: str,
    operation: dict,
    *,
    conditions: dict | None = None,
) -> ReplacementEffect:
    return ReplacementEffect(
        effect_id=effect_id,
        source_id=f"source:{effect_id}",
        event_kind=event_kind,
        replacement_class=ReplacementClass.OTHER,
        conditions=conditions or {},
        operations=(operation,),
        label=effect_id,
    )


class DamageResultEventTests(unittest.TestCase):
    """CR 120.3/120.4c damage-result materialization and commit witnesses."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        database = Path(cls.temporary.name) / "damage-results.sqlite3"
        build_fixture_database(
            [
                ROOT / "tests" / "fixtures" / "scryfall-exact-lists.json",
                ROOT / "tests" / "fixtures" / "damage-result-cards.json",
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

    def permanent(self, engine, seat: str, name: str, *, ref: str):
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

    @staticmethod
    def token(
        engine,
        seat: str,
        name: str,
        *,
        type_line: str = "Token Creature — Test",
        keywords: tuple[str, ...] = (),
        oracle_text: str = "",
        power: int = 3,
        toughness: int = 3,
        loyalty: int | None = None,
        defense: int | None = None,
        battle_protector: str | None = None,
    ):
        characteristics = {
            "type_line": type_line,
            "power": str(power),
            "toughness": str(toughness),
            "keywords": list(keywords),
            "oracle_text": oracle_text,
            "colors": ["G"],
        }
        if loyalty is not None:
            characteristics["loyalty"] = str(loyalty)
        if defense is not None:
            characteristics["defense"] = str(defense)
        ref = engine.create_token(
            seat,
            name=name,
            characteristics=characteristics,
            battle_protector=battle_protector,
        )[0]
        return engine._resolve_object(seat, ref, zones={"battlefield"})

    @staticmethod
    def proposal(
        engine,
        source,
        target,
        amount: int,
        *,
        event_id: str,
        combat: bool = False,
        deathtouch: bool = False,
    ):
        return damage_proposal(
            engine,
            proposal_id=event_id,
            actor=source.controller,
            source_ref=source.ref,
            target=target.ref if hasattr(target, "ref") else target,
            amount=amount,
            combat=combat,
            reason="damage-result witness",
            deathtouch=deathtouch,
        )

    def commit(self, engine, *proposals):
        prepared = prepare_damage_batch(engine, proposals)
        return commit_prepared_damage_batch(engine, prepared)

    def test_infect_player_damage_is_poison_not_life_loss(self):
        engine = self.session(120_300_001).engine
        source = self.token(engine, "A", "Infect Source", keywords=("Infect",))
        life_before = engine.state.players["B"].life

        result = self.commit(
            engine,
            self.proposal(
                engine, source, "B", 3, event_id="damage:infect-player"
            ),
        )

        self.assertEqual(life_before, engine.state.players["B"].life)
        self.assertEqual(3, engine.state.players["B"].poison)
        poison = [
            event
            for event in result.result_events
            if event.kind == "counter.place"
        ]
        self.assertEqual(1, len(poison))
        self.assertEqual("poison", poison[0].counter_name)
        self.assertEqual("A", poison[0].source_controller)

    def test_source_pinned_keyword_witnesses_follow_damage_results(self):
        engine = self.session(120_300_009).engine
        infect = self.permanent(
            engine, "A", "Phyrexian Crusader", ref="a-crusader"
        )
        wither = self.permanent(
            engine, "A", "Boggart Ram-Gang", ref="a-ram-gang"
        )
        lifelink = self.permanent(
            engine, "A", "Healer's Hawk", ref="a-hawk"
        )
        toxic = self.permanent(
            engine, "A", "Crawling Chorus", ref="a-chorus"
        )
        target = self.token(engine, "B", "Target", toughness=8)
        engine.state.players["A"].life = 20
        life_before = engine.state.players["B"].life

        self.commit(
            engine,
            self.proposal(
                engine, infect, "B", 2, event_id="damage:crusader"
            ),
            self.proposal(
                engine, wither, target, 3, event_id="damage:ram-gang"
            ),
            self.proposal(
                engine, lifelink, "B", 1, event_id="damage:hawk"
            ),
            self.proposal(
                engine,
                toxic,
                "B",
                1,
                event_id="damage:chorus",
                combat=True,
            ),
        )

        self.assertEqual(3, engine.state.players["B"].poison)
        self.assertEqual(life_before - 2, engine.state.players["B"].life)
        self.assertEqual(3, target.counters["-1/-1"])
        self.assertEqual(21, engine.state.players["A"].life)

    def test_infect_and_wither_use_minus_counters_only_on_creatures(self):
        for keyword in ("Infect", "Wither"):
            with self.subTest(keyword=keyword):
                engine = self.session(120_300_002).engine
                source = self.token(
                    engine, "A", f"{keyword} Source", keywords=(keyword,)
                )
                target = self.token(engine, "B", "Target", toughness=5)
                life_before = engine.state.players["B"].life

                self.commit(
                    engine,
                    self.proposal(
                        engine,
                        source,
                        target,
                        2,
                        event_id=f"damage:{keyword.casefold()}-creature",
                    ),
                    self.proposal(
                        engine,
                        source,
                        "B",
                        1,
                        event_id=f"damage:{keyword.casefold()}-player",
                    ),
                )

                self.assertEqual(0, target.marked_damage)
                self.assertEqual(2, target.counters["-1/-1"])
                if keyword == "Infect":
                    self.assertEqual(life_before, engine.state.players["B"].life)
                    self.assertEqual(1, engine.state.players["B"].poison)
                else:
                    self.assertEqual(
                        life_before - 1, engine.state.players["B"].life
                    )
                    self.assertEqual(0, engine.state.players["B"].poison)

    def test_lifelink_gains_final_damage_across_multiple_recipients(self):
        engine = self.session(120_300_003).engine
        source = self.token(
            engine, "A", "Lifelink Source", keywords=("Lifelink",)
        )
        target = self.token(engine, "B", "Target", toughness=6)
        engine.state.players["A"].life = 20

        result = self.commit(
            engine,
            self.proposal(
                engine, source, "B", 2, event_id="damage:lifelink-player"
            ),
            self.proposal(
                engine, source, target, 3, event_id="damage:lifelink-creature"
            ),
        )

        self.assertEqual(25, engine.state.players["A"].life)
        self.assertEqual(3, target.marked_damage)
        self.assertEqual(1, len(result.lifelink_gains))
        self.assertEqual(5, result.lifelink_gains[0].amount)

    def test_toxic_is_additional_only_for_creature_combat_damage_to_player(self):
        engine = self.session(120_300_004).engine
        source = self.token(
            engine,
            "A",
            "Toxic Source",
            keywords=("Toxic",),
            oracle_text="Toxic 2",
        )
        life_before = engine.state.players["B"].life

        self.commit(
            engine,
            self.proposal(
                engine,
                source,
                "B",
                3,
                event_id="damage:toxic-combat",
                combat=True,
            ),
        )
        self.assertEqual(life_before - 3, engine.state.players["B"].life)
        self.assertEqual(2, engine.state.players["B"].poison)

        self.commit(
            engine,
            self.proposal(
                engine,
                source,
                "B",
                1,
                event_id="damage:toxic-noncombat",
                combat=False,
            ),
        )
        self.assertEqual(2, engine.state.players["B"].poison)

    def test_multiple_toxic_abilities_are_cumulative(self):
        engine = self.session(120_300_005).engine
        source = self.token(
            engine,
            "A",
            "Multiple Toxic Source",
            keywords=("Toxic",),
            oracle_text="Toxic 1\nToxic 2",
        )

        self.commit(
            engine,
            self.proposal(
                engine,
                source,
                "B",
                1,
                event_id="damage:multiple-toxic",
                combat=True,
            ),
        )
        self.assertEqual(3, engine.state.players["B"].poison)

    def test_four_player_keyword_results_keep_source_attribution(self):
        engine = self.session(120_300_012, players=4).engine
        source_a = self.token(
            engine,
            "A",
            "A Infect Toxic Lifelink Source",
            keywords=("Infect", "Lifelink", "Toxic"),
            oracle_text="Toxic 1",
        )
        source_c = self.token(
            engine,
            "C",
            "C Toxic Lifelink Source",
            keywords=("Lifelink", "Toxic"),
            oracle_text="Toxic 2",
        )
        engine.state.players["A"].life = 20
        engine.state.players["C"].life = 20

        result = self.commit(
            engine,
            self.proposal(
                engine,
                source_a,
                "B",
                2,
                event_id="damage:four-player-keyword-a",
                combat=True,
            ),
            self.proposal(
                engine,
                source_c,
                "D",
                3,
                event_id="damage:four-player-keyword-c",
                combat=True,
            ),
        )

        self.assertEqual(3, engine.state.players["B"].poison)
        self.assertEqual(2, engine.state.players["D"].poison)
        self.assertEqual(40, engine.state.players["B"].life)
        self.assertEqual(37, engine.state.players["D"].life)
        self.assertEqual(22, engine.state.players["A"].life)
        self.assertEqual(23, engine.state.players["C"].life)
        poison_attribution = {
            (event.player, event.cause, event.source_controller)
            for event in result.result_events
            if event.kind == "counter.place"
            and event.counter_name == "poison"
        }
        self.assertEqual(
            {
                ("B", "infect", "A"),
                ("B", "toxic", "A"),
                ("D", "toxic", "C"),
            },
            poison_attribution,
        )

    def test_unresolved_toxic_value_fails_before_mutation(self):
        engine = self.session(120_300_006).engine
        source = self.token(
            engine, "A", "Unresolved Toxic Source", keywords=("Toxic",)
        )
        before = authoritative_state_hash(engine.state)
        proposal = self.proposal(
            engine,
            source,
            "B",
            1,
            event_id="damage:unresolved-toxic",
            combat=True,
        )

        with self.assertRaisesRegex(DamageError, "unresolved total toxic"):
            prepare_damage_batch(engine, (proposal,))
        self.assertEqual(before, authoritative_state_hash(engine.state))

    def test_prevented_infect_and_toxic_create_no_counter_results(self):
        engine = self.session(120_300_010).engine
        source = self.token(
            engine,
            "A",
            "Prevented Infect Toxic Source",
            keywords=("Infect", "Toxic"),
            oracle_text="Toxic 2",
        )
        engine.state.players["B"].stats[
            "protection_from_everything_until_next_turn"
        ] = True
        life_before = engine.state.players["B"].life

        result = self.commit(
            engine,
            self.proposal(
                engine,
                source,
                "B",
                3,
                event_id="damage:prevented-infect-toxic",
                combat=True,
            ),
        )

        self.assertEqual(0, result.events[0].dealt_amount)
        self.assertEqual(3, result.events[0].prevented_amount)
        self.assertEqual((), result.result_events)
        self.assertEqual(0, engine.state.players["B"].poison)
        self.assertEqual(life_before, engine.state.players["B"].life)

    def test_multitype_permanent_receives_every_applicable_result(self):
        engine = self.session(120_300_007).engine
        source = self.token(engine, "A", "Infect Source", keywords=("Infect",))
        target = self.token(
            engine,
            "B",
            "Every Damageable Type",
            type_line="Token Creature Planeswalker Battle — Siege",
            toughness=8,
            loyalty=5,
            defense=4,
            battle_protector="A",
        )

        self.commit(
            engine,
            self.proposal(
                engine, source, target, 2, event_id="damage:multitype"
            ),
        )

        self.assertEqual(2, target.counters["-1/-1"])
        self.assertEqual(3, target.counters["loyalty"])
        self.assertEqual(2, target.counters["defense"])
        self.assertEqual(0, target.marked_damage)

    def test_wither_damage_still_records_deathtouch_result(self):
        engine = self.session(120_300_008).engine
        source = self.token(engine, "A", "Wither Source", keywords=("Wither",))
        target = self.token(engine, "B", "Target", toughness=8)

        self.commit(
            engine,
            self.proposal(
                engine,
                source,
                target,
                1,
                event_id="damage:wither-deathtouch",
                deathtouch=True,
            ),
        )

        self.assertEqual(1, target.counters["-1/-1"])
        self.assertEqual(0, target.marked_damage)
        self.assertTrue(target.deathtouch_damage)

    def test_containing_result_replacement_precedes_life_gain_replacement(self):
        engine = self.session(120_400_001).engine
        source = self.token(engine, "A", "Damage Source")
        self.token(engine, "B", "Worship Creature")
        engine.state.players["B"].life = 5
        damage = self.proposal(
            engine, source, "B", 5, event_id="damage:worship-example"
        ).event()
        gain = ReplaceableEvent(
            event_id="damage:worship-example/gain",
            kind="life.change",
            affected_player="B",
            payload={
                "target_kind": "player",
                "player": "B",
                "direction": "gain",
                "amount": 5,
                "requested_amount": 5,
                "source": source.ref,
                "source_controller": "A",
                "cause": "damage-replacement",
            },
        )
        damage = ReplaceableEvent(
            event_id=damage.event_id,
            kind=damage.kind,
            affected_player=damage.affected_player,
            affected_object=damage.affected_object,
            payload=damage.payload,
            children=(gain,),
        )
        worship = result_effect(
            "worship",
            "damage.results",
            {"op": "cap_result_life_loss", "minimum": 1},
            conditions={
                "subject_kind": {"eq": "player"},
                "life_loss_amount": {"not_in": [0]},
                "life_after_without_replacement": {"lt": 1},
                "controls_creature": {"eq": True},
            },
        )
        boon = result_effect(
            "boon",
            "life.change",
            {"op": "multiply", "field": "amount", "factor": 2},
            conditions={"direction": {"eq": "gain"}},
        )

        prepared = prepare_damage_results(
            engine, (damage,), effects=(boon, worship)
        )
        self.assertEqual((1,), prepared.journal[0].path)
        plan = plan_damage_result_commit(engine, prepared)
        commit_damage_result_plan(engine, plan)

        self.assertEqual(10, engine.state.players["B"].life)
        self.assertEqual("boon", prepared.journal[0].effect_id)

    def test_life_floor_caps_damage_result_without_an_offsetting_gain(self):
        engine = self.session(120_400_002).engine
        source = self.token(engine, "A", "Damage Source")
        self.token(engine, "B", "Worship Creature")
        engine.state.players["B"].life = 5
        damage = self.proposal(
            engine, source, "B", 5, event_id="damage:worship-floor"
        ).event()
        worship = result_effect(
            "worship",
            "damage.results",
            {"op": "cap_result_life_loss", "minimum": 1},
            conditions={
                "subject_kind": {"eq": "player"},
                "life_loss_amount": {"not_in": [0]},
                "life_after_without_replacement": {"lt": 1},
                "controls_creature": {"eq": True},
            },
        )

        prepared = prepare_damage_results(engine, (damage,), effects=(worship,))
        plan = plan_damage_result_commit(engine, prepared)
        commit_damage_result_plan(engine, plan)

        self.assertEqual(1, engine.state.players["B"].life)
        self.assertEqual(4, plan.records[0].amount)

    def test_boon_reflection_doubles_lifelink_result(self):
        engine = self.session(120_400_005).engine
        self.permanent(engine, "A", "Boon Reflection", ref="a-boon")
        source = self.token(
            engine, "A", "Lifelink Source", keywords=("Lifelink",)
        )
        engine.state.players["A"].life = 20

        prepared = prepare_damage_batch(
            engine,
            (self.proposal(
                engine, source, "B", 3, event_id="damage:boon-lifelink"
            ),),
        )
        result = commit_prepared_damage_batch(engine, prepared)

        self.assertEqual(26, engine.state.players["A"].life)
        self.assertEqual(6, result.lifelink_gains[0].amount)
        self.assertEqual(1, len(prepared.result_journal))
        self.assertIn(
            "replacement.life.gain.multiplier.v1",
            prepared.result_journal[0].effect_id,
        )

    def test_life_gain_multiplier_ignores_losses_and_rejects_bad_shape(self):
        handler = LifeGainMultiplierHandler()
        descriptor = {
            "handler_id": "replacement.life.gain.multiplier.v1",
            "schema_version": 1,
            "event": "life.change",
            "condition": {
                "affected_player_relation": "source_controller",
            },
            "modification": {"multiplier": 2},
        }
        effect = handler.replacement_effect(
            descriptor,
            DamageResultReplacementSourceContext(
                source_ref="boon-negative-witness",
                source_controller="A",
            ),
        )
        loss = ReplaceableEvent(
            event_id="life:loss:boon-negative",
            kind="life.change",
            affected_player="A",
            payload={"direction": "loss", "amount": 3},
        )

        resolved = resolve_replacements(loss, (effect,), selections=())
        self.assertEqual(loss, resolved)

        malformed = {
            **descriptor,
            "modification": {"multiplier": 1},
        }
        with self.assertRaisesRegex(SemanticNodeError, "at least 2"):
            handler.replacement_effect(
                malformed,
                DamageResultReplacementSourceContext(
                    source_ref="boon-negative-witness",
                    source_controller="A",
                ),
            )

    def test_worship_caps_damage_result_at_one(self):
        engine = self.session(120_400_006).engine
        self.permanent(engine, "B", "Worship", ref="b-worship")
        self.token(engine, "B", "Worship Creature")
        source = self.token(engine, "A", "Damage Source")
        engine.state.players["B"].life = 5

        result = self.commit(
            engine,
            self.proposal(
                engine, source, "B", 5, event_id="damage:worship-semantic"
            ),
        )

        self.assertEqual(1, engine.state.players["B"].life)
        self.assertEqual(5, result.events[0].dealt_amount)
        life_loss = next(
            event
            for event in result.result_events
            if event.kind == "life.change" and event.direction == "loss"
        )
        self.assertEqual(4, life_loss.amount)

    def test_worship_and_boon_follow_containing_event_order(self):
        engine = self.session(120_400_007).engine
        self.permanent(engine, "B", "Worship", ref="b-worship")
        self.permanent(engine, "B", "Boon Reflection", ref="b-boon")
        self.token(engine, "B", "Worship Creature")
        source = self.token(engine, "A", "Damage Source")
        engine.state.players["B"].life = 5
        damage = self.proposal(
            engine, source, "B", 5, event_id="damage:official-result-order"
        ).event()
        gain = ReplaceableEvent(
            event_id="damage:official-result-order/gain",
            kind="life.change",
            affected_player="B",
            payload={
                "target_kind": "player",
                "player": "B",
                "direction": "gain",
                "amount": 5,
                "requested_amount": 5,
                "source": source.ref,
                "source_controller": "A",
                "cause": "damage-replacement",
            },
        )
        damage = ReplaceableEvent(
            event_id=damage.event_id,
            kind=damage.kind,
            affected_player=damage.affected_player,
            affected_object=damage.affected_object,
            payload=damage.payload,
            children=(gain,),
        )
        sources = engine._semantic_event_sources()
        effects = collect_damage_result_replacement_effects(
            engine,
            sources=sources,
            source_zones={card.object_id: card.zone for card in sources},
        )

        prepared = prepare_damage_results(engine, (damage,), effects=effects)
        plan = plan_damage_result_commit(engine, prepared)
        commit_damage_result_plan(engine, plan)

        self.assertEqual(10, engine.state.players["B"].life)
        self.assertEqual(1, len(prepared.journal))
        self.assertIn("life.gain.multiplier", prepared.journal[0].effect_id)
        self.assertNotIn(
            "damage.result.life_floor",
            {entry.effect_id for entry in prepared.journal},
        )

    def test_four_player_result_choices_follow_apnap_and_replay_exactly(self):
        engine = self.session(120_400_003, players=4).engine
        source = self.token(engine, "A", "Damage Source")
        events = (
            self.proposal(
                engine, source, "B", 2, event_id="damage:result-choice-b"
            ).event(),
            self.proposal(
                engine, source, "C", 2, event_id="damage:result-choice-c"
            ).event(),
        )
        effects = (
            result_effect(
                "add-one",
                "life.change",
                {"op": "add", "field": "amount", "amount": 1},
                conditions={"direction": {"eq": "loss"}},
            ),
            result_effect(
                "double",
                "life.change",
                {"op": "multiply", "field": "amount", "factor": 2},
                conditions={"direction": {"eq": "loss"}},
            ),
        )

        first = prepare_damage_results(engine, events, effects=effects)
        self.assertIsNotNone(first.pending)
        assert first.pending is not None
        self.assertEqual("B", first.pending.choice.chooser)
        second = prepare_damage_results(
            engine, events, effects=effects, selections=("add-one",)
        )
        self.assertIsNotNone(second.pending)
        assert second.pending is not None
        self.assertEqual("C", second.pending.choice.chooser)
        selections = ("add-one", "double")
        complete = prepare_damage_results(
            engine, events, effects=effects, selections=selections
        )
        replayed = prepare_damage_results(
            engine, events, effects=tuple(reversed(effects)), selections=selections
        )

        self.assertIsNone(complete.pending)
        self.assertEqual(complete.events, replayed.events)
        self.assertEqual(complete.journal, replayed.journal)
        self.assertEqual(["B", "B", "C", "C"], [
            entry.chooser for entry in complete.journal
        ])

    def test_keyword_damage_results_replay_from_combat_assignment(self):
        session = self.session(120_300_011)
        engine = session.engine
        engine.state.phase_index = 7
        engine.state.phase = "combat"
        engine.state.step = "combat_damage"
        infect = self.token(
            engine,
            "A",
            "Infect Toxic Lifelink Attacker",
            power=4,
            toughness=4,
            keywords=("Infect", "Lifelink", "Toxic"),
            oracle_text="Toxic 2",
        )
        wither = self.token(
            engine,
            "A",
            "Wither Attacker",
            power=2,
            toughness=4,
            keywords=("Wither",),
        )
        trampler = self.token(
            engine,
            "A",
            "Ordinary Trample Attacker",
            power=2,
            toughness=4,
            keywords=("Trample",),
        )
        wither_blocker = self.token(
            engine, "B", "Wither Blocker", power=0, toughness=5
        )
        trample_blocker = self.token(
            engine, "B", "Trample Blocker", power=0, toughness=1
        )
        infect.attacking = "B"
        wither.attacking = "B"
        trampler.attacking = "B"
        wither_blocker.blocking = wither.object_id
        trample_blocker.blocking = trampler.object_id
        engine.state.combat = CombatState(
            attackers_declared=True,
            blockers_declared=True,
            had_attacking_creature=True,
            attackers={
                infect.object_id: "B",
                wither.object_id: "B",
                trampler.object_id: "B",
            },
            defending_players=["B"],
            blockers={
                wither.object_id: [wither_blocker.object_id],
                trampler.object_id: [trample_blocker.object_id],
            },
        )
        engine._begin_combat_damage()
        self.assertEqual("combat.damage", engine.state.pending_decision.kind)
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()

        result = session.act(
            "pilot:A",
            {
                "a": "dmg",
                "assignments": [
                    {"source": infect.ref, "target": "B", "amount": 4},
                    {
                        "source": wither.ref,
                        "target": wither_blocker.ref,
                        "amount": 2,
                    },
                    {
                        "source": trampler.ref,
                        "target": trample_blocker.ref,
                        "amount": 1,
                    },
                    {"source": trampler.ref, "target": "B", "amount": 1},
                ],
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(6, engine.state.players["B"].poison)
        self.assertEqual(39, engine.state.players["B"].life)
        self.assertEqual(44, engine.state.players["A"].life)
        self.assertEqual(2, wither_blocker.counters["-1/-1"])

        expected_hash = authoritative_state_hash(engine.state)
        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "keyword-damage-result-record"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(1, replay["commands"])
        self.assertEqual(expected_hash, replay["final_state_hash"])

    def test_damage_result_replacement_choice_is_private_and_replays(self):
        session = self.session(120_400_008)
        engine = session.engine
        self.permanent(engine, "A", "Boon Reflection", ref="a-boon-one")
        self.permanent(engine, "A", "Boon Reflection", ref="a-boon-two")
        source = self.token(
            engine, "A", "Lifelink Source", keywords=("Lifelink",)
        )
        engine.state.players["A"].life = 20
        program = SemanticProgram(
            key="test:damage-result-replacement-replay",
            label="Replay a damage-result replacement choice",
            effects=[
                {
                    "op": "damage",
                    "source": "$source",
                    "target": "B",
                    "amount": 3,
                }
            ],
            trust_level="provisional",
        )
        engine.semantics.put(program)
        engine.state.stack.append(
            StackItem(
                stack_id="damage-result-replacement-replay",
                ref="S-damage-result-replacement-replay",
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
        self.assertEqual("replacement.order", engine.state.pending_decision.kind)

        projector = StateProjector(self.db, engine.state)
        projected_a = projector._decision("pilot:A")
        self.assertIsNotNone(projected_a)
        self.assertIsNone(projector._decision("pilot:B"))
        serialized = json.dumps(projected_a, sort_keys=True)
        for forbidden in (
            "replacement_batch",
            "replacement_effects",
            "life_before",
            "damage.results",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertNotIn(source.object_id, serialized)

        selected = projected_a["ctx"]["options"][0]["id"]
        result = session.act(
            "pilot:A",
            {
                "action_id": "choose",
                "choices": {"replacement": selected},
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(32, engine.state.players["A"].life)
        expected_hash = authoritative_state_hash(engine.state)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "damage-result-replacement-record"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(3, replay["commands"])
        self.assertEqual(expected_hash, replay["final_state_hash"])

    def test_invalid_result_leaf_keeps_the_whole_batch_atomic(self):
        engine = self.session(120_400_004).engine
        source = self.token(engine, "A", "Damage Source")
        prepared = prepare_damage_batch(
            engine,
            (
                self.proposal(
                    engine, source, "B", 2, event_id="damage:atomic"
                ),
            ),
        )
        root = prepared.result_events[0]
        bad_child = ReplaceableEvent(
            event_id="damage.result:unsupported",
            kind="unsupported.result",
            affected_player="B",
            payload={"amount": 1, "requested_amount": 1},
        )
        invalid = PreparedDamageResults(
            events=(
                ReplaceableEvent(
                    event_id=root.event_id,
                    kind=root.kind,
                    affected_player=root.affected_player,
                    affected_object=root.affected_object,
                    payload=root.payload,
                    children=(*root.children, bad_child),
                ),
            ),
            effects=(),
            journal=(),
        )
        before = authoritative_state_hash(engine.state)

        with self.assertRaisesRegex(ValueError, "Unsupported resolved"):
            plan_damage_result_commit(engine, invalid)
        self.assertEqual(before, authoritative_state_hash(engine.state))

    def test_damage_results_property_1000_deterministic_transitions(self):
        engine = self.session(120_400_005).engine
        for index in range(1_000):
            amount = index % 7 + 1
            infect = index % 2 == 0
            lifelink = index % 3 == 0
            toxic = index % 5 == 0
            keywords = [
                keyword
                for enabled, keyword in (
                    (infect, "infect"),
                    (lifelink, "lifelink"),
                    (toxic, "toxic"),
                )
                if enabled
            ]
            event = ReplaceableEvent(
                event_id=f"damage:property:{index}",
                kind="damage",
                affected_player="B",
                payload={
                    "amount": amount,
                    "target_kind": "player",
                    "target": "B",
                    "source": "S-property",
                    "source_controller": "A",
                    "source_logical_object_id": "logical:property",
                    "source_types": ["creature"],
                    "source_keywords": keywords,
                    "source_toxic_value": 2 if toxic else 0,
                    "combat": toxic,
                },
            )
            before = (
                engine.state.players["A"].life,
                engine.state.players["B"].life,
                engine.state.players["B"].poison,
            )
            prepared = prepare_damage_results(engine, (event,), effects=())
            plan = plan_damage_result_commit(engine, prepared)
            self.assertEqual(
                before,
                (
                    engine.state.players["A"].life,
                    engine.state.players["B"].life,
                    engine.state.players["B"].poison,
                ),
            )
            commit_damage_result_plan(engine, plan)
            self.assertEqual(
                before[0] + (amount if lifelink else 0),
                engine.state.players["A"].life,
            )
            self.assertEqual(
                before[1] - (0 if infect else amount),
                engine.state.players["B"].life,
            )
            self.assertEqual(
                before[2] + (amount if infect else 0) + (2 if toxic else 0),
                engine.state.players["B"].poison,
            )


if __name__ == "__main__":
    unittest.main()
