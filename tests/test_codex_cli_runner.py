from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from common import DB_PATH, load_assets, make_session
from mtg_commander_sim.codex_cli import (
    CodexCliArenaRunner,
    CodexCliError,
    CodexExecClient,
    CodexTurnResult,
)
from mtg_commander_sim.record import verify_record_suffix
from mtg_commander_sim.session import CommanderSession
from mtg_commander_sim.util import stable_json


class FakeCodexClient:
    provider_identity_verified = False
    model_identity_verified = False
    provider_version = None

    def __init__(self, *, forbidden_tool: bool = False):
        self.starts: list[str] = []
        self.resumes: list[str] = []
        self._by_thread: dict[str, str] = {}
        self._seat_calls: dict[str, int] = {}
        self.forbidden_tool = forbidden_tool

    def start(
        self,
        seat: str,
        prompt: str,
        *,
        timeout: float,
    ) -> CodexTurnResult:
        self.starts.append(seat)
        thread_id = f"fake-thread-{seat}"
        self._by_thread[thread_id] = seat
        return CodexTurnResult(
            thread_id=thread_id,
            message=stable_json({"status": "ready", "seat": seat}),
            input_tokens=10,
            cached_input_tokens=0,
            output_tokens=4,
            reasoning_output_tokens=0,
            latency_ms=5,
        )

    def resume(
        self,
        thread_id: str,
        prompt: str,
        *,
        response_schema: Path,
        timeout: float,
    ) -> CodexTurnResult:
        seat = self._by_thread[thread_id]
        self.resumes.append(thread_id)
        call = self._seat_calls.get(seat, 0)
        self._seat_calls[seat] = call + 1
        action = "mulligan" if seat == "D" and call == 0 else "keep"
        return CodexTurnResult(
            thread_id=thread_id,
            message=stable_json(
                {
                    "action_id": action,
                    "actions": [],
                    "choices_json": "{}",
                    "plan": "MULLIGAN",
                    "reason": "Exercise the persistent fixed-seat transport.",
                    "confidence": 0.8,
                    "yield": None,
                    "memory_update": f"{seat} memory",
                }
            ),
            input_tokens=100 + call,
            cached_input_tokens=20,
            output_tokens=25,
            reasoning_output_tokens=3,
            latency_ms=7,
            tool_calls=("shell",) if self.forbidden_tool else (),
        )


class CodexCliArenaRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def _record(self, root: Path, *, seed: int) -> Path:
        record = root / "arena"
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            seed=seed,
            auto_pass_empty=True,
        )
        session.state.config.semantic_policy = "trusted_only"
        session.initial_checkpoint = {}
        session.save(record)
        return record

    def test_four_fast_sessions_are_persistent_and_usage_is_provider_owned(self):
        with tempfile.TemporaryDirectory() as temporary:
            record = self._record(Path(temporary), seed=801)
            client = FakeCodexClient()
            runner = CodexCliArenaRunner(
                game_dir=record,
                db_path=DB_PATH,
                client=client,
                parent_session_id="parent-test",
                max_retries=1,
            )
            result = runner.run(
                through_turn=1,
                max_invocations=10,
                verify_replay=True,
            )
            self.assertEqual("turn_limit", result["stop_reason"])
            self.assertEqual("in_progress", result["record_status"])
            self.assertTrue(result["replay"]["ok"], result["replay"])
            self.assertEqual(4, result["pilot_thread_count"])
            self.assertEqual(0, result["suppressed_meaningful_windows"])
            self.assertCountEqual(list("ABCD"), client.starts)
            self.assertEqual(5, len(client.resumes))
            self.assertEqual(2, client.resumes.count("fake-thread-D"))

            reloaded = CommanderSession.load(
                self.db,
                record,
                semantics_path=record / "semantics.json",
            )
            actual = [
                row
                for row in reloaded.decisions
                if row.get("provider_invoked")
            ]
            self.assertEqual(5, len(actual))
            for seat in "ABCD":
                self.assertEqual(
                    {f"fake-thread-{seat}"},
                    {
                        row["thread_id"]
                        for row in actual
                        if row["seat"] == seat
                    },
                )
            self.assertTrue(all(row["accepted"] for row in actual))
            self.assertTrue(
                all(
                    row["metrics"]["reasoning_output_tokens"] == 3
                    for row in actual
                )
            )
            self.assertTrue(
                all(
                    row["metrics"]["cached_input_tokens"] == 20
                    for row in actual
                )
            )
            self.assertEqual(
                "D memory",
                json.loads(
                    (
                        record / "pilot-seat-memory" / "D.json"
                    ).read_text(encoding="utf-8")
                )["text"],
            )

            second = CodexCliArenaRunner(
                game_dir=record,
                db_path=DB_PATH,
                client=client,
                parent_session_id="parent-test",
            )
            second.ensure_sessions()
            self.assertEqual(4, len(client.starts))

    def test_forbidden_pilot_tool_pauses_without_submitting(self):
        with tempfile.TemporaryDirectory() as temporary:
            record = self._record(Path(temporary), seed=802)
            client = FakeCodexClient(forbidden_tool=True)
            runner = CodexCliArenaRunner(
                game_dir=record,
                db_path=DB_PATH,
                client=client,
            )
            with self.assertRaises(CodexCliError):
                runner.run(
                    through_turn=1,
                    max_invocations=1,
                    verify_replay=False,
                )
            reloaded = CommanderSession.load(
                self.db,
                record,
                semantics_path=record / "semantics.json",
            )
            self.assertEqual("paused", reloaded.record_status)
            self.assertEqual("codex_transport", reloaded.pause_reason["kind"])
            self.assertFalse(reloaded.decisions)

    def test_verified_resume_replays_only_the_new_command_suffix(self):
        with tempfile.TemporaryDirectory() as temporary:
            record = self._record(Path(temporary), seed=8021)
            client = FakeCodexClient()
            first = CodexCliArenaRunner(
                game_dir=record,
                db_path=DB_PATH,
                client=client,
            )
            first_result = first.run(
                through_turn=0,
                max_invocations=1,
                verify_replay=True,
            )
            self.assertTrue(first_result["replay"]["ok"])
            self.assertEqual(1, first_result["replay"]["commands"])

            second = CodexCliArenaRunner(
                game_dir=record,
                db_path=DB_PATH,
                client=client,
            )
            with mock.patch(
                "mtg_commander_sim.codex_cli.refresh_record",
                side_effect=AssertionError(
                    "verified resume must not replay the initial prefix"
                ),
            ), mock.patch(
                "mtg_commander_sim.codex_cli.verify_record_suffix",
                wraps=verify_record_suffix,
            ) as suffix_replay:
                second_result = second.run(
                    through_turn=0,
                    max_invocations=1,
                    verify_replay=True,
                )

            suffix_replay.assert_called_once()
            self.assertTrue(second_result["replay"]["ok"])
            self.assertEqual(2, second_result["replay"]["commands"])
            self.assertEqual(1, second_result["replay"]["suffix_commands"])
            self.assertEqual(
                "verified_prefix_suffix",
                second_result["replay"]["verification_strategy"],
            )
            manifest = json.loads(
                (record / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual("pass", manifest["replay"]["verification"])
            self.assertEqual(2, manifest["replay"]["verified_commands"])
            self.assertEqual(
                "verified_prefix_suffix",
                manifest["replay"]["verification_strategy"],
            )

    def test_suffix_replay_rejects_a_tampered_verified_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            record = self._record(Path(temporary), seed=8022)
            client = FakeCodexClient()
            first = CodexCliArenaRunner(
                game_dir=record,
                db_path=DB_PATH,
                client=client,
            )
            first.run(
                through_turn=0,
                max_invocations=1,
                verify_replay=True,
            )

            second = CodexCliArenaRunner(
                game_dir=record,
                db_path=DB_PATH,
                client=client,
            )
            baseline = second._verified_replay_baseline()
            self.assertIsNotNone(baseline)
            baseline_state, baseline_commands = baseline
            second.run(
                through_turn=0,
                max_invocations=1,
                verify_replay=False,
            )

            tampered = copy.deepcopy(baseline_state)
            tampered["players"]["A"]["life"] -= 1
            with self.assertRaisesRegex(
                ValueError,
                "baseline does not match",
            ):
                verify_record_suffix(
                    record,
                    self.db,
                    baseline_state=tampered,
                    baseline_commands=baseline_commands,
                )

    def test_replay_failure_pauses_and_disqualifies_the_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            record = self._record(Path(temporary), seed=803)
            client = FakeCodexClient()
            runner = CodexCliArenaRunner(
                game_dir=record,
                db_path=DB_PATH,
                client=client,
            )
            with mock.patch(
                "mtg_commander_sim.codex_cli.refresh_record",
                side_effect=ValueError("replay divergence"),
            ):
                with self.assertRaisesRegex(
                    CodexCliError,
                    "Exact command replay failed",
                ):
                    runner.run(
                        through_turn=1,
                        max_invocations=10,
                        verify_replay=True,
                    )
            reloaded = CommanderSession.load(
                self.db,
                record,
                semantics_path=record / "semantics.json",
            )
            self.assertEqual("paused", reloaded.record_status)
            self.assertEqual(
                "command_replay",
                reloaded.pause_reason["kind"],
            )
            benchmark = json.loads(
                (record / "codex-cli-benchmark.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("command_replay", benchmark["stop_reason"])

    def test_response_envelope_decodes_choices_but_rejects_two_action_modes(self):
        decision_prompt = CodexCliArenaRunner._decision_prompt(
            "A",
            {"decision": {"kind": "semantic.choice"}},
            profile=None,
            memory="",
        )
        self.assertIn('shape "object_map"', decision_prompt)
        self.assertIn("top-first order", decision_prompt)
        self.assertIn('shape "ref_array"', decision_prompt)
        self.assertIn("never the display objects", decision_prompt)
        self.assertIn("legal_refs always means raw ref strings", decision_prompt)
        value = CodexCliArenaRunner.normalize_response(
            stable_json(
                {
                    "action_id": "play-land:A1",
                    "actions": [],
                    "choices_json": '{"entry_pay_life":true}',
                    "plan": "DEVELOP_MANA",
                    "reason": "Develop mana.",
                    "confidence": 0.9,
                    "yield": None,
                    "memory_update": "",
                }
            )
        )
        self.assertEqual("play-land:A1", value["action_id"])
        self.assertEqual({"entry_pay_life": True}, value["choices"])
        with self.assertRaises(CodexCliError):
            CodexCliArenaRunner.normalize_response(
                stable_json(
                    {
                        "action_id": "keep",
                        "actions": [
                            {"action_id": "keep", "choices_json": "{}"}
                        ],
                        "choices_json": "{}",
                        "plan": "MULLIGAN",
                        "reason": "Invalid dual mode.",
                        "confidence": 0.5,
                        "yield": None,
                        "memory_update": "",
                    }
                )
            )

    def test_exec_commands_enforce_low_priority_read_only_no_tools(self):
        client = object.__new__(CodexExecClient)
        client.executable = "codex"
        client.project_root = Path("C:/project")
        client.model = "gpt-5.6-sol"
        client.reasoning_effort = "low"
        client.service_tier = "priority"
        start = client.start_command()
        resume = client.resume_command(
            "thread-A",
            Path("C:/project/schema.json"),
        )
        for command in (start, resume):
            joined = " ".join(str(value) for value in command)
            self.assertIn('model_reasoning_effort="low"', joined)
            self.assertIn('service_tier="priority"', joined)
            self.assertIn('sandbox_mode="read-only"', joined)
            self.assertIn("features.multi_agent=false", joined)
            self.assertIn("features.shell_tool=false", joined)
            self.assertIn('approval_policy="never"', joined)


if __name__ == "__main__":
    unittest.main()
