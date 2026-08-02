from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .. import tap_state
from ..tap_state import TapStateHost
from .intents import (
    AddManaIntent,
    AmassIntent,
    BecomeMonarchIntent,
    CounterStackIntent,
    CopyControlledTokensIntent,
    CopyStackItemIntent,
    CreateTokenIntent,
    DrawCardsIntent,
    IntentPlan,
    EliminatePlayersIntent,
    LifeChangeIntent,
    MoveLibraryCardsToBottomIntent,
    PayManaCostIntent,
    PlaceCountersIntent,
    RecordChoiceIntent,
    RecordZoneMoveIntent,
    ReorderLibraryTopIntent,
    RetargetStackItemIntent,
    RevealLibraryCardsIntent,
    SetCardDesignationIntent,
    SetPermanentTappedIntent,
    UntapAllCreaturesIntent,
    ZoneMoveIntent,
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

    def apply_mana_intent(self, intent: AddManaIntent) -> int: ...

    def set_card_designation_intent(
        self,
        intent: SetCardDesignationIntent,
    ) -> str: ...

    def record_choice_intent(self, intent: RecordChoiceIntent) -> None: ...

    def move_object_intent(self, intent: ZoneMoveIntent) -> str: ...

    def record_zone_move_intent(self, intent: RecordZoneMoveIntent) -> None: ...

    def apply_life_change_intent(self, intent: LifeChangeIntent) -> int: ...

    def reveal_library_cards_intent(
        self,
        intent: RevealLibraryCardsIntent,
    ) -> tuple[str, ...]: ...

    def move_library_cards_to_bottom_intent(
        self,
        intent: MoveLibraryCardsToBottomIntent,
    ) -> tuple[str, ...]: ...

    def reorder_library_top_intent(
        self,
        intent: ReorderLibraryTopIntent,
    ) -> tuple[str, ...]: ...

    def pay_mana_cost_intent(self, intent: PayManaCostIntent) -> None: ...

    def place_counters_intent(
        self,
        intent: PlaceCountersIntent,
    ) -> tuple[str, ...]: ...

    def counter_stack_intent(self, intent: CounterStackIntent) -> None: ...

    def eliminate_players_intent(self, intent: EliminatePlayersIntent) -> None: ...

    def copy_stack_item_intent(self, intent: CopyStackItemIntent) -> str: ...

    def retarget_stack_item_intent(
        self,
        intent: RetargetStackItemIntent,
    ) -> str: ...

    def create_token_intent(self, intent: CreateTokenIntent) -> tuple[str, ...]: ...

    def copy_controlled_tokens_intent(
        self,
        intent: CopyControlledTokensIntent,
    ) -> tuple[str, ...]: ...

    def apply_amass_intent(self, intent: AmassIntent) -> str: ...


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
        if isinstance(intent, AddManaIntent):
            result = sink.apply_mana_intent(intent)
            results.append((intent.player, result))
            continue
        if isinstance(intent, SetCardDesignationIntent):
            result = sink.set_card_designation_intent(intent)
            results.append((intent.object_ref, result))
            continue
        if isinstance(intent, RecordChoiceIntent):
            sink.record_choice_intent(intent)
            results.append((intent.actor, None))
            continue
        if isinstance(intent, ZoneMoveIntent):
            result = sink.move_object_intent(intent)
            results.append((intent.object_ref, result))
            continue
        if isinstance(intent, RecordZoneMoveIntent):
            sink.record_zone_move_intent(intent)
            results.append((intent.object_ref, None))
            continue
        if isinstance(intent, LifeChangeIntent):
            result = sink.apply_life_change_intent(intent)
            results.append((intent.player, result))
            continue
        if isinstance(intent, RevealLibraryCardsIntent):
            result = sink.reveal_library_cards_intent(intent)
            results.append((intent.player, result))
            continue
        if isinstance(intent, MoveLibraryCardsToBottomIntent):
            result = sink.move_library_cards_to_bottom_intent(intent)
            results.append((intent.player, result))
            continue
        if isinstance(intent, ReorderLibraryTopIntent):
            result = sink.reorder_library_top_intent(intent)
            results.append((intent.player, result))
            continue
        if isinstance(intent, PayManaCostIntent):
            sink.pay_mana_cost_intent(intent)
            results.append((intent.player, None))
            continue
        if isinstance(intent, PlaceCountersIntent):
            result = sink.place_counters_intent(intent)
            results.append(("counters", result))
            continue
        if isinstance(intent, CounterStackIntent):
            sink.counter_stack_intent(intent)
            results.append((intent.stack_ref, None))
            continue
        if isinstance(intent, EliminatePlayersIntent):
            sink.eliminate_players_intent(intent)
            results.append(("players", None))
            continue
        if isinstance(intent, CopyStackItemIntent):
            result = sink.copy_stack_item_intent(intent)
            results.append((intent.target_stack_ref, result))
            continue
        if isinstance(intent, RetargetStackItemIntent):
            result = sink.retarget_stack_item_intent(intent)
            results.append((intent.target_stack_ref, result))
            continue
        if isinstance(intent, CreateTokenIntent):
            result = sink.create_token_intent(intent)
            results.append((intent.controller, result))
            continue
        if isinstance(intent, CopyControlledTokensIntent):
            result = sink.copy_controlled_tokens_intent(intent)
            results.append((intent.controller, result))
            continue
        if isinstance(intent, AmassIntent):
            result = sink.apply_amass_intent(intent)
            results.append((intent.controller, result))
            continue
        raise TypeError(f"Unsupported semantic intent {type(intent).__name__}")
    if plan.result_shape == "by_player":
        return dict(results)
    return results[0][1]
    SetCardDesignationIntent,
