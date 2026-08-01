from __future__ import annotations

from typing import Protocol

from .intents import BecomeMonarchIntent, DrawCardsIntent, IntentPlan


class SemanticIntentSink(Protocol):
    def draw(
        self,
        seat: str,
        count: int = 1,
        *,
        reason: str = "draw",
        private: bool = False,
    ) -> list[str]: ...

    def become_monarch(self, seat: str, *, reason: str) -> str: ...


def execute_intent_plan(sink: SemanticIntentSink, plan: IntentPlan) -> object:
    results: list[tuple[str, object]] = []
    for intent in plan.intents:
        if isinstance(intent, DrawCardsIntent):
            result = sink.draw(
                intent.player,
                intent.count,
                reason=intent.reason,
                private=intent.private,
            )
            results.append((intent.player, result))
            continue
        if isinstance(intent, BecomeMonarchIntent):
            result = sink.become_monarch(
                intent.player,
                reason=intent.reason,
            )
            results.append((intent.player, result))
            continue
        raise TypeError(f"Unsupported semantic intent {type(intent).__name__}")
    if plan.result_shape == "by_player":
        return dict(results)
    return results[0][1]
