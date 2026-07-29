from __future__ import annotations

import copy
import json
import shlex
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence, TextIO

from .projection import StateProjector
from .session import CommanderSession

PLAN_CATEGORIES = (
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
)


@dataclass(slots=True)
class PilotMemory:
    """Seat-private strategic memory persisted independently for each pilot."""

    text: str = ""
    profile: dict[str, Any] = field(default_factory=dict)
    invocations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any] | None) -> "PilotMemory":
        value = value or {}
        return cls(
            text=str(value.get("text") or "")[:500],
            profile=dict(value.get("profile") or {}),
            invocations=int(value.get("invocations", 0)),
        )


@dataclass(slots=True)
class PilotResponse:
    action_id: str | None = None
    raw_action: str | None = None
    choices: dict[str, Any] = field(default_factory=dict)
    actions: list[dict[str, Any]] = field(default_factory=list)
    plan: str = "PASS_WITH_YIELD"
    reason: str = ""
    confidence: float | None = None
    yield_mode: str | None = None
    memory_update: str = ""
    provider: str | None = None
    model: str | None = None
    invocation_id: str | None = None
    reasoning_effort: str | None = None
    thread_id: str | None = None
    thread_label: str | None = None
    parent_session_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float | None = None
    automatic_fallback: bool = False

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "PilotResponse":
        value = dict(raw)
        actions = [dict(item) for item in value.get("actions") or []]
        choices = dict(value.get("choices") or {})
        # Manual/subprocess providers may return the engine's compact response
        # shape directly. Preserve it by treating non-audit fields as choices.
        reserved = {
            "action_id", "a", "action", "actions", "choices", "plan", "reason", "confidence",
            "yield", "memory_update", "provider", "model", "model_id",
            "implementation_id", "invocation_id", "input_tokens",
            "output_tokens", "latency_ms", "automatic_fallback", "fallback",
            "reasoning_effort", "thread_id", "thread_label",
            "parent_session_id",
        }
        for key, child in value.items():
            if key not in reserved:
                choices.setdefault(key, child)
        response = cls(
            action_id=(str(value["action_id"]) if value.get("action_id") else None),
            raw_action=(
                str(value.get("action") or value.get("a"))
                if value.get("action") or value.get("a")
                else None
            ),
            choices=choices,
            actions=actions,
            plan=str(value.get("plan") or "PASS_WITH_YIELD"),
            reason=str(value.get("reason") or ""),
            confidence=(
                float(value["confidence"])
                if value.get("confidence") is not None
                else None
            ),
            yield_mode=value.get("yield"),
            memory_update=str(value.get("memory_update") or ""),
            provider=value.get("provider"),
            model=(
                value.get("model")
                or value.get("model_id")
                or value.get("implementation_id")
            ),
            invocation_id=value.get("invocation_id"),
            reasoning_effort=value.get("reasoning_effort"),
            thread_id=value.get("thread_id"),
            thread_label=value.get("thread_label"),
            parent_session_id=value.get("parent_session_id"),
            input_tokens=(
                int(value["input_tokens"])
                if value.get("input_tokens") is not None
                else None
            ),
            output_tokens=(
                int(value["output_tokens"])
                if value.get("output_tokens") is not None
                else None
            ),
            latency_ms=(
                float(value["latency_ms"])
                if value.get("latency_ms") is not None
                else None
            ),
            automatic_fallback=bool(
                value.get("automatic_fallback", value.get("fallback", False))
            ),
        )
        response.validate()
        return response

    def validate(self) -> None:
        if self.plan not in PLAN_CATEGORIES:
            raise ValueError(
                f"plan must be one of {', '.join(PLAN_CATEGORIES)}"
            )
        if len(self.reason) > 180:
            raise ValueError("reason exceeds 180 characters")
        if len(self.memory_update) > 500:
            raise ValueError("memory_update exceeds 500 characters")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not self.action_id and not self.raw_action and not self.actions:
            raise ValueError(
                "pilot response needs action_id, action, or a nonempty actions list"
            )
        if self.action_id and self.actions:
            raise ValueError("use action_id or actions, not both")
        if len(self.actions) > 8:
            raise ValueError("ordered actions may contain at most 8 entries")
        for item in self.actions:
            if not item.get("action_id"):
                raise ValueError("every planned action needs action_id")

    def engine_response(self) -> dict[str, Any]:
        plan_actions = copy.deepcopy(self.actions)
        action_id = self.action_id
        selected_choices = copy.deepcopy(self.choices)
        if plan_actions and action_id is None:
            action_id = str(plan_actions[0]["action_id"])
            first = plan_actions[0]
            selected_choices = {
                **dict(first.get("choices") or {}),
                **{
                    key: copy.deepcopy(value)
                    for key, value in first.items()
                    if key not in {"action_id", "choices", "future_choices"}
                },
                **selected_choices,
            }
        payload = {
            "action_id": action_id,
            **selected_choices,
            "plan": plan_actions if plan_actions else self.plan,
            "plan_category": self.plan,
            "reason": self.reason,
            "confidence": self.confidence,
            "memory_update": self.memory_update or None,
            "provider": self.provider,
            "model_id": self.model,
            "invocation_id": self.invocation_id,
            "reasoning_effort": self.reasoning_effort,
            "thread_id": self.thread_id,
            "thread_label": self.thread_label,
            "parent_session_id": self.parent_session_id,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "latency_ms": self.latency_ms,
            "automatic_fallback": self.automatic_fallback,
        }
        if self.yield_mode:
            payload["yield"] = self.yield_mode
        if self.raw_action and not action_id:
            payload["a"] = self.raw_action
        return {key: value for key, value in payload.items() if value is not None}


