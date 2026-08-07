from __future__ import annotations

import copy
import contextlib
import io
import json
import tempfile
import tomllib
import unittest
from pathlib import Path

from common import DB_PATH, keep_all, load_assets, make_session
from quorune import __version__
from quorune.arena import (
    CodexThreadRegistry,
    CoordinatorTools,
    PILOT_TOOL_NAMES,
    PilotInvocationIdentity,
    SeatScopedPilotTools,
    primary_session_prompt,
)
from quorune.bulk import SCRYFALL_USER_AGENT
from quorune.cli import build_parser, main as cli_main
from quorune.deck import DeckDefinition
from quorune.profiles import DeckProfileCache
from quorune.record import ENGINE_VERSION
from quorune.session import CommanderSession


class CodexArenaBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_runtime_and_distribution_versions_match(self):
        project = tomllib.loads(
            (Path(__file__).parents[1] / "pyproject.toml").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("quorune", project["project"]["name"])
        self.assertEqual(project["project"]["version"], __version__)
        self.assertEqual(__version__, ENGINE_VERSION)
        self.assertIn(f"/{__version__} ", SCRYFALL_USER_AGENT)
        self.assertEqual(
            {
                "quorune": "quorune.cli:main",
                "simctl": "quorune.cli:main",
                "quorune-server": "server.__main__:main",
            },
            project["project"]["scripts"],
        )
        root = Path(__file__).parents[1]
        self.assertTrue((root / "quorune" / "__init__.py").is_file())
        self.assertFalse((root / "mtg_commander_sim").exists())

    def test_primary_command_help_uses_quorune_name(self):
        self.assertTrue(
            build_parser(prog="quorune").format_usage().startswith(
                "usage: quorune"
            )
        )

    def test_pilot_parent_responses_forbid_private_packet_echoes(self):
        root = Path(__file__).parents[1]
        required = (
            "Never echo private task data",
            "accepted decision IDs",
            "principal boundary",
            "sanitized error code/message",
        )
        for seat in "abcd":
            config = tomllib.loads(
                (
                    root / ".codex" / "agents" / f"quorune-pilot-{seat}.toml"
                ).read_text(encoding="utf-8")
            )
            instructions = config["developer_instructions"]
            for phrase in required:
                self.assertIn(phrase, instructions)
            self.assertEqual("low", config["model_reasoning_effort"])
            self.assertEqual("priority", config["service_tier"])
        skill = (
            root / ".agents" / "skills" / "quorune-pilot-harness" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("parent-message channel", skill)
        self.assertIn("fidelity failure", skill)

    def test_exact_profile_fingerprint_acceptance_and_mismatch_warning(self):
        cache = DeckProfileCache()
        exact = cache.load_validated(self.zimone)
        self.assertEqual("exact", exact.status)
        self.assertTrue(exact.profile_fingerprint_match)
        self.assertIsNotNone(exact.profile)

        changed = DeckDefinition.from_dict(self.zimone.to_dict())
        changed.entries[0].quantity += 1
        missing = cache.load_validated(changed)
        self.assertEqual("missing", missing.status)
        self.assertFalse(missing.profile_fingerprint_match)
        self.assertIsNone(missing.profile)

        fallback = cache.load_validated(
            changed, allow_commander_fallback=True
        )
        self.assertEqual("commander_fallback", fallback.status)
        self.assertFalse(fallback.profile_fingerprint_match)
        self.assertIn("not exact-list", fallback.warning)

    def test_profile_validation_survives_record_reload(self):
        session = make_session(
            self.db, self.mishra, self.zimone, players=2, seed=411
        )
        with tempfile.TemporaryDirectory() as temporary:
            game_dir = Path(temporary) / "game"
            session.save(game_dir)
            reloaded = CommanderSession.load(
                self.db,
                game_dir,
                semantics_path=game_dir / "semantics.json",
            )
            reloaded.save(game_dir)
            manifest = json.loads(
                (game_dir / "manifest.json").read_text(encoding="utf-8")
            )
        self.assertTrue(manifest["profile_fingerprint_match"])
        self.assertTrue(
            all(
                player["profile_validation"][
                    "profile_fingerprint_match"
                ]
                for player in manifest["players"]
            )
        )

    def test_fixed_seat_task_has_no_capability_and_never_routes_other_seat(self):
        session = make_session(
            self.db, self.mishra, self.zimone, seed=401
        )
        tools_a = SeatScopedPilotTools(session, "A")
        tools_b = SeatScopedPilotTools(session, "B")

        task_a = tools_a.get_task()
        self.assertIsNotNone(task_a)
        self.assertNotIn("cap", task_a["decision"])
        self.assertIsNone(tools_b.get_task())

    def test_tool_surface_has_no_checkpoint_or_analyst_access(self):
        session = make_session(
            self.db, self.mishra, self.zimone, seed=402
        )
        tools = SeatScopedPilotTools(session, "A")
        self.assertEqual(PILOT_TOOL_NAMES, tools.tool_names())
        self.assertFalse(hasattr(tools, "get_checkpoint"))
        self.assertFalse(hasattr(tools, "get_analyst_data"))

        opposing_hand = session.state.players["B"].zones["hand"][0]
        opposing_ref = session.state.cards[opposing_hand].ref
        own_library = session.state.players["A"].zones["library"][0]
        own_library_ref = session.state.cards[own_library].ref
        with self.assertRaises(PermissionError):
            tools.get_rules([opposing_ref])
        with self.assertRaises(PermissionError):
            tools.get_rules([own_library_ref])

        own_hand = session.state.players["A"].zones["hand"][0]
        own_hand_ref = session.state.cards[own_hand].ref
        self.assertTrue(tools.get_rules([own_hand_ref]))

    def test_pilot_cannot_forge_identity_or_another_seat(self):
        session = make_session(
            self.db, self.mishra, self.zimone, seed=403
        )
        identity = PilotInvocationIdentity(
            provider="trusted-test-provider",
            model="trusted-model",
            thread_id="thread-a",
            thread_label="quorune-pilot-a",
            provider_invoked=True,
        )
        tools = SeatScopedPilotTools(session, "A", identity=identity)
        forged = tools.submit_action(
            {
                "action_id": "keep",
                "seat": "B",
                "provider": "codex_subagent",
            }
        )
        self.assertFalse(forged["accepted"])
        self.assertEqual(1, len(session.decisions))
        self.assertFalse(session.decisions[-1]["accepted"])
        self.assertIn("transport/authority", session.decisions[-1]["rejection"])

        accepted = tools.submit_action(
            {
                "action_id": "keep",
                "plan": "MULLIGAN",
                "reason": "Keep this functional opening hand.",
            }
        )
        self.assertTrue(accepted["accepted"])
        row = session.decisions[-1]
        self.assertEqual("trusted-test-provider", row["provider"])
        self.assertEqual("trusted-model", row["model"])
        self.assertEqual("thread-a", row["thread_id"])

    def test_fixed_seat_tool_accepts_ordered_pilot_response_schema(self):
        session = make_session(
            self.db, self.mishra, self.zimone, seed=406
        )
        tools = SeatScopedPilotTools(session, "A")
        accepted = tools.submit_action(
            {
                "actions": [{"action_id": "keep"}],
                "plan": "MULLIGAN",
                "reason": "Keep a functional opening hand.",
                "confidence": 0.8,
            }
        )
        self.assertTrue(accepted["accepted"], accepted["error"])
        self.assertEqual("keep", session.decisions[-1]["action"])

    def test_ordered_plan_survives_fixed_seat_process_reload(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=410,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.started = True
        engine.state.turn_sequence = 1
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.phase_index = 3
        engine.state.players["A"].land_plays_remaining = 1
        engine.state.stack = []
        engine._grant_priority("A")
        engine.pump()

        with tempfile.TemporaryDirectory() as temporary:
            game_dir = Path(temporary) / "game"
            session.save(game_dir)
            first_process = SeatScopedPilotTools.open(
                game_dir=game_dir,
                db_path=DB_PATH,
                seat="A",
            )
            task = first_process.get_task()
            land = next(
                item
                for item in task["decision"]["legal_actions"]
                if item["action"] == "play_land"
                and item["label"] == "Play Mana Confluence"
            )
            accepted = first_process.submit_action(
                {
                    "actions": [
                        {"action_id": land["id"]},
                        {"action_id": "pass"},
                    ],
                    "plan": "DEVELOP_MANA",
                    "reason": "Play a land, then pass unchanged priority.",
                    "confidence": 0.8,
                }
            )
            self.assertTrue(accepted["accepted"], accepted["error"])
            self.assertTrue(
                json.loads(
                    (game_dir / "plans.json").read_text(encoding="utf-8")
                )["pilot:A"]
            )

            second_process = SeatScopedPilotTools.open(
                game_dir=game_dir,
                db_path=DB_PATH,
                seat="A",
            )
            self.assertIsNone(second_process.get_task())
            restored = second_process._session
            self.assertEqual(
                "planned_automatic",
                restored.commands[-1]["execution"],
            )
            self.assertNotIn("pilot:A", restored.plans)

    def test_nested_transport_identity_is_rejected(self):
        session = make_session(
            self.db, self.mishra, self.zimone, seed=407
        )
        tools = SeatScopedPilotTools(session, "A")
        result = tools.submit_action(
            {
                "action_id": "keep",
                "choices": {"provider": "forged"},
                "plan": "MULLIGAN",
            }
        )
        self.assertFalse(result["accepted"])
        self.assertIn("$.choices.provider", result["error"])

    def test_codex_response_requires_auditable_reason_and_confidence(self):
        session = make_session(
            self.db, self.mishra, self.zimone, seed=408
        )
        tools = SeatScopedPilotTools(
            session,
            "A",
            identity=PilotInvocationIdentity(
                provider="codex_subagent",
                model="gpt-5.6-sol",
                reasoning_effort="max",
                thread_id="thread-a",
                thread_label="quorune-pilot-a",
                provider_invoked=True,
            ),
        )
        result = tools.submit_action(
            {"action_id": "keep", "plan": "MULLIGAN"}
        )
        self.assertFalse(result["accepted"])
        self.assertIn("reason", result["error"])
        self.assertIn("confidence", result["error"])

    def test_codex_submission_requires_invocation_evidence(self):
        session = make_session(
            self.db, self.mishra, self.zimone, seed=412
        )
        tools = SeatScopedPilotTools(
            session,
            "A",
            identity=PilotInvocationIdentity(
                provider="codex_subagent",
                model="gpt-5.6-sol",
                reasoning_effort="max",
                thread_id="/root/pilot-a",
                thread_label="quorune-pilot-a",
                provider_invoked=False,
            ),
        )
        result = tools.submit_action(
            {
                "action_id": "keep",
                "plan": "MULLIGAN",
                "reason": "Keep a functional opening hand.",
                "confidence": 0.8,
            }
        )
        self.assertFalse(result["accepted"])
        self.assertIn("--provider-invoked", result["error"])
        self.assertFalse(session.decisions[-1]["provider_invoked"])

    def test_codex_submission_rejects_dropped_thread_identity(self):
        session = make_session(
            self.db, self.mishra, self.zimone, seed=413
        )
        session.decisions.append(
            {
                "principal": "pilot:A",
                "provider": "codex_subagent",
                "model": "gpt-5.6-sol",
                "reasoning_effort": "max",
                "thread_id": "/root/pilot-a",
                "thread_label": "quorune-pilot-a",
                "provider_invoked": True,
                "provider_identity_verified": True,
                "model_identity_verified": True,
            }
        )
        tools = SeatScopedPilotTools(
            session,
            "A",
            identity=PilotInvocationIdentity(
                provider="codex_subagent",
                model="gpt-5.6-sol",
                reasoning_effort="max",
                thread_id=None,
                thread_label="quorune-pilot-a",
                provider_invoked=True,
                provider_identity_verified=True,
                model_identity_verified=True,
            ),
        )
        result = tools.submit_action(
            {
                "action_id": "keep",
                "plan": "MULLIGAN",
                "reason": "Keep a functional opening hand.",
                "confidence": 0.8,
            }
        )
        self.assertFalse(result["accepted"])
        self.assertIn("thread_id", result["error"])

    def test_primary_prompt_requires_full_identity_on_every_submission(self):
        prompt = primary_session_prompt("run/test")
        self.assertIn("every submit-action invocation", prompt)
        self.assertIn("never shorten that command", prompt)
        self.assertIn("semantic_policy is trusted_only", prompt)

    def test_arena_create_defaults_to_trusted_only_semantics(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "arena"
            zimone = Path(__file__).parents[1] / "examples" / "zimone-and-dina.txt"
            mishra = Path(__file__).parents[1] / "examples" / "mishra-eminent-one.txt"
            with contextlib.redirect_stdout(io.StringIO()):
                result = cli_main(
                    [
                        "arena-create",
                        "--db",
                        str(DB_PATH),
                        "--deck",
                        f"A={zimone}",
                        "--deck",
                        f"B={mishra}",
                        "--deck",
                        f"C={zimone}",
                        "--deck",
                        f"D={mishra}",
                        "--output",
                        str(output),
                        "--seed",
                        "414",
                    ]
                )
            self.assertEqual(0, result)
            checkpoint = json.loads(
                (output / "checkpoint.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                "trusted_only",
                checkpoint["state"]["config"]["semantic_policy"],
            )

    def test_pilot_memory_is_seat_isolated(self):
        session = make_session(
            self.db, self.mishra, self.zimone, seed=404
        )
        with tempfile.TemporaryDirectory() as temporary:
            game_dir = Path(temporary) / "game"
            session.save(game_dir)
            tools_a = SeatScopedPilotTools.open(
                game_dir=game_dir, db_path=DB_PATH, seat="A"
            )
            tools_b = SeatScopedPilotTools.open(
                game_dir=game_dir, db_path=DB_PATH, seat="B"
            )
            tools_a.update_memory("A-only strategy")
            tools_b.update_memory("B-only strategy")
            self.assertEqual("A-only strategy", tools_a.get_memory())
            self.assertEqual("B-only strategy", tools_b.get_memory())

    def test_four_persistent_labels_and_honest_unavailable_metadata(self):
        registry = CodexThreadRegistry(parent_session_id=None)
        for seat in "ABCD":
            registry.register(
                seat=seat,
                thread_label=f"quorune-pilot-{seat.lower()}",
                provider="codex_subagent",
                model="gpt-5.6-sol",
                reasoning_effort="max",
                thread_id=None,
            )
        metadata = registry.metadata()
        self.assertEqual(4, metadata["pilot_thread_count"])
        self.assertFalse(metadata["codex_subagent_run"])
        self.assertFalse(metadata["provider_identity_verified"])
        self.assertFalse(metadata["model_identity_verified"])
        self.assertFalse(metadata["nested_pilot_subagents"])

    def test_thread_registry_reconstructs_actual_persistent_decisions(self):
        decisions = []
        for seat in "ABCD":
            for index in range(2):
                decisions.append(
                    {
                        "principal": f"pilot:{seat}",
                        "provider": "codex_subagent",
                        "model": "gpt-5.6-sol",
                        "reasoning_effort": "max",
                        "thread_id": f"thread-{seat}",
                        "thread_label": f"quorune-pilot-{seat.lower()}",
                        "provider_invoked": True,
                        "retry_count": index,
                        "accepted": index != 0,
                        "invoked_at": f"2026-07-28T00:00:0{index}+00:00",
                    }
                )
        metadata = CodexThreadRegistry.from_decisions(decisions).metadata()
        self.assertTrue(metadata["codex_subagent_run"])
        self.assertTrue(metadata["persistent_thread_reuse"])
        self.assertTrue(metadata["provider_identity_verified"])
        self.assertTrue(metadata["model_identity_verified"])
        self.assertEqual(4, metadata["pilot_thread_count"])
        self.assertEqual(1, metadata["threads"][0]["retries"])

    def test_duplicate_thread_or_parent_seat_submission_is_rejected(self):
        registry = CodexThreadRegistry()
        registry.register(
            seat="A",
            thread_label="quorune-pilot-a",
            provider="codex_subagent",
            model="gpt-5.6-sol",
            reasoning_effort="max",
            thread_id="same-thread",
        )
        with self.assertRaises(ValueError):
            registry.register(
                seat="B",
                thread_label="quorune-pilot-b",
                provider="codex_subagent",
                model="gpt-5.6-sol",
                reasoning_effort="max",
                thread_id="same-thread",
            )

        session = make_session(
            self.db, self.mishra, self.zimone, seed=405
        )
        coordinator = CoordinatorTools(session)
        self.assertFalse(hasattr(coordinator, "submit_action"))
        self.assertFalse(
            coordinator.submit_arbiter({"action_id": "keep"})["accepted"]
        )

    def test_duplicated_four_player_fixture_is_not_matchup_evidence(self):
        session = make_session(
            self.db, self.mishra, self.zimone, seed=409
        )
        with tempfile.TemporaryDirectory() as temporary:
            game_dir = Path(temporary) / "duplicate-fixture"
            session.save(game_dir)
            review = json.loads(
                (game_dir / "review.json").read_text(encoding="utf-8")
            )
        self.assertFalse(review["fidelity"]["matchup_evidence"])
        self.assertIn(
            "duplicated-deck protocol fixture is not matchup evidence",
            review["fidelity"]["failures"],
        )


if __name__ == "__main__":
    unittest.main()
