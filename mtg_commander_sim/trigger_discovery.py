from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from .ability_fragments import (
    canonical_ability_fragments,
    granted_triggered_specs,
)
from .errors import GameRuleError
from .model import CardInstance, StackItem
from .semantics import SemanticProgram
from .trigger_processing import enqueue_trigger_batch


_DEPARTURE_EVENTS = frozenset(
    {
        "artifact.graveyard",
        "creature.dies",
        "permanent.graveyard",
        "permanent.leave",
    }
)
_ENTER_EVENTS = frozenset(
    {
        "permanent.enter",
        "artifact.enter",
        "creature.enter",
        "land.enter",
        "enchantment.enter",
    }
)

_CHOSEN_TYPE_TRIGGER_MULTIPLIER = (
    "if a triggered ability of another creature you control of the chosen "
    "type triggers, it triggers an additional time"
)


class TriggerDiscoveryHost(Protocol):
    state: Any
    active_seats: Sequence[str]
    seats: Sequence[str]
    semantics: Any

    def _semantic_event_sources(
        self, *, zones: set[str] | None = None
    ) -> list[CardInstance]: ...

    def _effective_card_data(
        self, card: str | CardInstance
    ) -> Mapping[str, Any]: ...

    def _type_parts(
        self, type_line: str
    ) -> tuple[set[str], set[str], set[str]]: ...

    def _resolve_object(
        self, actor: str, ref: str, *, zones: set[str]
    ) -> CardInstance: ...

    def card_record(self, card: CardInstance) -> Any: ...

    def semantic_program_is_current_trusted(
        self, program: SemanticProgram
    ) -> bool: ...

    def _pause_for_unsupported_semantic(
        self,
        *,
        program: SemanticProgram,
        event: str,
        source: CardInstance,
    ) -> None: ...

    def _next_ref(self, prefix: str) -> str: ...

    def _stable_runtime_id(self, kind: str, ref: str) -> str: ...


def semantic_event_value(
    host: TriggerDiscoveryHost,
    value: Any,
    *,
    source: CardInstance,
    context: Mapping[str, Any],
) -> Any:
    substitutions = {
        "$source.controller": source.controller,
        "$source.owner": source.owner,
        "$source.ref": source.ref,
        "$source.object_id": source.object_id,
        "$active_player": host.state.active_player,
    }
    if isinstance(value, str) and value in substitutions:
        return substitutions[value]
    if isinstance(value, str) and value.startswith("$context."):
        return context.get(value.removeprefix("$context."))
    if isinstance(value, list):
        return [
            semantic_event_value(
                host,
                item,
                source=source,
                context=context,
            )
            for item in value
        ]
    return value


def _semantic_condition_actual(
    host: TriggerDiscoveryHost,
    condition: Mapping[str, Any],
    *,
    source: CardInstance,
    context: Mapping[str, Any],
) -> Any:
    field = str(condition.get("field") or "")
    if not field:
        raise GameRuleError("Semantic event condition requires a field")
    if field == "source_controller_subtype_count":
        subtype = str(condition.get("subtype") or "").casefold()
        if not subtype:
            raise GameRuleError("Subtype-count condition requires a subtype")
        return sum(
            1
            for object_id in host.state.players[source.controller].zones[
                "battlefield"
            ]
            if host.state.cards[object_id].controller == source.controller
            and subtype
            in host._type_parts(
                str(host._effective_card_data(object_id).get("type_line") or "")
            )[1]
        )
    if field == "source_controller_type_count":
        card_type = str(condition.get("type") or "").casefold()
        if not card_type:
            raise GameRuleError("Type-count condition requires a card type")
        return sum(
            1
            for object_id in host.state.players[source.controller].zones[
                "battlefield"
            ]
            if host.state.cards[object_id].controller == source.controller
            and card_type
            in host._type_parts(
                str(host._effective_card_data(object_id).get("type_line") or "")
            )[0]
        )
    if field == "source_controller_controls_highest_artifact_mana_value":
        controlled_values: list[float] = []
        all_values: list[float] = []
        for active_seat in host.active_seats:
            for object_id in host.state.players[active_seat].zones["battlefield"]:
                permanent = host.state.cards[object_id]
                if permanent.phased_out:
                    continue
                data = host._effective_card_data(permanent)
                types, _, _ = host._type_parts(str(data.get("type_line") or ""))
                if "artifact" not in types:
                    continue
                value = float(data.get("mana_value") or 0)
                all_values.append(value)
                if permanent.controller == source.controller:
                    controlled_values.append(value)
        return bool(
            controlled_values and max(controlled_values) == max(all_values)
        )
    if field.startswith("source_annotation."):
        return source.annotations.get(field.removeprefix("source_annotation."))
    if field == "source_active_face":
        record = host.card_record(source)
        return source.active_face or (
            record.faces[0].get("name")
            if record is not None and record.faces
            else None
        )
    return context.get(field)