class PilotProvider(Protocol):
    provider_id: str
    implementation_id: str

    def decide(
        self,
        observation: Mapping[str, Any],
        decision: Mapping[str, Any],
        memory: PilotMemory,
    ) -> PilotResponse | Mapping[str, Any]: ...


class PilotCallable(Protocol):
    def __call__(
        self, principal: str, packet: Mapping[str, Any]
    ) -> Mapping[str, Any]: ...


class ScriptedPilot:
    """Deterministic provider used for scenarios and replayable fixtures."""

    provider_id = "scripted"

    def __init__(
        self,
        responses: Sequence[Mapping[str, Any]] | None = None,
        *,
        chooser: Any | None = None,
        implementation_id: str = "scripted-pilot-v1",
    ):
        self.responses = [dict(value) for value in (responses or [])]
        self.chooser = chooser
        self.implementation_id = implementation_id
        self._cursor = 0

    def decide(
        self,
        observation: Mapping[str, Any],
        decision: Mapping[str, Any],
        memory: PilotMemory,
    ) -> PilotResponse:
        if self.chooser is not None:
            raw = self.chooser(observation, decision, memory)
        else:
            if self._cursor >= len(self.responses):
                raise RuntimeError("ScriptedPilot exhausted its exact responses")
            raw = self.responses[self._cursor]
            self._cursor += 1
        response = PilotResponse.from_mapping(raw)
        response.provider = response.provider or self.provider_id
        response.model = response.model or self.implementation_id
        response.invocation_id = response.invocation_id or f"script-{memory.invocations + 1}"
        return response


