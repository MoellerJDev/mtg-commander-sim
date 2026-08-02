from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .. import tap_state
from ..tap_state import TapStateHost
from .intents import (
    BecomeMonarchIntent,
    DrawCardsIntent,
    IntentPlan,
    SetPermanentTappedIntent,
    UntapAllCreaturesIntent,
)


class SemanticIntentSink(TapStateHost, Protocol):
    def draw(
        self,
        seat: str,
        count: int = 1,
        *,
        reason: str = "draw",
        private: bool = False,
    ) -> list[str]: ...

    def become_monarch(self, seat: str, *, reason: str) -> str: ...

@dataclass(frozen=True, slots=True)
class DrawResolutionBatch:
    """Draw intents that must use the replacement-aware resolution path."""

    intents: tuple[DrawCardsIntent, ...]


@dataclass(frozen=True, slots=True)
class DrawResolutionRequest:
    current: DrawCardsIntent | None
    remaining_effects: tuple[dict[str, Any], ...]


def draw_resolution_batch(plan: IntentPlan) -> DrawResolutionBatch | None:
    if not all(isinstance(intent, DrawCardsIntent) for intent in plan.intents):
        return None
    return DrawResolutionBatch(
        intents=tuple(
            intent
            for intent in plan.intents
            if isinstance(intent, DrawCardsIntent)
        )
    )


def draw_intent_effect(intent: DrawCardsIntent) -> dict[str, Any]:
    """Serialize a queued typed draw without reintroducing untyped defaults."""

    return {
        "op": "draw",
        "player": intent.player,
        "count": intent.count,
        "private": intent.private,
        "reason": intent.reason,
    }


def prepare_draw_resolution(
    plan: IntentPlan,
    following_effects: tuple[Mapping[str, Any], ...],
) -> DrawResolutionRequest | None:
    batch = draw_resolution_batch(plan)
    if batch is None:
        return None
    current = batch.intents[0] if batch.intents else None
    return DrawResolutionRequest(
        current=current,
        remaining_effects=(
            *(
                draw_intent_effect(intent)
                for intent in batch.intents[1:]
            ),
            *(dict(effect) for effect in following_effects),
        ),
    )


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
        if isinstance(intent, SetPermanentTappedIntent):
            result = tap_state.set_permanent_tapped(
                sink,
                intent.object_ref,
                actor=intent.actor,
                tapped=intent.tapped,
                reason=intent.reason,
            )
            results.append((intent.object_ref, result))
            continue
        if isinstance(intent, UntapAllCreaturesIntent):
            result = tap_state.untap_all_creatures(
                sink,
                actor=intent.actor,
                reason=intent.reason,
            )
            results.append(("creatures", result))
            continue
        raise TypeError(f"Unsupported semantic intent {type(intent).__name__}")
    if plan.result_shape == "by_player":
        return dict(results)
    return results[0][1]