def _semantic_condition_operator_matches(
    op: str,
    actual: Any,
    expected: Any,
) -> bool:
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op == "in":
        return actual in (expected or [])
    if op == "not_in":
        return actual not in (expected or [])
    if op == "contains_any":
        return bool(set(actual or []).intersection(expected or []))
    if op == "gte":
        return actual is not None and actual >= expected
    if op == "gt":
        return actual is not None and actual > expected
    if op == "lte":
        return actual is not None and actual <= expected
    if op == "lt":
        return actual is not None and actual < expected
    if op == "truthy":
        return bool(actual)
    if op == "falsy":
        return not bool(actual)
    raise GameRuleError(
        f"Unsupported semantic event condition operator {op!r}"
    )


def semantic_event_condition_matches(
    host: TriggerDiscoveryHost,
    condition: Mapping[str, Any],
    *,
    source: CardInstance,
    context: Mapping[str, Any],
) -> bool:
    """Evaluate one read-only declarative condition over normalized facts."""

    if "all" in condition:
        values = condition.get("all")
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise GameRuleError("Semantic event 'all' must be a list")
        return all(
            semantic_event_condition_matches(
                host,
                dict(item),
                source=source,
                context=context,
            )
            for item in values
            if isinstance(item, Mapping)
        )
    if "any" in condition:
        values = condition.get("any")
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise GameRuleError("Semantic event 'any' must be a list")
        return any(
            semantic_event_condition_matches(
                host,
                dict(item),
                source=source,
                context=context,
            )
            for item in values
            if isinstance(item, Mapping)
        )
    if "not" in condition:
        nested = condition.get("not")
        if not isinstance(nested, Mapping):
            raise GameRuleError("Semantic event 'not' must be an object")
        return not semantic_event_condition_matches(
            host,
            nested,
            source=source,
            context=context,
        )

    actual = _semantic_condition_actual(
        host,
        condition,
        source=source,
        context=context,
    )
    expected = semantic_event_value(
        host,
        condition.get("value"),
        source=source,
        context=context,
    )
    return _semantic_condition_operator_matches(
        str(condition.get("op") or "eq"),
        actual,
        expected,
    )


def semantic_event_matches(
    host: TriggerDiscoveryHost,
    program: SemanticProgram,
    source: CardInstance,
    event: str,
    context: Mapping[str, Any],
    *,
    source_zone: str | None = None,
) -> bool:
    self_event = program.event.endswith(".self")
    program_event = (
        program.event.removesuffix(".self") if self_event else program.event
    )
    if program_event != event or program.active_zone != (
        source_zone or source.zone
    ):
        return False
    if self_event and str(context.get("card") or "") != source.ref:
        return False
    trigger_controller = (
        str(context.get("previous_controller"))
        if (
            self_event
            and context.get("previous_controller") is not None
            and event in _DEPARTURE_EVENTS
        )
        else source.controller
    )
    if trigger_controller not in host.active_seats:
        return False
    if program.event_condition is not None:
        return semantic_event_condition_matches(
            host,
            program.event_condition,
            source=source,
            context=context,
        )
    if event == "land.enter":
        entered = host._resolve_object(
            source.controller,
            str(context.get("card")),
            zones={"battlefield"},
        )
        return entered.controller == source.controller
    if event == "card.second_draw":
        return context.get("player") == source.controller
    if event == "step.begin":
        return (
            context.get("player") == source.controller
            and context.get("step") == "beginning_combat"
        )
    if event == "artifact.enter":
        entered = host._resolve_object(
            source.controller,
            str(context.get("card")),
            zones={"battlefield"},
        )
        return entered.controller == source.controller
    if event == "creature.dies" and not self_event:
        return context.get("previous_controller") == source.controller
    return True


def _trigger_controller(
    program: SemanticProgram,
    source: CardInstance,
    event: str,
    context: Mapping[str, Any],
) -> str:
    if (
        program.event.endswith(".self")
        and str(context.get("card") or "") == source.ref
        and context.get("previous_controller") is not None
        and event in _DEPARTURE_EVENTS
    ):
        return str(context["previous_controller"])
    return source.controller