class ManualJsonPilot:
    """JSON-file/stdin bridge for ChatGPT/Codex-assisted play."""

    provider_id = "manual-json"

    def __init__(
        self,
        *,
        task_path: str | Path | None = None,
        response_path: str | Path | None = None,
        input_stream: TextIO | None = None,
        output_stream: TextIO | None = None,
        implementation_id: str = "manual-json-v1",
    ):
        self.task_path = Path(task_path) if task_path else None
        self.response_path = Path(response_path) if response_path else None
        self.input_stream = input_stream or sys.stdin
        self.output_stream = output_stream or sys.stdout
        self.implementation_id = implementation_id

    def decide(
        self,
        observation: Mapping[str, Any],
        decision: Mapping[str, Any],
        memory: PilotMemory,
    ) -> PilotResponse:
        task = {
            "observation": observation,
            "decision": decision,
            "memory": memory.to_dict(),
        }
        text = json.dumps(task, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        if self.task_path:
            self.task_path.parent.mkdir(parents=True, exist_ok=True)
            self.task_path.write_text(text + "\n", encoding="utf-8")
        else:
            self.output_stream.write(text + "\n")
            self.output_stream.flush()
        if self.response_path:
            raw = json.loads(self.response_path.read_text(encoding="utf-8"))
        else:
            raw = json.loads(self.input_stream.readline())
        response = PilotResponse.from_mapping(raw)
        response.provider = response.provider or self.provider_id
        response.model = response.model or self.implementation_id
        response.invocation_id = response.invocation_id or uuid.uuid4().hex
        return response


class SubprocessJsonPilot:
    """Provider adapter for any command accepting JSON stdin/stdout."""

    provider_id = "subprocess-json"

    def __init__(
        self,
        command: str | Sequence[str],
        *,
        timeout: float = 120,
        implementation_id: str | None = None,
    ):
        self.command = (
            shlex.split(command, posix=True)
            if isinstance(command, str)
            else [str(value) for value in command]
        )
        if not self.command:
            raise ValueError("SubprocessJsonPilot requires a command")
        self.timeout = timeout
        self.implementation_id = implementation_id or " ".join(self.command)

    def decide(
        self,
        observation: Mapping[str, Any],
        decision: Mapping[str, Any],
        memory: PilotMemory,
    ) -> PilotResponse:
        request = json.dumps(
            {
                "observation": observation,
                "decision": decision,
                "memory": memory.to_dict(),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        completed = subprocess.run(
            self.command,
            input=request,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
        )
        if completed.returncode:
            raise RuntimeError(
                f"Pilot subprocess exited {completed.returncode}: "
                f"{completed.stderr.strip()[:500]}"
            )
        response = PilotResponse.from_mapping(json.loads(completed.stdout))
        response.provider = response.provider or self.provider_id
        response.model = response.model or self.implementation_id
        response.invocation_id = response.invocation_id or uuid.uuid4().hex
        return response


@dataclass(slots=True)
class RunMetrics:
    accepted_decisions: int = 0
    action_attempts: int = 0
    failed_actions: int = 0
    retries: int = 0
    pilot_invocations: int = 0
    arbiter_invocations: int = 0
    automatic_decisions: int = 0
    packet_chars: int = 0
    bootstrap_chars: int = 0
    delta_chars: int = 0
    packet_bytes: int = 0
    bootstrap_bytes: int = 0
    delta_bytes: int = 0
    bootstrap_estimated_tokens: int = 0
    delta_estimated_tokens: int = 0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    input_tokens_observed: int = 0
    output_tokens_observed: int = 0
    pilot_input_tokens_observed: int = 0
    pilot_output_tokens_observed: int = 0
    arbiter_input_tokens_observed: int = 0
    arbiter_output_tokens_observed: int = 0
    invocations_with_input_usage: int = 0
    invocations_with_output_usage: int = 0
    pilot_invocations_with_input_usage: int = 0
    pilot_invocations_with_output_usage: int = 0
    arbiter_invocations_with_input_usage: int = 0
    arbiter_invocations_with_output_usage: int = 0
    latency_ms: float = 0.0
    pass_only_windows_skipped: int = 0
    yield_covered_windows: int = 0
    ordered_plan_actions_executed: int = 0
    by_principal: dict[str, int] = field(default_factory=dict)

    @property
    def decisions(self) -> int:
        return self.accepted_decisions

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        measured_fields = {
            "input_tokens_observed": "invocations_with_input_usage",
            "output_tokens_observed": "invocations_with_output_usage",
            "pilot_input_tokens_observed": "pilot_invocations_with_input_usage",
            "pilot_output_tokens_observed": "pilot_invocations_with_output_usage",
            "arbiter_input_tokens_observed": "arbiter_invocations_with_input_usage",
            "arbiter_output_tokens_observed": "arbiter_invocations_with_output_usage",
        }
        for value_field, count_field in measured_fields.items():
            if not payload[count_field]:
                payload[value_field] = None
        payload["token_measurement_status"] = (
            "complete"
            if (
                self.pilot_invocations + self.arbiter_invocations
                and self.invocations_with_input_usage
                == self.pilot_invocations + self.arbiter_invocations
                and self.invocations_with_output_usage
                == self.pilot_invocations + self.arbiter_invocations
            )
            else "partial"
            if self.invocations_with_input_usage
            or self.invocations_with_output_usage
            else "unavailable"
        )
        return payload


class SequentialPilotRunner:
    """Route isolated seat projections through provider-neutral pilot adapters."""

    def __init__(
        self,
        session: CommanderSession,
        pilots: Mapping[str, PilotProvider | PilotCallable] | PilotProvider | PilotCallable,
        *,
        arbiter: PilotProvider | PilotCallable | None = None,
        max_retries_per_decision: int = 2,
        memories: Mapping[str, PilotMemory] | None = None,
    ):
        if max_retries_per_decision < 0:
            raise ValueError("max_retries_per_decision cannot be negative")
        self.session = session
        self.pilots = pilots
        self.arbiter = arbiter
        self.max_retries_per_decision = max_retries_per_decision
        self.metrics = RunMetrics()
        self.memories = {
            principal: PilotMemory.from_dict(memory.to_dict())
            for principal, memory in (memories or {}).items()
        }

    def _provider(self, principal: str) -> PilotProvider | PilotCallable:
        if principal == "arbiter" and self.arbiter is not None:
            return self.arbiter
        if callable(self.pilots) or hasattr(self.pilots, "decide"):
            return self.pilots  # type: ignore[return-value]
        if principal not in self.pilots:
            raise KeyError(f"No pilot provider registered for {principal}")
        return self.pilots[principal]

    def _memory(self, principal: str) -> PilotMemory:
        return self.memories.setdefault(
            principal,
            PilotMemory(
                profile=copy.deepcopy(
                    self.session.pilot_profiles.get(principal, {})
                )
            ),
        )

    def _refresh_optimization_metrics(self) -> None:
        self.metrics.pass_only_windows_skipped = sum(
            int(
                player.stats.get("decision_optimization", {}).get(
                    "pass_only_windows_skipped", 0
                )
            )
            for player in self.session.state.players.values()
        )
        self.metrics.yield_covered_windows = sum(
            int(
                player.stats.get("decision_optimization", {}).get(
                    "yield_covered_windows", 0
                )
            )
            for player in self.session.state.players.values()
        )

    def _measure(self, packet: Mapping[str, Any]) -> dict[str, int]:
        size = StateProjector.measure(packet)
        self.metrics.packet_chars += size["compact_chars"]
        self.metrics.packet_bytes += size["compact_bytes"]
        self.metrics.estimated_input_tokens += size["estimated_tokens"]
        if packet.get("mode") == "full":
            self.metrics.bootstrap_chars += size["compact_chars"]
            self.metrics.bootstrap_bytes += size["compact_bytes"]
            self.metrics.bootstrap_estimated_tokens += size["estimated_tokens"]
        else:
            self.metrics.delta_chars += size["compact_chars"]
            self.metrics.delta_bytes += size["compact_bytes"]
            self.metrics.delta_estimated_tokens += size["estimated_tokens"]
        return size

    @staticmethod
    def _observation(packet: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: copy.deepcopy(value)
            for key, value in packet.items()
            if key != "decision"
        }

    def _invoke(
        self,
        principal: str,
        provider: PilotProvider | PilotCallable,
        packet: Mapping[str, Any],
    ) -> PilotResponse:
        memory = self._memory(principal)
        started = time.perf_counter()
        if hasattr(provider, "decide"):
            raw = provider.decide(
                self._observation(packet),
                dict(packet.get("decision") or {}),
                memory,
            )
        else:
            raw = provider(principal, packet)  # type: ignore[operator]
        elapsed = (time.perf_counter() - started) * 1000
        response = (
            raw if isinstance(raw, PilotResponse) else PilotResponse.from_mapping(raw)
        )
        response.provider = response.provider or str(
            getattr(provider, "provider_id", "callback")
        )
        response.model = response.model or str(
            getattr(
                provider,
                "implementation_id",
                getattr(provider, "model_id", getattr(provider, "__name__", "callback")),
            )
        )
        response.invocation_id = response.invocation_id or uuid.uuid4().hex
        response.latency_ms = (
            response.latency_ms if response.latency_ms is not None else round(elapsed, 3)
        )
        memory.invocations += 1
        if response.memory_update:
            memory.text = response.memory_update
        if principal == "arbiter":
            self.metrics.arbiter_invocations += 1
        else:
            self.metrics.pilot_invocations += 1
        self.metrics.latency_ms += elapsed
        if response.input_tokens is not None:
            self.metrics.input_tokens_observed += response.input_tokens
            self.metrics.invocations_with_input_usage += 1
            if principal == "arbiter":
                self.metrics.arbiter_input_tokens_observed += response.input_tokens
                self.metrics.arbiter_invocations_with_input_usage += 1
            else:
                self.metrics.pilot_input_tokens_observed += response.input_tokens
                self.metrics.pilot_invocations_with_input_usage += 1
        if response.output_tokens is not None:
            self.metrics.output_tokens_observed += response.output_tokens
            self.metrics.invocations_with_output_usage += 1
            if principal == "arbiter":
                self.metrics.arbiter_output_tokens_observed += response.output_tokens
                self.metrics.arbiter_invocations_with_output_usage += 1
            else:
                self.metrics.pilot_output_tokens_observed += response.output_tokens
                self.metrics.pilot_invocations_with_output_usage += 1
        return response

    def step(self) -> bool:
        commands_before = len(self.session.commands)
        packet = self.session.next_task()
        auto_commands = len(self.session.commands) - commands_before
        if auto_commands:
            self.metrics.automatic_decisions += auto_commands
            self.metrics.ordered_plan_actions_executed += auto_commands
        if packet is None:
            self._refresh_optimization_metrics()
            return False
        principal = str(packet["principal"])
        provider = self._provider(principal)
        last_error = ""

        for attempt in range(self.max_retries_per_decision + 1):
            delivered = copy.deepcopy(packet)
            if attempt:
                # Retry contains a projection delta plus the compact error; it
                # never resends a full authoritative or projected state.
                delivered["retry"] = {
                    "attempt": attempt + 1,
                    "instruction": (
                        "Correct only the invalid fields and return one JSON response."
                    ),
                    "error": last_error,
                }
            measured = self._measure(delivered)
            response = self._invoke(principal, provider, delivered)
            if response.output_tokens is None:
                self.metrics.estimated_output_tokens += max(
                    1, len(json.dumps(response.engine_response())) // 4
                )
            engine_response = response.engine_response()
            engine_response["provider_invoked"] = True
            engine_response["retry_count"] = attempt
            engine_response.setdefault("estimated_input_tokens", measured["estimated_tokens"])
            result = self.session.act(principal, engine_response)
            self.metrics.action_attempts += 1
            if result.ok:
                self.metrics.accepted_decisions += 1
                self.metrics.by_principal[principal] = (
                    self.metrics.by_principal.get(principal, 0) + 1
                )
                self._refresh_optimization_metrics()
                return True
            self.metrics.failed_actions += 1
            last_error = result.summary
            if attempt < self.max_retries_per_decision:
                self.metrics.retries += 1
                packet = self.session.packet(principal)

        raise RuntimeError(
            f"{principal} action rejected after "
            f"{self.max_retries_per_decision + 1} attempts: {last_error}"
        )

    def run(self, *, max_decisions: int = 10_000) -> RunMetrics:
        for _ in range(max_decisions):
            if self.session.state.game_over:
                return self.metrics
            if not self.step():
                return self.metrics
        raise RuntimeError(f"Decision limit {max_decisions} reached")
