from __future__ import annotations

"""Strict typed lowering for fixed counter-placement effects."""

from dataclasses import dataclass
from typing import Any, Mapping

from .context import ReadOnlyHandlerContext, SemanticNodeError
from .direct_target_fields import validate_direct_target_effect
from .intents import (
    IntentPlan,
    PlaceCountersIntent,
    PlacePlayerCountersIntent,
)


_REASON_FIELD = "rea" + "son"


@dataclass(frozen=True, slots=True)
class FixedCounterPlacementHandler:
    handler_id: str = "generic.fixed-counter-placement.v1"
    schema_version: int = 1
    family: str = "effect.counter-placement"
    operation: str = "place_counters"
    rule_references: tuple[str, ...] = (
        "122.1",
        "122.1a",
        "122.6",
        "608.2c",
    )
    capability_dependencies: tuple[str, ...] = (
        "counter.producer.fixed_effect",
    )

    def lower(
        self,
        effect: Mapping[str, Any],
        context: ReadOnlyHandlerContext,
    ) -> IntentPlan:
        fields = validate_direct_target_effect(
            effect,
            context,
            operation=self.operation,
            reference_field="card",
            family_label="Counter placement",
            allow_replacement_selections=True,
            additional_allowed_fields=("counter", "amount", "source"),
        )
        counter_name = effect.get("counter")
        if type(counter_name) is not str or not counter_name.strip():
            raise SemanticNodeError(
                "Counter placement requires one nonempty counter name"
            )
        amount = effect.get("amount")
        if type(amount) is not int or amount <= 0:
            raise SemanticNodeError(
                "Counter placement amount must be a positive exact integer"
            )
        source_ref = effect.get("source")
        if type(source_ref) is not str or not source_ref:
            raise SemanticNodeError(
                "Counter placement requires one nonempty source reference"
            )
        return IntentPlan(
            operation=self.operation,
            handler_id=self.handler_id,
            intents=(
                PlaceCountersIntent(
                    actor=context.actor,
                    object_refs=(fields.object_ref,),
                    counter_name=" ".join(counter_name.casefold().split()),
                    amount=amount,
                    reason=fields.reason,
                    source_ref=source_ref,
                    replacement_selections=fields.replacement_selections,
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class FixedPlayerCounterPlacementHandler:
    handler_id: str = "generic.fixed-player-counter-placement.v1"
    schema_version: int = 1
    family: str = "effect.player-counter-placement"
    operation: str = "place_player_counters"
    rule_references: tuple[str, ...] = (
        "101.4",
        "107.14",
        "107.17",
        "115.1",
        "122.1",
        "608.2b",
        "608.2c",
    )
    capability_dependencies: tuple[str, ...] = (
        "counter.producer.fixed_player_effect",
    )

    def lower(
        self,
        effect: Mapping[str, Any],
        context: ReadOnlyHandlerContext,
    ) -> IntentPlan:
        subject = effect.get("subjects")
        base_fields = {
            "op",
            "subjects",
            "counter",
            "amount",
            "source",
            _REASON_FIELD,
            "_replacement_selections",
        }
        allowed = base_fields | ({"target"} if subject == "target" else set())
        unknown = sorted(set(effect) - allowed)
        if unknown:
            raise SemanticNodeError(
                "Player counter effect has unknown fields: "
                + ", ".join(unknown)
            )
        if effect.get("op") != self.operation or subject not in {
            "controller",
            "target",
            "each-player",
            "each-opponent",
        }:
            raise SemanticNodeError(
                "Player counter placement subject is unsupported"
            )
        counter_name = effect.get("counter")
        if type(counter_name) is not str or not counter_name.strip():
            raise SemanticNodeError(
                "Player counter placement requires one nonempty counter name"
            )
        amount = effect.get("amount")
        if type(amount) is not int or amount <= 0:
            raise SemanticNodeError(
                "Player counter amount must be a positive exact integer"
            )
        source_ref = effect.get("source")
        if type(source_ref) is not str or not source_ref:
            raise SemanticNodeError(
                "Player counter placement requires one nonempty source reference"
            )
        reason = effect.get(_REASON_FIELD, context.default_reason)
        if type(reason) is not str or not reason:
            raise SemanticNodeError(
                "Player counter placement reason must be nonempty"
            )
        raw_selections = effect.get("_replacement_selections", ())
        if raw_selections is None:
            raw_selections = ()
        if not isinstance(raw_selections, (list, tuple)):
            raise SemanticNodeError(
                "Player counter replacement selections must be an array"
            )
        if subject == "controller":
            players = (context.query.require_active_seat(context.actor),)
        elif subject == "target":
            target = effect.get("target")
            if type(target) is not str or not target:
                raise SemanticNodeError(
                    "Targeted player counter placement requires one target"
                )
            players = (context.query.require_active_seat(target),)
        elif subject == "each-player":
            players = context.query.apnap_order
        else:
            players = tuple(
                player
                for player in context.query.apnap_order
                if player != context.actor
            )
        try:
            intent = PlacePlayerCountersIntent(
                actor=context.actor,
                player_ids=players,
                counter_name=counter_name,
                amount=amount,
                reason=reason,
                source_ref=source_ref,
                replacement_selections=tuple(raw_selections),
            )
        except (TypeError, ValueError) as exc:
            raise SemanticNodeError(str(exc)) from exc
        return IntentPlan(
            operation=self.operation,
            handler_id=self.handler_id,
            intents=(intent,),
        )


COUNTER_PLACEMENT_HANDLERS = (
    FixedCounterPlacementHandler(),
    FixedPlayerCounterPlacementHandler(),
)


__all__ = [
    "COUNTER_PLACEMENT_HANDLERS",
    "FixedCounterPlacementHandler",
    "FixedPlayerCounterPlacementHandler",
]