def _additional_trigger_count(
    host: TriggerDiscoveryHost,
    *,
    source: CardInstance,
    controller: str,
    event: str,
    context: Mapping[str, Any],
) -> int:
    count = 1
    entering_types = {
        str(value).casefold() for value in context.get("types", [])
    }
    if (
        event in _ENTER_EVENTS
        and entering_types.intersection({"artifact", "creature"})
        and source.zone == "battlefield"
    ):
        count += sum(
            1
            for permanent_id in host.state.players[controller].zones[
                "battlefield"
            ]
            if host.state.cards[permanent_id].controller == controller
            and not host.state.cards[permanent_id].phased_out
            and (
                "if an artifact or creature entering causes a triggered "
                "ability of a permanent you control to trigger, that "
                "ability triggers an additional time"
                in str(
                    (
                        host.card_record(host.state.cards[permanent_id]).oracle_text
                        if host.card_record(host.state.cards[permanent_id])
                        is not None
                        else ""
                    )
                ).casefold()
            )
        )
    source_types, source_subtypes, _ = host._type_parts(
        str(host._effective_card_data(source).get("type_line") or "")
    )
    if "creature" in source_types:
        count += sum(
            1
            for permanent_id in host.state.players[controller].zones[
                "battlefield"
            ]
            if permanent_id != source.object_id
            if host.state.cards[permanent_id].controller == controller
            and not host.state.cards[permanent_id].phased_out
            and _CHOSEN_TYPE_TRIGGER_MULTIPLIER
            in str(
                (
                    host.card_record(host.state.cards[permanent_id]).oracle_text
                    if host.card_record(host.state.cards[permanent_id])
                    is not None
                    else ""
                )
            ).casefold()
            and str(
                host.state.cards[permanent_id].annotations.get(
                    "chosen_creature_type", ""
                )
            ).casefold()
            in source_subtypes
        )
    return count


def dispatch_semantic_event(
    host: TriggerDiscoveryHost,
    event: str,
    context: Mapping[str, Any],
    *,
    sources: Sequence[CardInstance] | None = None,
    source_zones: Mapping[str, str] | None = None,
    source_characteristics: Mapping[
        str, Mapping[str, Any]
    ] | None = None,
    trigger_batch: list[StackItem] | None = None,
) -> list[str]:
    """Detect data-driven triggers for one normalized authoritative event."""

    triggered: list[StackItem] = []
    candidates = (
        list(sources) if sources is not None else host._semantic_event_sources()
    )
    for source in candidates:
        active_zone = (
            source_zones.get(source.object_id, source.zone)
            if source_zones is not None
            else source.zone
        )
        programs = list(
            program
            for program in host.semantics.programs_for_oracle(
                source.oracle_id,
                active_zone=active_zone,
            )
            if not program.provenance.get("granted_only")
        )
        characteristics = (
            source_characteristics.get(source.object_id)
            if source_characteristics is not None
            else None
        ) or host._effective_card_data(source)
        for granted in granted_triggered_specs(
            canonical_ability_fragments(
                characteristics.get("ability_fragments", ())
            )
        ):
            if granted.event != event:
                continue
            program = host.semantics.get(granted.semantic_key)
            if program is None:
                raise GameRuleError(
                    "A typed granted trigger references an unknown "
                    f"semantic program {granted.semantic_key!r}"
                )
            if program.event != granted.event:
                raise GameRuleError(
                    "A typed granted trigger disagrees with its semantic "
                    "program event"
                )
            programs.append(program)
        for program in programs:
            if program.trust_level == "unresolved":
                continue
            if not semantic_event_matches(
                host,
                program,
                source,
                event,
                context,
                source_zone=active_zone,
            ):
                continue
            if (
                host.state.config.semantic_policy == "trusted_only"
                and not host.semantic_program_is_current_trusted(program)
            ):
                host._pause_for_unsupported_semantic(
                    program=program,
                    event=event,
                    source=source,
                )
                return [item.ref for item in triggered]
            ref = host._next_ref("S")
            item = StackItem(
                stack_id=host._stable_runtime_id("stack", ref),
                ref=ref,
                kind="triggered_ability",
                controller=_trigger_controller(program, source, event, context),
                label=program.label,
                source_object_id=source.object_id,
                semantic_key=program.key,
                visibility=list(host.seats),
                context={
                    "event": event,
                    **copy.deepcopy(dict(context)),
                    "source_logical_object_id": source.logical_object_id,
                    **(
                        {"trigger_target_selection_pending": True}
                        if program.target_schema
                        else {}
                    ),
                },
            )
            if (
                trigger_batch is not None
                and "one_or_more_event_batch" in program.coverage
                and any(
                    existing.semantic_key == item.semantic_key
                    and existing.source_object_id == item.source_object_id
                    and existing.context.get("event") == event
                    for existing in trigger_batch
                )
            ):
                continue
            triggered.append(item)
            for copy_index in range(
                1,
                _additional_trigger_count(
                    host,
                    source=source,
                    controller=item.controller,
                    event=event,
                    context=context,
                ),
            ):
                copy_ref = host._next_ref("S")
                copied = StackItem.from_dict(item.to_dict())
                copied.stack_id = host._stable_runtime_id("stack", copy_ref)
                copied.ref = copy_ref
                copied.context = {
                    **copy.deepcopy(item.context),
                    "additional_trigger_copy": copy_index,
                }
                triggered.append(copied)
            if "consume_evoked_marker" in program.coverage:
                source.annotations.pop("evoked", None)
    if trigger_batch is not None:
        trigger_batch.extend(triggered)
    elif triggered:
        enqueue_trigger_batch(host, triggered)
    return [item.ref for item in triggered]


__all__ = [
    "TriggerDiscoveryHost",
    "dispatch_semantic_event",
    "semantic_event_condition_matches",
    "semantic_event_matches",
    "semantic_event_value",
]
