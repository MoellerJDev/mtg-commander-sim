from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from .arena import PilotInvocationIdentity, SeatScopedPilotTools
from .carddb import CardDatabase
from .record import refresh_record, utc_now
from .session import CommanderSession
from .util import stable_json


CODEX_PILOT_SEATS = ("A", "B", "C", "D")
CODEX_PILOT_PROVIDER = "codex_subagent"


class CodexCliError(RuntimeError):
    """A fail-closed Codex transport or identity error."""


@dataclass(frozen=True, slots=True)
class CodexTurnResult:
    thread_id: str
    message: str
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    reasoning_output_tokens: int | None
    latency_ms: float
    tool_calls: tuple[str, ...] = ()


class CodexPilotClient(Protocol):
    provider_identity_verified: bool
    model_identity_verified: bool
    provider_version: str | None

    def start(self, seat: str, prompt: str, *, timeout: float) -> CodexTurnResult:
        ...

    def resume(
        self,
        thread_id: str,
        prompt: str,
        *,
        response_schema: Path,
        timeout: float,
    ) -> CodexTurnResult:
        ...


class CodexExecClient:
    """Noninteractive persistent Codex CLI transport with no pilot tools."""

    def __init__(
        self,
        *,
        project_root: str | Path,
        executable: str = "codex",
        model: str = "gpt-5.6-sol",
        reasoning_effort: str = "low",
        service_tier: str = "priority",
    ):
        resolved = shutil.which(executable)
        if resolved is None:
            raise CodexCliError(f"Codex executable not found: {executable!r}")
        self.executable = resolved
        self.project_root = Path(project_root).resolve()
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.service_tier = service_tier
        self.provider_version = self._read_version()
        self.provider_identity_verified = bool(
            self.provider_version
            and self.provider_version.lower().startswith("codex-cli ")
        )
        # The CLI invocation fixes the model explicitly on every turn. Codex
        # does not currently return a separate model identifier in its JSONL.
        self.model_identity_verified = self.provider_identity_verified

    def _read_version(self) -> str | None:
        result = subprocess.run(
            [self.executable, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        if result.returncode:
            return None
        return result.stdout.strip() or None

    def _config_args(self) -> list[str]:
        return [
            "-m",
            self.model,
            "-c",
            f'model_reasoning_effort="{self.reasoning_effort}"',
            "-c",
            f'service_tier="{self.service_tier}"',
            "-c",
            'approval_policy="never"',
            "-c",
            'sandbox_mode="read-only"',
            "-c",
            "features.multi_agent=false",
            "-c",
            "features.shell_tool=false",
            "-c",
            "features.apps=false",
        ]

    def start_command(self) -> list[str]:
        return [
            self.executable,
            "exec",
            "--json",
            "--ignore-user-config",
            *self._config_args(),
            "-s",
            "read-only",
            "-C",
            str(self.project_root),
            "-",
        ]

    def resume_command(
        self,
        thread_id: str,
        response_schema: Path,
    ) -> list[str]:
        return [
            self.executable,
            "exec",
            "resume",
            "--json",
            "--ignore-user-config",
            *self._config_args(),
            "--output-schema",
            str(response_schema.resolve()),
            thread_id,
            "-",
        ]

    @staticmethod
    def _tool_name(event: Mapping[str, Any]) -> str | None:
        item = event.get("item")
        if not isinstance(item, Mapping):
            return None
        item_type = str(item.get("type") or "")
        lowered = item_type.lower()
        if any(
            marker in lowered
            for marker in (
                "tool",
                "function_call",
                "command_execution",
                "mcp",
            )
        ):
            return str(
                item.get("tool")
                or item.get("name")
                or item.get("server")
                or item_type
            )
        return None

    def _run(
        self,
        command: Sequence[str],
        prompt: str,
        *,
        timeout: float,
    ) -> CodexTurnResult:
        started = time.perf_counter()
        try:
            result = subprocess.run(
                list(command),
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CodexCliError(
                f"Codex pilot invocation exceeded {timeout:g} seconds"
            ) from exc
        latency_ms = (time.perf_counter() - started) * 1000
        events: list[dict[str, Any]] = []
        for raw_line in result.stdout.splitlines():
            try:
                value = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                events.append(value)
        if result.returncode:
            errors = [
                str(event.get("message") or event.get("error") or "")
                for event in events
                if event.get("type") in {"error", "turn.failed"}
            ]
            detail = next((value for value in errors if value), "")
            if not detail:
                detail = result.stderr.strip()
            raise CodexCliError(
                f"Codex pilot invocation failed ({result.returncode}): "
                f"{detail[:1200]}"
            )
        thread_ids = {
            str(event["thread_id"])
            for event in events
            if event.get("type") == "thread.started"
            and event.get("thread_id")
        }
        if len(thread_ids) != 1:
            raise CodexCliError(
                "Codex JSONL did not expose exactly one stable thread ID"
            )
        messages = [
            str(item.get("text") or "")
            for event in events
            if event.get("type") == "item.completed"
            and isinstance((item := event.get("item")), Mapping)
            and item.get("type") == "agent_message"
        ]
        if not messages or not messages[-1]:
            raise CodexCliError("Codex JSONL did not contain a final response")
        usage: Mapping[str, Any] = {}
        for event in events:
            if event.get("type") == "turn.completed" and isinstance(
                event.get("usage"), Mapping
            ):
                usage = event["usage"]
        tools = tuple(
            name
            for event in events
            if (name := self._tool_name(event)) is not None
        )
        return CodexTurnResult(
            thread_id=next(iter(thread_ids)),
            message=messages[-1],
            input_tokens=_optional_int(usage.get("input_tokens")),
            cached_input_tokens=_optional_int(
                usage.get("cached_input_tokens")
            ),
            output_tokens=_optional_int(usage.get("output_tokens")),
            reasoning_output_tokens=_optional_int(
                usage.get("reasoning_output_tokens")
            ),
            latency_ms=latency_ms,
            tool_calls=tools,
        )

    def start(self, seat: str, prompt: str, *, timeout: float) -> CodexTurnResult:
        return self._run(self.start_command(), prompt, timeout=timeout)

    def resume(
        self,
        thread_id: str,
        prompt: str,
        *,
        response_schema: Path,
        timeout: float,
    ) -> CodexTurnResult:
        result = self._run(
            self.resume_command(thread_id, response_schema),
            prompt,
            timeout=timeout,
        )
        if result.thread_id != thread_id:
            raise CodexCliError(
                "Codex resumed a replacement thread; the arena stopped"
            )
        return result


@dataclass(slots=True)
class FastPilotThread:
    seat: str
    thread_id: str
    thread_label: str
    profile_sent: bool = False
    invocation_count: int = 0
    first_invocation_at: str | None = None
    last_invocation_at: str | None = None
    retries: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    latency_ms: float = 0.0

    def record(self, turn: CodexTurnResult, *, retry: bool) -> None:
        now = utc_now()
        self.invocation_count += 1
        self.first_invocation_at = self.first_invocation_at or now
        self.last_invocation_at = now
        self.retries += int(retry)
        self.input_tokens += int(turn.input_tokens or 0)
        self.cached_input_tokens += int(turn.cached_input_tokens or 0)
        self.output_tokens += int(turn.output_tokens or 0)
        self.reasoning_output_tokens += int(
            turn.reasoning_output_tokens or 0
        )
        self.latency_ms += turn.latency_ms


class FastPilotRegistry:
    SCHEMA_VERSION = 1

    def __init__(
        self,
        *,
        game_id: str,
        model: str,
        reasoning_effort: str,
        service_tier: str,
        parent_session_id: str | None,
        provider_version: str | None,
        provider_identity_verified: bool,
        model_identity_verified: bool,
        threads: Mapping[str, FastPilotThread] | None = None,
    ):
        self.game_id = game_id
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.service_tier = service_tier
        self.parent_session_id = parent_session_id
        self.provider_version = provider_version
        self.provider_identity_verified = provider_identity_verified
        self.model_identity_verified = model_identity_verified
        self.threads = dict(threads or {})

    def validate(self) -> None:
        if set(self.threads) != set(CODEX_PILOT_SEATS):
            raise CodexCliError(
                "The fast arena needs exactly four persistent seat sessions"
            )
        handles = [self.threads[seat].thread_id for seat in CODEX_PILOT_SEATS]
        if any(not handle for handle in handles) or len(set(handles)) != 4:
            raise CodexCliError(
                "Every seat needs a distinct nonempty Codex thread ID"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "game_id": self.game_id,
            "provider": CODEX_PILOT_PROVIDER,
            "provider_version": self.provider_version,
            "provider_identity_verified": self.provider_identity_verified,
            "model": self.model,
            "model_identity_verified": self.model_identity_verified,
            "reasoning_effort": self.reasoning_effort,
            "service_tier": self.service_tier,
            "parent_session_id": self.parent_session_id,
            "nested_pilot_subagents": False,
            "threads": {
                seat: asdict(self.threads[seat])
                for seat in CODEX_PILOT_SEATS
                if seat in self.threads
            },
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FastPilotRegistry":
        if int(value.get("schema_version", 0)) != cls.SCHEMA_VERSION:
            raise CodexCliError("Unsupported fast-pilot registry version")
        threads = {
            str(seat): FastPilotThread(**dict(row))
            for seat, row in dict(value.get("threads") or {}).items()
        }
        registry = cls(
            game_id=str(value.get("game_id") or ""),
            model=str(value.get("model") or ""),
            reasoning_effort=str(value.get("reasoning_effort") or ""),
            service_tier=str(value.get("service_tier") or ""),
            parent_session_id=value.get("parent_session_id"),
            provider_version=value.get("provider_version"),
            provider_identity_verified=bool(
                value.get("provider_identity_verified")
            ),
            model_identity_verified=bool(
                value.get("model_identity_verified")
            ),
            threads=threads,
        )
        registry.validate()
        return registry


class CodexCliArenaRunner:
    """Neutral fixed-seat broker for four persistent fast Codex sessions."""

    REGISTRY_NAME = "codex-cli-pilots.json"
    BENCHMARK_NAME = "codex-cli-benchmark.json"

    def __init__(
        self,
        *,
        game_dir: str | Path,
        db_path: str | Path,
        client: CodexPilotClient,
        model: str = "gpt-5.6-sol",
        reasoning_effort: str = "low",
        service_tier: str = "priority",
        parent_session_id: str | None = None,
        response_schema: str | Path | None = None,
        bootstrap_timeout: float = 30,
        decision_timeout: float = 90,
        max_retries: int = 2,
    ):
        self.game_dir = Path(game_dir).resolve()
        self.db_path = Path(db_path).resolve()
        self.client = client
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.service_tier = service_tier
        self.parent_session_id = parent_session_id
        self.response_schema = (
            Path(response_schema).resolve()
            if response_schema is not None
            else (
                Path(__file__).parent
                / "schemas"
                / "codex-pilot-response.schema.json"
            ).resolve()
        )
        self.bootstrap_timeout = bootstrap_timeout
        self.decision_timeout = decision_timeout
        self.max_retries = max_retries
        self.registry: FastPilotRegistry | None = None

    @property
    def registry_path(self) -> Path:
        return self.game_dir / self.REGISTRY_NAME

    def _session(self) -> tuple[CardDatabase, CommanderSession]:
        db = CardDatabase(self.db_path)
        session = CommanderSession.load(
            db,
            self.game_dir,
            semantics_path=self.game_dir / "semantics.json",
        )
        return db, session

    def _write_registry(self) -> None:
        if self.registry is None:
            raise CodexCliError("Fast-pilot registry is not initialized")
        temporary = self.registry_path.with_suffix(".json.tmp")
        temporary.write_text(
            stable_json(self.registry.to_dict()),
            encoding="utf-8",
        )
        temporary.replace(self.registry_path)

    def _load_registry(self) -> FastPilotRegistry | None:
        if not self.registry_path.exists():
            return None
        value = json.loads(self.registry_path.read_text(encoding="utf-8"))
        registry = FastPilotRegistry.from_dict(value)
        self._validate_registry_config(registry)
        return registry

    def _validate_registry_config(
        self,
        registry: FastPilotRegistry,
    ) -> None:
        expected = {
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "service_tier": self.service_tier,
        }
        for field, wanted in expected.items():
            actual = getattr(registry, field)
            if actual != wanted:
                raise CodexCliError(
                    f"Persistent pilot {field} changed from "
                    f"{actual!r} to {wanted!r}"
                )
        db, session = self._session()
        try:
            if registry.game_id != session.state.game_id:
                raise CodexCliError(
                    "Fast-pilot registry belongs to another game"
                )
        finally:
            db.close()

    @staticmethod
    def _bootstrap_prompt(seat: str) -> str:
        return (
            f"You are only the strategic pilot for seat {seat} in a "
            "four-player Commander game. You are persistent and seat-isolated, "
            "not the coordinator or rules arbiter. Never inspect another "
            "seat's private packet, memory, or hand. Never inspect checkpoint "
            "or analyst files. Never infer hidden information from filenames "
            "or deck order. Never act for another seat. Do not use tools, "
            "shell, files, network access, or subagents. Make adversarial "
            "high-quality decisions intended to win, follow realistic "
            "Commander mulligans, preserve concise strategic memory, reassess "
            "public threats, and use ordered plans for routine development. "
            "Stop a plan when state or stack changes materially. On later "
            "turns a trusted fixed-seat broker will provide only this seat's "
            "projected task/profile/memory. Return only the required JSON. "
            f"For this bootstrap return exactly "
            f'{{"status":"ready","seat":"{seat}"}}.'
        )

    def _new_registry(self, game_id: str) -> FastPilotRegistry:
        registry = FastPilotRegistry(
            game_id=game_id,
            model=self.model,
            reasoning_effort=self.reasoning_effort,
            service_tier=self.service_tier,
            parent_session_id=self.parent_session_id,
            provider_version=self.client.provider_version,
            provider_identity_verified=(
                self.client.provider_identity_verified
            ),
            model_identity_verified=self.client.model_identity_verified,
        )
        failures: list[str] = []
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(
                    self.client.start,
                    seat,
                    self._bootstrap_prompt(seat),
                    timeout=self.bootstrap_timeout,
                ): seat
                for seat in CODEX_PILOT_SEATS
            }
            for future in as_completed(futures):
                seat = futures[future]
                try:
                    result = future.result()
                    if result.tool_calls:
                        raise CodexCliError(
                            f"Seat {seat} used a bootstrap tool"
                        )
                    ready = json.loads(result.message)
                    if ready != {"status": "ready", "seat": seat}:
                        raise CodexCliError(
                            f"Seat {seat} returned an invalid bootstrap"
                        )
                    registry.threads[seat] = FastPilotThread(
                        seat=seat,
                        thread_id=result.thread_id,
                        thread_label=f"fast-pilot-{seat.lower()}",
                    )
                except Exception as exc:  # pragma: no cover - aggregation
                    failures.append(f"{seat}: {exc}")
        if failures:
            raise CodexCliError(
                "Could not start all four persistent pilots: "
                + "; ".join(sorted(failures))
            )
        registry.validate()
        return registry

    def _recover_registry(
        self,
        session: CommanderSession,
    ) -> FastPilotRegistry | None:
        rows = [
            row
            for row in session.decisions
            if row.get("provider") == CODEX_PILOT_PROVIDER
            and row.get("provider_invoked") is True
        ]
        if not rows:
            return None
        threads: dict[str, FastPilotThread] = {}
        for seat in CODEX_PILOT_SEATS:
            seat_rows = [
                row
                for row in rows
                if row.get("principal") == f"pilot:{seat}"
            ]
            if not seat_rows:
                raise CodexCliError(
                    "Cannot replace a partially recorded persistent pilot pod"
                )
            handles = {
                str(row.get("thread_id"))
                for row in seat_rows
                if row.get("thread_id")
            }
            models = {
                str(row.get("model"))
                for row in seat_rows
                if row.get("model")
            }
            efforts = {
                str(row.get("reasoning_effort"))
                for row in seat_rows
                if row.get("reasoning_effort")
            }
            if len(handles) != 1 or models != {self.model} or efforts != {
                self.reasoning_effort
            }:
                raise CodexCliError(
                    f"Seat {seat} has incompatible persistent identity history"
                )
            timestamps = sorted(
                str(row.get("invoked_at"))
                for row in seat_rows
                if row.get("invoked_at")
            )
            metrics = [dict(row.get("metrics") or {}) for row in seat_rows]
            threads[seat] = FastPilotThread(
                seat=seat,
                thread_id=next(iter(handles)),
                thread_label=str(
                    seat_rows[0].get("thread_label")
                    or f"fast-pilot-{seat.lower()}"
                ),
                profile_sent=True,
                invocation_count=len(seat_rows),
                first_invocation_at=timestamps[0] if timestamps else None,
                last_invocation_at=timestamps[-1] if timestamps else None,
                retries=sum(row.get("accepted") is False for row in seat_rows),
                input_tokens=sum(
                    int(metric.get("input_tokens") or 0)
                    for metric in metrics
                ),
                cached_input_tokens=sum(
                    int(metric.get("cached_input_tokens") or 0)
                    for metric in metrics
                ),
                output_tokens=sum(
                    int(metric.get("output_tokens") or 0)
                    for metric in metrics
                ),
                reasoning_output_tokens=sum(
                    int(metric.get("reasoning_output_tokens") or 0)
                    for metric in metrics
                ),
                latency_ms=sum(
                    float(metric.get("latency_ms") or 0)
                    for metric in metrics
                ),
            )
        parents = {
            str(row.get("parent_session_id"))
            for row in rows
            if row.get("parent_session_id")
        }
        registry = FastPilotRegistry(
            game_id=session.state.game_id,
            model=self.model,
            reasoning_effort=self.reasoning_effort,
            service_tier=self.service_tier,
            parent_session_id=(
                self.parent_session_id
                or (next(iter(parents)) if len(parents) == 1 else None)
            ),
            provider_version=self.client.provider_version,
            provider_identity_verified=(
                self.client.provider_identity_verified
            ),
            model_identity_verified=self.client.model_identity_verified,
            threads=threads,
        )
        registry.validate()
        return registry

    def ensure_sessions(self) -> FastPilotRegistry:
        db, session = self._session()
        try:
            if session.state.config.semantic_policy != "trusted_only":
                raise CodexCliError(
                    "Codex operation arenas require semantic_policy=trusted_only"
                )
            if set(session.state.players) != set(CODEX_PILOT_SEATS):
                raise CodexCliError(
                    "Codex operation arenas require exactly seats A, B, C, D"
                )
            if not all(
                row.get("profile_fingerprint_match") is True
                for row in session.profile_validation.values()
            ):
                raise CodexCliError(
                    "Every seat requires an exact compatible profile fingerprint"
                )
            registry = self._load_registry()
            if registry is None:
                registry = self._recover_registry(session)
            if registry is None:
                registry = self._new_registry(session.state.game_id)
            self.registry = registry
            session.arena_metadata["parent_session_id"] = (
                registry.parent_session_id
            )
            session.arena_metadata["primary_made_strategic_decision"] = False
            session.arena_metadata["parent_made_strategic_decision"] = False
            session.arena_metadata["nested_pilot_subagents"] = False
            if session.record_status == "created":
                session.resume()
            session.save(self.game_dir)
        finally:
            db.close()
        self._write_registry()
        return self.registry

    @staticmethod
    def _decision_prompt(
        seat: str,
        task: Mapping[str, Any],
        *,
        profile: Mapping[str, Any] | None,
        memory: str,
        rejection: str | None = None,
    ) -> str:
        profile_block = (
            "\nEXACT_VALIDATED_PROFILE_JSON:\n" + stable_json(profile)
            if profile is not None
            else ""
        )
        retry_block = (
            "\nPRIOR_RESPONSE_REJECTION:\n" + str(rejection)[:500]
            if rejection
            else ""
        )
        return (
            f"Resolve exactly one current seat-{seat} Commander decision using "
            "only the seat-projected JSON below and your persistent strategic "
            "context. Do not use any tool, shell, file, network source, or "
            "subagent. Never mention or infer hidden information. Return one "
            "object conforming to the supplied schema. Select only an action_id "
            "present in legal_actions. For one action use action_id and an "
            "empty actions array. For an ordered plan use action_id null and "
            "the actions array. Each choices_json is a compact JSON object "
            'encoded as a string, normally "{}". Do not restate server-derived '
            "mana payments. Include a plan category, reason under 180 "
            "characters, confidence, yield (normally null), and bounded "
            "memory_update. Follow realistic Commander mulligans without "
            "chasing an ideal hand.\n"
            "SEAT_TASK_JSON:\n"
            + stable_json(task)
            + profile_block
            + "\nSEAT_MEMORY:\n"
            + memory[:500]
            + retry_block
        )

    @staticmethod
    def _decode_choices(value: Any) -> dict[str, Any]:
        try:
            decoded = json.loads(str(value))
        except json.JSONDecodeError as exc:
            raise CodexCliError("Pilot choices_json is not valid JSON") from exc
        if not isinstance(decoded, dict):
            raise CodexCliError("Pilot choices_json must encode an object")
        return decoded

    @classmethod
    def normalize_response(cls, message: str) -> dict[str, Any]:
        try:
            raw = json.loads(message)
        except json.JSONDecodeError as exc:
            raise CodexCliError("Pilot response is not JSON") from exc
        if not isinstance(raw, dict):
            raise CodexCliError("Pilot response must be a JSON object")
        action_id = raw.get("action_id")
        actions: list[dict[str, Any]] = []
        for item in list(raw.get("actions") or []):
            if not isinstance(item, Mapping) or not item.get("action_id"):
                raise CodexCliError(
                    "Every ordered action requires a server action_id"
                )
            choices = cls._decode_choices(item.get("choices_json", "{}"))
            action = {"action_id": str(item["action_id"])}
            if choices:
                action["choices"] = choices
            actions.append(action)
        if bool(action_id) == bool(actions):
            raise CodexCliError(
                "Pilot must return exactly one action_id or ordered actions"
            )
        response: dict[str, Any] = {}
        if action_id:
            response["action_id"] = str(action_id)
        else:
            response["actions"] = actions
        choices = cls._decode_choices(raw.get("choices_json", "{}"))
        if choices:
            response["choices"] = choices
        response.update(
            {
                "plan": str(raw.get("plan") or ""),
                "reason": str(raw.get("reason") or ""),
                "confidence": raw.get("confidence"),
                "yield": raw.get("yield"),
                "memory_update": str(raw.get("memory_update") or "")[:500],
            }
        )
        return response

    def _identity(
        self,
        thread: FastPilotThread,
        turn: CodexTurnResult,
    ) -> PilotInvocationIdentity:
        assert self.registry is not None
        return PilotInvocationIdentity(
            provider=CODEX_PILOT_PROVIDER,
            model=self.model,
            reasoning_effort=self.reasoning_effort,
            thread_id=thread.thread_id,
            thread_label=thread.thread_label,
            parent_session_id=self.registry.parent_session_id,
            provider_invoked=True,
            provider_identity_verified=(
                self.registry.provider_identity_verified
            ),
            model_identity_verified=self.registry.model_identity_verified,
            model_configured=self.model,
            reasoning_effort_configured=self.reasoning_effort,
            invocation_id=None,
            input_tokens=turn.input_tokens,
            cached_input_tokens=turn.cached_input_tokens,
            output_tokens=turn.output_tokens,
            reasoning_output_tokens=turn.reasoning_output_tokens,
            latency_ms=turn.latency_ms,
        )

    def _pause(self, kind: str, label: str) -> None:
        db, session = self._session()
        try:
            session.pause(
                {
                    "kind": kind[:100],
                    "label": label[:500],
                    "decision_id": (
                        session.state.pending_decision.decision_id
                        if session.state.pending_decision
                        else None
                    ),
                    "decision_kind": (
                        session.state.pending_decision.kind
                        if session.state.pending_decision
                        else None
                    ),
                }
            )
            session.arena_metadata["stop_reason"] = kind
            session.save(self.game_dir)
        finally:
            db.close()

    def _suppressed_meaningful_windows(self) -> int:
        db, session = self._session()
        try:
            return sum(
                int(
                    player.stats.get("decision_optimization", {}).get(
                        "suppressed_meaningful_windows", 0
                    )
                )
                for player in session.state.players.values()
            )
        finally:
            db.close()

    def _next_state(self) -> tuple[str | None, int, bool, str]:
        db, session = self._session()
        try:
            session.engine.pump()
            session.save(self.game_dir)
            pending = session.pending_principals()
            return (
                pending[0] if pending else None,
                session.state.turn_sequence,
                session.state.game_over,
                session.record_status,
            )
        finally:
            db.close()

    def _resolve_one(self, seat: str) -> int:
        if self.registry is None:
            raise CodexCliError("Fast-pilot registry is not initialized")
        thread = self.registry.threads[seat]
        task_tools = SeatScopedPilotTools.open(
            game_dir=self.game_dir,
            db_path=self.db_path,
            seat=seat,
        )
        try:
            task = task_tools.get_task()
            if task is None:
                return 0
            profile = (
                task_tools.get_profile() if not thread.profile_sent else None
            )
            memory = task_tools.get_memory()
        finally:
            task_tools.close()
        retry_task = task
        rejection: str | None = None
        invocations = 0
        for retry_index in range(self.max_retries + 1):
            prompt = self._decision_prompt(
                seat,
                retry_task,
                profile=profile if retry_index == 0 else None,
                memory=memory,
                rejection=rejection,
            )
            turn = self.client.resume(
                thread.thread_id,
                prompt,
                response_schema=self.response_schema,
                timeout=self.decision_timeout,
            )
            invocations += 1
            thread.record(turn, retry=retry_index > 0)
            thread.profile_sent = True
            self._write_registry()
            if turn.tool_calls:
                raise CodexCliError(
                    f"Seat {seat} used forbidden pilot tools: "
                    + ", ".join(turn.tool_calls)
                )
            response = self.normalize_response(turn.message)
            submit_tools = SeatScopedPilotTools.open(
                game_dir=self.game_dir,
                db_path=self.db_path,
                seat=seat,
                identity=self._identity(thread, turn),
            )
            try:
                result = submit_tools.submit_action(response)
                if result.get("accepted"):
                    if response.get("memory_update"):
                        submit_tools.update_memory(
                            str(response["memory_update"])
                        )
                    return invocations
                rejection = str(result.get("error") or "Action rejected")
                retry_value = result.get("retry")
                if not isinstance(retry_value, Mapping):
                    break
                retry_task = copy.deepcopy(dict(retry_value))
            finally:
                submit_tools.close()
        raise CodexCliError(
            f"Seat {seat} exhausted {self.max_retries + 1} responses "
            f"for one decision: {rejection or 'invalid response'}"
        )

    def _benchmark(self, *, stop_reason: str, invocations: int) -> None:
        assert self.registry is not None
        payload = {
            "schema_version": 1,
            "provider": CODEX_PILOT_PROVIDER,
            "provider_version": self.registry.provider_version,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "service_tier": self.service_tier,
            "provider_identity_verified": (
                self.registry.provider_identity_verified
            ),
            "model_identity_verified": self.registry.model_identity_verified,
            "pilot_invocations_this_run": invocations,
            "stop_reason": stop_reason,
            "threads": {
                seat: asdict(self.registry.threads[seat])
                for seat in CODEX_PILOT_SEATS
            },
            "notes": {
                "usage": (
                    "Token counts are recorded only from Codex turn.completed "
                    "events; unavailable values remain absent from decisions."
                ),
                "privacy": (
                    "The neutral broker relays one fixed-seat projection and "
                    "never writes packet contents to this benchmark."
                ),
            },
        }
        path = self.game_dir / self.BENCHMARK_NAME
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(stable_json(payload), encoding="utf-8")
        temporary.replace(path)

    def run(
        self,
        *,
        through_turn: int = 8,
        max_invocations: int = 200,
        verify_replay: bool = True,
    ) -> dict[str, Any]:
        self.ensure_sessions()
        invocations = 0
        stop_reason = "unknown"
        try:
            while invocations < max_invocations:
                suppressed = self._suppressed_meaningful_windows()
                if suppressed:
                    self._pause(
                        "suppressed_meaningful_window",
                        "A meaningful decision window was suppressed; "
                        "the fast arena stopped before another pilot call.",
                    )
                    stop_reason = "suppressed_meaningful_window"
                    break
                principal, turn_sequence, game_over, record_status = (
                    self._next_state()
                )
                if game_over:
                    stop_reason = "game_over"
                    break
                if record_status == "paused":
                    stop_reason = "record_paused"
                    break
                if through_turn > 0 and turn_sequence >= through_turn:
                    stop_reason = "turn_limit"
                    break
                if principal == "arbiter":
                    self._pause(
                        "material_semantic",
                        "Trusted-only play requested live rules arbitration; "
                        "the run stopped without improvisation.",
                    )
                    stop_reason = "material_semantic"
                    break
                if not principal:
                    self._pause(
                        "infrastructure",
                        "The engine produced no next principal before game end.",
                    )
                    stop_reason = "no_next_principal"
                    break
                if not principal.startswith("pilot:"):
                    self._pause(
                        "infrastructure",
                        f"Unsupported arena principal {principal!r}.",
                    )
                    stop_reason = "unsupported_principal"
                    break
                seat = principal.split(":", 1)[1]
                if seat not in CODEX_PILOT_SEATS:
                    self._pause(
                        "seat_isolation",
                        f"Unexpected pilot seat {seat!r}.",
                    )
                    stop_reason = "seat_isolation"
                    break
                used = self._resolve_one(seat)
                if used == 0:
                    continue
                invocations += used
            else:
                stop_reason = "invocation_limit"
        except CodexCliError as exc:
            self._pause("codex_transport", str(exc))
            stop_reason = "codex_transport"
            self._benchmark(
                stop_reason=stop_reason,
                invocations=invocations,
            )
            raise
        self._benchmark(stop_reason=stop_reason, invocations=invocations)
        replay_result: dict[str, Any] | None = None
        if verify_replay:
            db = CardDatabase(self.db_path)
            try:
                current = CommanderSession.load(
                    db,
                    self.game_dir,
                    semantics_path=self.game_dir / "semantics.json",
                )
                preserved_status = (
                    None
                    if current.state.game_over
                    else current.record_status
                )
                refreshed = refresh_record(
                    self.game_dir,
                    db,
                    status=preserved_status,
                    verify_replay=True,
                )
                replay_result = dict(refreshed.get("replay_result") or {})
            finally:
                db.close()
        principal, turn_sequence, game_over, record_status = self._next_state()
        assert self.registry is not None
        return {
            "game_id": self.registry.game_id,
            "record": str(self.game_dir),
            "stop_reason": stop_reason,
            "turn_sequence": turn_sequence,
            "game_over": game_over,
            "record_status": record_status,
            "next_principal": principal,
            "pilot_invocations": invocations,
            "pilot_thread_count": 4,
            "persistent_thread_ids": {
                seat: self.registry.threads[seat].thread_id
                for seat in CODEX_PILOT_SEATS
            },
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "service_tier": self.service_tier,
            "provider_identity_verified": (
                self.registry.provider_identity_verified
            ),
            "model_identity_verified": self.registry.model_identity_verified,
            "suppressed_meaningful_windows": (
                self._suppressed_meaningful_windows()
            ),
            "replay": replay_result,
        }


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)
