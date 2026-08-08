from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .. import destruction, permanent_exile, return_to_hand, tap_state
from ..destruction import DestructionHost
from ..permanent_exile import PermanentExileHost
from ..return_to_hand import ReturnToHandHost
from ..tap_state import TapStateHost
from .context import SemanticNodeError
from .intents import (
    AddManaIntent,
    AddSubtypeIntent,
    AmassIntent,
    BecomeMonarchIntent,
    CounterStackIntent,
    ChooseOneRestBottomRandomIntent,
    CopyControlledTokensIntent,
    CopyStackItemIntent,
    CreateTokenIntent,
    DealFixedDamageSetIntent,
    DomainEffectIntent,
    DestroyPermanentIntent,
    DestroyPermanentSetIntent,
    DrawCardsIntent,
    IntentPlan,
    EliminatePlayersIntent,
    ExploreCompletedIntent,
    ExilePermanentIntent,
    LifeChangeIntent,
    MoveObjectsSimultaneouslyIntent,
    MoveLibraryCardsToBottomIntent,
    PayManaCostIntent,
    PayLifeIntent,
    PlaceCountersIntent,
    PlaceCountersOnSetIntent,
    PlacePlayerCountersIntent,
    RecordChoiceIntent,
    RecordZoneMoveIntent,
    ReturnCardsToLibraryTopIntent,
    ReturnPermanentToOwnerHandIntent,
    ReorderLibraryTopIntent,
    RetargetStackItemIntent,
    RevealLibraryCardsIntent,
    SetCardDesignationIntent,
    SetPermanentTappedIntent,
    ShuffleLibraryIntent,
    UntapAllCreaturesIntent,
    ZoneMoveIntent,
    ProliferateIntent,
)


