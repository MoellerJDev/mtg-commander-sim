from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from .projection import StateProjector
from .session import CommanderSession


class PilotCallable(Protocol):
    def __call__(self, principal: str, packet: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(slots=True)
class RunMetrics:
    accepted_decisions: int = 0
    action_attempts: int = 0
    failed_actions: int = 0
    retries: int = 0
    packet_chars: int = 0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    latency_ms: float = 0.0
    by_principal: dict[str, int] = field(default_factory=dict)

    @property
    def decisions(self) -> int:
        """Backward-compatible name for accepted external decisions."""
        return self.accepted_decisions


class SequentialPilotRunner:
    """Route permission-scoped decisions to one or more LLM callables.

    This class deliberately knows nothing about a particular model API. Codex,
    ChatGPT tool calls, a local model, or four isolated remote agents can all be
    supplied as callbacks. The authoritative engine remains server-side.

    Invalid model output is retried against the *same* live capability. The
    retry packet contains only a compact rejection message in addition to the
    normal seat projection; state rollback and capability restoration remain
    engine responsibilities.
    """

    def __init__(
        self,
        session: CommanderSession,
        pilots: Mapping[str, PilotCallable] | PilotCallable,
        *,
        arbiter: PilotCallable | None = None,
        max_retries_per_decision: int = 2,
    ):
        if max_retries_per_decision < 0:
            raise ValueError("max_retries_per_decision cannot be negative")
        self.session = session
        self.pilots = pilots
        self.arbiter = arbiter
        self.max_retries_per_decision = max_retries_per_decision
        self.metrics = RunMetrics()

    def _callback(self, principal: str) -> PilotCallable:
        if principal == "arbiter" and self.arbiter is not None:
            return self.arbiter
        if callable(self.pilots):
            return self.pilots
        if principal not in self.pilots:
            raise KeyError(f"No pilot callback registered for {principal}")
        return self.pilots[principal]

    def _measure(self, packet: Mapping[str, Any]) -> None:
        size = StateProjector.measure(packet)
        self.metrics.packet_chars += size["compact_chars"]
        self.metrics.estimated_input_tokens += size["estimated_tokens"]

    def step(self) -> bool:
        packet = self.session.next_task()
        if packet is None:
            return False
        principal = str(packet["principal"])
        callback = self._callback(principal)

        for attempt in range(self.max_retries_per_decision + 1):
            delivered = copy.deepcopy(packet)
            if attempt:
                delivered["retry"] = {
                    "attempt": attempt + 1,
                    "instruction": "Previous action was rejected; correct only the illegal assumption and return one JSON action.",
                    "error": last_error,
                }
            self._measure(delivered)
            started = time.perf_counter()
            response = dict(callback(principal, delivered))
            latency_ms = (time.perf_counter() - started) * 1000
            self.metrics.latency_ms += latency_ms
            self.metrics.estimated_output_tokens += max(
                1,
                len(str(response)) // 4,
            )
            response.setdefault("latency_ms", round(latency_ms, 3))
            response.setdefault(
                "model_id",
                str(getattr(callback, "model_id", getattr(callback, "__name__", "callback"))),
            )
            response.setdefault("input_tokens", StateProjector.measure(delivered)["estimated_tokens"])
            response.setdefault("output_tokens", max(1, len(str(response)) // 4))
            result = self.session.act(principal, response)
            self.metrics.action_attempts += 1
            if result.ok:
                self.metrics.accepted_decisions += 1
                self.metrics.by_principal[principal] = self.metrics.by_principal.get(principal, 0) + 1
                return True
            self.metrics.failed_actions += 1
            last_error = result.summary
            if attempt < self.max_retries_per_decision:
                self.metrics.retries += 1
                # The rejected command is transactional: the same principal
                # still owns the same live capability. Refresh delivery metadata
                # without requiring a full resync.
                refreshed = self.session.packet(principal)
                packet = refreshed

        raise RuntimeError(
            f"{principal} action rejected after {self.max_retries_per_decision + 1} attempts: {last_error}"
        )

    def run(self, *, max_decisions: int = 10_000) -> RunMetrics:
        for _ in range(max_decisions):
            if self.session.state.game_over:
                return self.metrics
            if not self.step():
                return self.metrics
        raise RuntimeError(f"Decision limit {max_decisions} reached")
