from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common import DB_PATH, load_assets, make_session
from mtg_commander_sim.arena import (
    PilotInvocationIdentity,
    SeatScopedPilotTools,
    _record_lock,
    _tool_specs,
)
from mtg_commander_sim.record import (
    finalize_record,
    provider_telemetry,
    refresh_record,
    verify_record_integrity,
)
from mtg_commander_sim.model import Event
from mtg_commander_sim.report import _semantic_coverage, derive_review


class RecordLifecycleAndTypedToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    @staticmethod
    def _identity(seat: str):
        return PilotInvocationIdentity(
            provider="codex_subagent",
            model="gpt-5.6-sol",
            reasoning_effort="max",
            thread_id=f"/root/test-pilot-{seat.lower()}",
            thread_label=f"mtg-pilot-{seat.lower()}",
            provider_invoked=True,
            provider_identity_verified=True,
            model_identity_verified=True,
            model_configured="gpt-5.6-sol",
            reasoning_effort_configured="max",
        )

    def test_builtin_shockland_entry_is_trusted_in_coverage_report(self):
        session = make_session(
            self.db, self.mishra, self.zimone, players=2, seed=419
        )
        steam_vents = next(
            card
            for card in session.engine.state.cards.values()
            if card.printed_name == "Steam Vents"
        )
        session.engine.state.events.append(
            Event(
                event_id=1,
                revision=0,
                turn_sequence=1,
                active_player=steam_vents.owner,
                phase="main",
                step="precombat_main",
                actor=steam_vents.owner,
                code="land.play",
                summary="played Steam Vents",
                details={"object": steam_vents.ref, "tapped": True},
            )
        )
        coverage = _semantic_coverage(session.engine)
        row = next(
            card
            for card in coverage["cards"]
            if card["name"] == "Steam Vents"
        )
        self.assertEqual("fully_supported", row["status"])
        self.assertEqual("trusted", row["trust_level"])
        self.assertEqual("complete", coverage["status"])

    def test_builtin_mana_side_effect_is_trusted_in_coverage_report(self):
        session = make_session(
            self.db, self.mishra, self.zimone, players=2, seed=420
        )
        elves = next(
            card
            for card in session.engine.state.cards.values()
            if card.printed_name == "Elves of Deep Shadow"
        )
        session.engine.state.events.append(
            Event(
                event_id=1,
                revision=0,
                turn_sequence=1,
                active_player=elves.owner,
                phase="main",
                step="precombat_main",
                actor=elves.owner,
                code="stack.cast",
                summary="cast Elves of Deep Shadow",
                details={"object": elves.ref},
            )
        )
        coverage = _semantic_coverage(session.engine)
        row = next(
            card
            for card in coverage["cards"]
            if card["name"] == "Elves of Deep Shadow"
        )
        self.assertEqual("fully_supported", row["status"])
        self.assertEqual("trusted", row["trust_level"])
        self.assertEqual("complete", coverage["status"])

    def test_typed_schema_enforces_plan_and_reason_bounds(self):
        spec = next(
            item for item in _tool_specs() if item["name"] == "submit_action"
        )
        schema = spec["inputSchema"]
        self.assertEqual(
            [
                "MULLIGAN",
                "DEVELOP_MANA",
                "FIX_COLORS",
                "DEVELOP_ENGINE",
                "HOLD_INTERACTION",
                "DISRUPT_LEADER",
                "PROTECT_ENGINE",
                "ASSEMBLE_WIN",
                "PRESSURE_PLAYER",
                "RECOVER",
                "PASS_WITH_YIELD",
            ],
            schema["properties"]["plan"]["enum"],
        )
        self.assertEqual(
            180, schema["properties"]["reason"]["maxLength"]
        )
        self.assertNotIn("response", schema["properties"])

    def test_reason_rejected_before_mutation_and_mulligan_yield_stripped(self):
        session = make_session(
            self.db, self.mishra, self.zimone, seed=620
        )
        tools = SeatScopedPilotTools(
            session, "A", identity=self._identity("A")
        )
        before = session.state.revision
        rejected = tools.submit_action(
            {
                "action_id": "keep",
                "plan": "MULLIGAN",
                "reason": "x" * 181,
                "confidence": 0.9,
            }
        )
        self.assertFalse(rejected["accepted"])
        self.assertEqual(before, session.state.revision)
        accepted = tools.submit_action(
            {
                "action_id": "keep",
                "plan": "MULLIGAN",
                "reason": "Keep a functional opening hand.",
                "confidence": 0.9,
                "yield_mode": "until_public_change",
            }
        )
        self.assertTrue(accepted["accepted"], accepted["error"])
        self.assertNotIn("yield", session.commands[-1]["payload"])

    def test_retries_group_under_decision_without_erasing_legal_trace(self):
        session = make_session(
            self.db, self.mishra, self.zimone, seed=621
        )
        tools = SeatScopedPilotTools(
            session, "A", identity=self._identity("A")
        )
        decision_id = session.state.pending_decision.decision_id
        rejected = tools.submit_action(
            {
                "action_id": "keep",
                "plan": "mulligan",
                "reason": "Invalid enum casing.",
                "confidence": 0.8,
            }
        )
        self.assertFalse(rejected["accepted"])
        accepted = tools.submit_action(
            {
                "action_id": "keep",
                "plan": "MULLIGAN",
                "reason": "Keep the functional seven.",
                "confidence": 0.8,
            }
        )
        self.assertTrue(accepted["accepted"])
        rows = [
            row
            for row in session.decisions
            if row.get("decision_id") == decision_id
        ]
        self.assertEqual(2, len(rows))
        self.assertTrue(all(row["legal_alternatives"] for row in rows))
        metrics = provider_telemetry(session.decisions, session.commands)
        self.assertEqual(2, metrics["provider_calls_attempted"])
        self.assertEqual(1, metrics["retry_provider_calls"])
        self.assertEqual(1, metrics["game_decisions_created"])
        review = derive_review(
            session.engine,
            decisions=session.decisions,
            manifest={
                "replay": {"verification": "not_run"},
                "provider_telemetry": metrics,
            },
        )
        self.assertTrue(review["pilot_audit"]["complete_alternatives"])
        self.assertTrue(review["pilot_audit"]["complete_reasons"])

    def test_manifest_reconstructed_and_contradiction_detected(self):
        session = make_session(
            self.db, self.mishra, self.zimone, seed=622
        )
        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "record"
            for seat in "ABCD":
                if f"pilot:{seat}" not in session.pending_principals():
                    break
                tools = SeatScopedPilotTools(
                    session, seat, identity=self._identity(seat)
                )
                result = tools.submit_action(
                    {
                        "action_id": "keep",
                        "plan": "MULLIGAN",
                        "reason": "Keep the functional opening hand.",
                        "confidence": 0.9,
                    }
                )
                self.assertTrue(result["accepted"])
            session.save(record)
            manifest = json.loads(
                (record / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                4,
                manifest["provider_telemetry"][
                    "provider_calls_attempted"
                ],
            )
            self.assertTrue(
                manifest["codex_arena"]["codex_subagent_run_recorded"]
            )
            self.assertEqual(
                4, manifest["codex_arena"]["unique_pilot_threads"]
            )
            self.assertTrue(
                manifest["codex_arena"]["provider_identity_verified"]
            )

            manifest["codex_arena"]["unique_pilot_threads"] = 0
            (record / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            integrity = verify_record_integrity(
                record, self.db, replay=False
            )
            self.assertFalse(integrity["ok"])
            self.assertTrue(
                any(
                    "unique_pilot_threads" in error
                    for error in integrity["errors"]
                )
            )
            refreshed = refresh_record(record, self.db)
            self.assertEqual(
                4,
                refreshed["codex_arena"]["unique_pilot_threads"],
            )

    def test_paused_reason_prefix_replay_and_partial_review(self):
        session = make_session(
            self.db, self.mishra, self.zimone, seed=623
        )
        self.assertTrue(
            session.act(
                "pilot:A",
                {
                    "action_id": "keep",
                    "plan": "MULLIGAN",
                    "reason": "Keep a functional hand.",
                },
            ).ok
        )
        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "paused"
            session.save(record)
            finalized = finalize_record(record, self.db)
            self.assertEqual("paused", finalized["status"])
            self.assertEqual(
                "pilot_required",
                finalized["pause_reason"]["kind"],
            )
            self.assertEqual(
                "pass", finalized["replay"]["verification"]
            )
            manifest = json.loads(
                (record / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                "accepted_command_prefix",
                manifest["replay"]["scope"],
            )
            self.assertEqual(
                manifest["pause_reason"],
                manifest["codex_arena"]["stop_reason"],
            )
            benchmark = json.loads(
                (record / "call-benchmark.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                len(session.commands),
                benchmark["provider_telemetry"]["accepted_commands"],
            )
            hidden_audit = json.loads(
                (record / "hidden-information-audit.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertTrue(hidden_audit["seat_projection_verified"])
            review = json.loads(
                (record / "review.json").read_text(encoding="utf-8")
            )
            self.assertEqual("paused", review["outcome"]["status"])
            self.assertFalse(review["fidelity"]["matchup_evidence"])
            integrity = verify_record_integrity(record, self.db)
            self.assertTrue(integrity["ok"], integrity["errors"])

    def test_stale_one_byte_arena_lock_is_recovered(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / ".arena.lock").write_bytes(b"0")
            with _record_lock(directory):
                pass
            released = json.loads(
                (directory / ".arena.lock").read_text(encoding="utf-8")
            )
            self.assertFalse(released["active"])
            self.assertTrue(released["recovered_from_stale"])

    def test_explicit_pause_reason_survives_finalization(self):
        session = make_session(
            self.db, self.mishra, self.zimone, seed=624
        )
        session.pause(
            {
                "kind": "fidelity_failure",
                "label": "Targeted spell advertised without a legal target.",
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "explicit-pause"
            session.save(record)
            finalized = finalize_record(record, self.db)
            self.assertEqual(
                "fidelity_failure",
                finalized["pause_reason"]["kind"],
            )
            self.assertEqual(
                finalized["pause_reason"],
                finalized["codex_arena"]["stop_reason"],
            )


if __name__ == "__main__":
    unittest.main()