class SemanticIntentSink(
    TapStateHost,
    DestructionHost,
    PermanentExileHost,
    ReturnToHandHost,
    Protocol,
):
    def apply_domain_effect_intent(self, intent: DomainEffectIntent) -> Any: ...

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

    def complete_explore_intent(
        self,
        intent: ExploreCompletedIntent,
    ) -> None: ...

    def move_object_intent(self, intent: ZoneMoveIntent) -> str: ...

    def move_objects_simultaneously_intent(
        self,
        intent: MoveObjectsSimultaneouslyIntent,
    ) -> tuple[str, ...]: ...

    def choose_one_rest_bottom_random_intent(
        self,
        intent: ChooseOneRestBottomRandomIntent,
    ) -> tuple[str, ...]: ...

    def shuffle_library_intent(self, intent: ShuffleLibraryIntent) -> None: ...

    def return_cards_to_library_top_intent(
        self,
        intent: ReturnCardsToLibraryTopIntent,
    ) -> tuple[str, ...]: ...

    def record_zone_move_intent(self, intent: RecordZoneMoveIntent) -> None: ...

    def apply_life_change_intent(self, intent: LifeChangeIntent) -> int: ...

    def pay_life_intent(self, intent: PayLifeIntent) -> int: ...

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

    def place_counters_on_set_intent(
        self,
        intent: PlaceCountersOnSetIntent,
    ) -> tuple[str, ...]: ...

    def place_player_counters_intent(
        self,
        intent: PlacePlayerCountersIntent,
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

    def add_subtype_intent(self, intent: AddSubtypeIntent) -> str: ...

    def proliferate_intent(self, intent: ProliferateIntent) -> None: ...

    def deal_fixed_damage_set_intent(
        self,
        intent: DealFixedDamageSetIntent,
    ) -> Any: ...

    def destroy_permanent_set_intent(
        self,
        intent: DestroyPermanentSetIntent,
    ) -> Any: ...


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

    effect = {
        "op": (
            "draw_with_actions"
            if intent.post_draw_actions
            else "draw"
        ),
        "player": intent.player,
        "count": intent.count,
        "private": intent.private,
        "reason": intent.reason,
    }
    if intent.post_draw_actions:
        effect["post_draw_actions"] = [
            action.to_dict() for action in intent.post_draw_actions
        ]
    return effect


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


PermanentTransitionIntent = (
    DestroyPermanentIntent
    | DestroyPermanentSetIntent
    | ExilePermanentIntent
    | ReturnPermanentToOwnerHandIntent
)
PERMANENT_TRANSITION_INTENT_TYPES = (
    DestroyPermanentIntent,
    DestroyPermanentSetIntent,
    ExilePermanentIntent,
    ReturnPermanentToOwnerHandIntent,
)


def _execute_permanent_transition_intent(
    sink: SemanticIntentSink,
    intent: PermanentTransitionIntent,
) -> tuple[str, object]:
    if isinstance(intent, DestroyPermanentIntent):
        return (
            intent.object_ref,
            destruction.destroy_permanent_refs(
                sink,
                (intent.object_ref,),
                actor=intent.actor,
                reason=intent.reason,
                replacement_selections=intent.replacement_selections,
            ),
        )
    if isinstance(intent, DestroyPermanentSetIntent):
        return intent.actor, sink.destroy_permanent_set_intent(intent)
    if isinstance(intent, ExilePermanentIntent):
        return (
            intent.object_ref,
            permanent_exile.exile_permanent(
                sink,
                intent.object_ref,
                actor=intent.actor,
                reason=intent.reason,
                replacement_selections=intent.replacement_selections,
            ),
        )
    return (
        intent.object_ref,
        return_to_hand.return_permanent_to_owner_hand(
            sink,
            intent.object_ref,
            actor=intent.actor,
            reason=intent.reason,
            replacement_selections=intent.replacement_selections,
        ),
    )


RecordingIntent = RecordChoiceIntent | ExploreCompletedIntent
RECORDING_INTENT_TYPES = (RecordChoiceIntent, ExploreCompletedIntent)


def _execute_recording_intent(
    sink: SemanticIntentSink,
    intent: RecordingIntent,
) -> tuple[str, None]:
    if isinstance(intent, RecordChoiceIntent):
        sink.record_choice_intent(intent)
        return intent.actor, None
    sink.complete_explore_intent(intent)
    return intent.explorer_ref, None


CounterPlacementIntent = (
    PlaceCountersIntent
    | PlaceCountersOnSetIntent
    | PlacePlayerCountersIntent
)
COUNTER_PLACEMENT_INTENT_TYPES = (
    PlaceCountersIntent,
    PlaceCountersOnSetIntent,
    PlacePlayerCountersIntent,
)
_COUNTER_RESULT_KEY = "counter" + "s"


def _execute_counter_placement_intent(
    sink: SemanticIntentSink,
    intent: CounterPlacementIntent,
) -> tuple[str, object]:
    if isinstance(intent, PlaceCountersIntent):
        return _COUNTER_RESULT_KEY, sink.place_counters_intent(intent)
    if isinstance(intent, PlaceCountersOnSetIntent):
        return _COUNTER_RESULT_KEY, sink.place_counters_on_set_intent(intent)
    return "player_counters", sink.place_player_counters_intent(intent)


def execute_intent_plan(sink: SemanticIntentSink, plan: IntentPlan) -> object:
    if any(isinstance(intent, DrawCardsIntent) for intent in plan.intents):
        raise SemanticNodeError(
            "Draw intents require the replacement-aware draw coordinator"
        )
    results: list[tuple[str, object]] = []
    for intent in plan.intents:
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
                logical_object_id=intent.logical_object_id,
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
        if isinstance(intent, PERMANENT_TRANSITION_INTENT_TYPES):
            results.append(_execute_permanent_transition_intent(sink, intent))
            continue
        if isinstance(intent, AddManaIntent):
            result = sink.apply_mana_intent(intent)
            results.append((intent.player, result))
            continue
        if isinstance(intent, SetCardDesignationIntent):
            result = sink.set_card_designation_intent(intent)
            results.append((intent.object_ref, result))
            continue
        if isinstance(intent, RECORDING_INTENT_TYPES):
            results.append(_execute_recording_intent(sink, intent))
            continue
        if isinstance(intent, ZoneMoveIntent):
            result = sink.move_object_intent(intent)
            results.append((intent.object_ref, result))
            continue
        if isinstance(intent, MoveObjectsSimultaneouslyIntent):
            result = sink.move_objects_simultaneously_intent(intent)
            results.append((intent.actor, result))
            continue
        if isinstance(intent, ChooseOneRestBottomRandomIntent):
            result = sink.choose_one_rest_bottom_random_intent(intent)
            results.append((intent.player, result))
            continue
        if isinstance(intent, ShuffleLibraryIntent):
            sink.shuffle_library_intent(intent)
            results.append((intent.player, None))
            continue
        if isinstance(intent, ReturnCardsToLibraryTopIntent):
            result = sink.return_cards_to_library_top_intent(intent)
            results.append((intent.player, result))
            continue
        if isinstance(intent, RecordZoneMoveIntent):
            sink.record_zone_move_intent(intent)
            results.append((intent.object_ref, None))
            continue
        if isinstance(intent, LifeChangeIntent):
            result = sink.apply_life_change_intent(intent)
            results.append((intent.player, result))
            continue
        if isinstance(intent, PayLifeIntent):
            result = sink.pay_life_intent(intent)
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
        if isinstance(intent, COUNTER_PLACEMENT_INTENT_TYPES):
            results.append(_execute_counter_placement_intent(sink, intent))
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
        if isinstance(intent, AddSubtypeIntent):
            result = sink.add_subtype_intent(intent)
            results.append((intent.object_ref, result))
            continue
        if isinstance(intent, ProliferateIntent):
            sink.proliferate_intent(intent)
            results.append((intent.actor, None))
            continue
        if isinstance(intent, DealFixedDamageSetIntent):
            result = sink.deal_fixed_damage_set_intent(intent)
            results.append((intent.source_ref, result))
            continue
        if isinstance(intent, DomainEffectIntent):
            result = sink.apply_domain_effect_intent(intent)
            results.append((intent.operation, result))
            continue
        raise TypeError(f"Unsupported semantic intent {type(intent).__name__}")
    if plan.result_shape == "by_player":
        return dict(results)
    return results[0][1]
    SetCardDesignationIntent,
