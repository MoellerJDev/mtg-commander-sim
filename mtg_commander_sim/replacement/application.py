from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from .applicability import canonical_effects, replacement_choice
from .immutable import thaw_value
from .model import (
    AffectedObject,
    EntryReplacementScope,
    ReplaceableEvent,
    ReplacementChoice,
    ReplacementEffect,
    ReplacementEffectError,
    mapping_sequence,
    string_sequence,
)
from .operations import (
    AddAmount,
    AppendValues,
    CapResultLifeLoss,
    CreateNestedEvent,
    DredgeDraw,
    MultiplyAmount,
    PreventAmount,
    PreventDraw,
    PreventUsingShield,
    RedirectDamage,
    ReserveZoneChange,
    SetField,
    UnionValues,
)


_LIFE_LOSS_DIRECTION = "lo" + "ss"


_SET_FIELDS = {
    "damage": {"amount", "prevented", "prevented_by", "target"},
    "zone.change": {"destination"},
    "token.create": {"quantity", "created_types", "created_subtypes"},
    "counter.place": {"amount"},
    "counter.add": {"amount", "quantity"},
    "life.change": {"amount"},
    "draw.instruction": {"count"},
    "damage.results": {"life_loss_amount", "life_after_without_replacement"},
    "effect": {"resolved"},
}
_NUMERIC_FIELDS = {
    "damage": {"amount", "prevented"},
    "token.create": {"quantity"},
    "counter.place": {"amount"},
    "counter.add": {"amount", "quantity"},
    "life.change": {"amount"},
    "draw.instruction": {"count"},
}
_SEQUENCE_FIELDS = {
    "token.create": {"tokens", "created_types", "created_subtypes"},
}


def _require_field(
    event: ReplaceableEvent,
    field_name: str,
    allowed: Mapping[str, set[str]],
    *,
    operation: str,
) -> None:
    if field_name not in allowed.get(event.kind, set()):
        raise ReplacementEffectError(
            f"Replacement {operation} does not support {event.kind}.{field_name}"
        )


def _nested_event_from_mapping(
    parent: ReplaceableEvent,
    value: Mapping[str, Any],
    *,
    suffix: str,
) -> ReplaceableEvent:
    allowed = {
        "event_id",
        "kind",
        "affected_player",
        "affected_object",
        "payload",
        "applied_effects",
        "children",
        "entry_scope",
    }
    unknown = sorted(str(field) for field in set(value) - allowed)
    if unknown:
        raise ReplacementEffectError(
            "Nested replacement event has unknown field(s): "
            + ", ".join(unknown)
        )
    affected_object_value = value.get("affected_object")
    if affected_object_value is not None and not isinstance(
        affected_object_value, Mapping
    ):
        raise ReplacementEffectError(
            "Nested affected_object must be an object or null"
        )
    has_player = "affected_player" in value
    has_object = isinstance(affected_object_value, Mapping)
    if has_player and has_object:
        raise ReplacementEffectError(
            "A nested event cannot specify both affected subjects"
        )
    if has_player:
        affected_player = (
            str(value["affected_player"])
            if value.get("affected_player") is not None
            else None
        )
        affected_object = None
    elif has_object:
        affected_player = None
        affected_object = AffectedObject.from_dict(affected_object_value)
    else:
        affected_player = parent.affected_player
        affected_object = parent.affected_object
    payload = value["payload"] if "payload" in value else {}
    if not isinstance(payload, Mapping):
        raise ReplacementEffectError(
            "Nested replacement event payload must be an object"
        )
    entry_scope_value = value.get("entry_scope")
    if entry_scope_value is not None and not isinstance(
        entry_scope_value, Mapping
    ):
        raise ReplacementEffectError(
            "Nested entry_scope must be an object or null"
        )
    event = ReplaceableEvent(
        event_id=str(value.get("event_id") or f"{parent.event_id}/{suffix}"),
        kind=str(value.get("kind") or ""),
        affected_player=affected_player,
        affected_object=affected_object,
        payload=payload,
        applied_effects=string_sequence(
            value.get("applied_effects", ()),
            field_name="nested applied_effects",
        ),
        entry_scope=(
            EntryReplacementScope.from_dict(entry_scope_value)
            if isinstance(entry_scope_value, Mapping)
            else None
        ),
    )
    children = tuple(
        _nested_event_from_mapping(event, child, suffix=str(index))
        for index, child in enumerate(
            mapping_sequence(
                value.get("children", ()),
                field_name="nested event children",
            )
        )
    )
    if not children:
        return event
    return ReplaceableEvent(
        event_id=event.event_id,
        kind=event.kind,
        affected_player=event.affected_player,
        affected_object=event.affected_object,
        payload=event.payload,
        applied_effects=event.applied_effects,
        children=children,
        entry_scope=event.entry_scope,
    )


def _apply_result_life_floor(
    event: ReplaceableEvent,
    payload: dict[str, Any],
    children: list[ReplaceableEvent],
    operation: CapResultLifeLoss,
) -> None:
    if event.kind != "damage.results" or event.affected_player is None:
        raise ReplacementEffectError(
            "A damage-result life floor requires a player result event"
        )
    try:
        life_before = int(payload["life_before"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ReplacementEffectError(
            "A damage-result life floor requires the prior life total"
        ) from exc
    losses = [
        (index, child)
        for index, child in enumerate(children)
        if child.kind == "life.change"
        and child.affected_player == event.affected_player
        and child.payload.get("direction") == _LIFE_LOSS_DIRECTION
    ]
    gains = [
        child
        for child in children
        if child.kind == "life.change"
        and child.affected_player == event.affected_player
        and child.payload.get("direction") == "gain"
    ]
    if not losses:
        raise ReplacementEffectError(
            "A damage-result life floor requires a life-loss result"
        )
    loss_total = sum(int(child.payload.get("amount", 0)) for _, child in losses)
    gain_total = sum(int(child.payload.get("amount", 0)) for child in gains)
    if life_before - loss_total + gain_total >= operation.minimum:
        raise ReplacementEffectError(
            "A damage-result life floor is not applicable"
        )
    remaining = max(0, life_before + gain_total - operation.minimum)
    for index, child in losses:
        kept = min(int(child.payload.get("amount", 0)), remaining)
        remaining -= kept
        child_payload = thaw_value(child.payload)
        child_payload["amount"] = kept
        children[index] = ReplaceableEvent(
            event_id=child.event_id,
            kind=child.kind,
            affected_player=child.affected_player,
            affected_object=child.affected_object,
            payload=child_payload,
            applied_effects=child.applied_effects,
            children=child.children,
            entry_scope=child.entry_scope,
        )
    resolved_loss = sum(
        int(child.payload.get("amount", 0))
        for child in children
        if child.kind == "life.change"
        and child.affected_player == event.affected_player
        and child.payload.get("direction") == _LIFE_LOSS_DIRECTION
    )
    payload["life_loss_amount"] = resolved_loss
    payload["life_after_without_replacement"] = life_before - resolved_loss + gain_total


def _apply_operation(
    event: ReplaceableEvent,
    payload: dict[str, Any],
    children: list[ReplaceableEvent],
    entry_scope: EntryReplacementScope | None,
    operation: Any,
) -> EntryReplacementScope | None:
    if isinstance(operation, SetField):
        _require_field(event, operation.field, _SET_FIELDS, operation="set")
        payload[operation.field] = thaw_value(operation.value)
        return entry_scope
    if isinstance(operation, AddAmount):
        _require_field(event, operation.field, _NUMERIC_FIELDS, operation="add")
        payload[operation.field] = int(payload.get(operation.field, 0)) + operation.amount
        return entry_scope
    if isinstance(operation, MultiplyAmount):
        _require_field(event, operation.field, _NUMERIC_FIELDS, operation="multiply")
        payload[operation.field] = int(payload.get(operation.field, 0)) * operation.factor
        return entry_scope
    if isinstance(operation, PreventAmount):
        if event.kind != "damage":
            raise ReplacementEffectError(
                "Damage prevention can apply only to a damage event"
            )
        available = int(payload.get("amount", 0))
        requested = available if operation.amount is None else operation.amount
        if available < 0:
            raise ReplacementEffectError("Damage amounts cannot be negative")
        prevented = 0 if bool(payload.get("unpreventable")) else min(available, requested)
        payload["amount"] = available - prevented
        payload["prevented"] = int(payload.get("prevented", 0)) + prevented
        return entry_scope
    if isinstance(operation, PreventUsingShield):
        raise ReplacementEffectError(
            "Durable shield prevention requires a replacement batch boundary"
        )
    if isinstance(operation, RedirectDamage):
        raise ReplacementEffectError(
            "Damage redirection requires subject-aware replacement application"
        )
    if isinstance(operation, (AppendValues, UnionValues)):
        _require_field(
            event, operation.field, _SEQUENCE_FIELDS, operation="sequence"
        )
        current = payload.get(operation.field, [])
        if not isinstance(current, Sequence) or isinstance(current, (str, bytes)):
            raise ReplacementEffectError(
                "Replacement sequence destination must be an array"
            )
        values = [*list(current), *[thaw_value(value) for value in operation.values]]
        payload[operation.field] = (
            values
            if isinstance(operation, AppendValues)
            else sorted(set(values), key=str)
        )
        return entry_scope
    if isinstance(operation, CreateNestedEvent):
        children.append(
            _nested_event_from_mapping(
                event,
                thaw_value(operation.event),
                suffix=str(len(children)),
            )
        )
        return entry_scope
    if isinstance(operation, ReserveZoneChange):
        if event.kind != "zone.change" or entry_scope is None:
            raise ReplacementEffectError(
                "Zone-change reservation requires a scoped zone-change event"
            )
        values: Any = operation.objects
        if operation.from_field is not None:
            values = payload.get(operation.from_field, ())
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            raise ReplacementEffectError(
                "Zone-change reservation requires object IDs"
            )
        return entry_scope.reserve_zone_changes(str(value) for value in values)
    if isinstance(operation, CapResultLifeLoss):
        _apply_result_life_floor(event, payload, children, operation)
        return entry_scope
    if isinstance(operation, PreventDraw):
        if event.kind != "draw" or payload.get("is_draw") is not True:
            raise ReplacementEffectError(
                "Draw prevention requires an unresolved draw event"
            )
        payload["is_draw"] = False
        payload["result_kind"] = "prevented"
        return entry_scope
    if isinstance(operation, DredgeDraw):
        if event.kind != "draw" or payload.get("is_draw") is not True:
            raise ReplacementEffectError(
                "Dredge requires an unresolved draw event"
            )
        library_size = payload.get("library_size")
        if type(library_size) is not int or library_size < operation.mill_count:
            raise ReplacementEffectError(
                "Dredge requires enough cards in the affected library"
            )
        payload.update(
            {
                "is_draw": False,
                "result_kind": "dredge",
                "dredge_source_ref": operation.source_ref,
                "dredge_source_object_id": operation.source_object_id,
                "dredge_source_zone_change_counter": (
                    operation.source_zone_change_counter
                ),
                "dredge_mill_count": operation.mill_count,
            }
        )
        return entry_scope
    raise ReplacementEffectError("Unknown typed replacement operation")


def canonical_replacement_selection(
    choice: ReplacementChoice, selected_effect_id: str | None
) -> str:
    if selected_effect_id is None:
        if len(choice.options) != 1 or choice.options[0] not in choice.optional_options:
            raise ReplacementEffectError(
                "A decline must identify one currently optional replacement"
            )
        return f"decline:{choice.options[0]}"
    if not isinstance(selected_effect_id, str) or not selected_effect_id:
        raise ReplacementEffectError(
            "A replacement selection must be a nonempty string"
        )
    return selected_effect_id


def apply_replacement(
    choice: ReplacementChoice,
    effects: Iterable[ReplacementEffect],
    selected_effect_id: str | None,
) -> ReplaceableEvent:
    all_effects = canonical_effects(effects)
    by_id = {effect.effect_id: effect for effect in all_effects}
    selection = canonical_replacement_selection(choice, selected_effect_id)
    if selection.startswith("decline:"):
        declined = selection.removeprefix("decline:")
        if declined not in choice.options or declined not in choice.optional_options:
            raise ReplacementEffectError(
                "Selected replacement cannot currently be declined"
            )
        return choice.event.with_payload(
            choice.event.payload, applied_effect=declined
        )
    if selection not in choice.options:
        raise ReplacementEffectError(
            "Selected replacement is not currently applicable"
        )
    effect = by_id[selection]
    payload = thaw_value(choice.event.payload)
    children = list(choice.event.children)
    entry_scope = choice.event.entry_scope
    affected_player = choice.event.affected_player
    affected_object = choice.event.affected_object
    for operation in effect.operations:
        if isinstance(operation, RedirectDamage):
            if choice.event.kind != "damage":
                raise ReplacementEffectError(
                    "Damage redirection can apply only to a damage event"
                )
            payload.update(
                {
                    "target": operation.target,
                    "target_kind": operation.target_kind,
                    "target_object_id": operation.target_object_id,
                    "target_logical_object_id": (
                        operation.target_logical_object_id
                    ),
                    "target_controller": operation.target_controller,
                    "target_owner": operation.target_owner,
                    "target_types": list(operation.target_types),
                    "target_subtypes": list(operation.target_subtypes),
                    "target_characteristics": sorted(
                        {*operation.target_types, *operation.target_subtypes}
                    ),
                }
            )
            if operation.target_kind == "player":
                affected_player = operation.target
                affected_object = None
            else:
                assert operation.target_object_id is not None
                assert operation.target_owner is not None
                affected_player = None
                affected_object = AffectedObject(
                    object_id=operation.target_object_id,
                    owner=operation.target_owner,
                    controller=operation.target_controller,
                )
            continue
        prevented_before = int(payload.get("prevented", 0))
        entry_scope = _apply_operation(
            choice.event, payload, children, entry_scope, operation
        )
        if isinstance(operation, PreventAmount):
            prevented = int(payload.get("prevented", 0)) - prevented_before
            by_effect = dict(payload.get("prevention_applied") or {})
            by_effect[effect.effect_id] = (
                int(by_effect.get(effect.effect_id, 0)) + prevented
            )
            payload["prevention_applied"] = by_effect
    chooser_history = dict(payload.get("replacement_choosers") or {})
    chooser_history[effect.effect_id] = choice.event.chooser
    payload["replacement_choosers"] = chooser_history
    return ReplaceableEvent(
        event_id=choice.event.event_id,
        kind=choice.event.kind,
        affected_player=affected_player,
        affected_object=affected_object,
        payload=payload,
        applied_effects=(*choice.event.applied_effects, effect.effect_id),
        children=tuple(children),
        entry_scope=entry_scope,
    )


def resolve_replacements(
    event: ReplaceableEvent,
    effects: Iterable[ReplacementEffect],
    *,
    selections: Iterable[str | None],
) -> ReplaceableEvent:
    all_effects = canonical_effects(effects)
    supplied = iter(selections)
    current = event
    while choice := replacement_choice(current, all_effects):
        try:
            selected = next(supplied)
        except StopIteration as exc:
            raise ReplacementEffectError(
                "Replacement choice sequence ended early"
            ) from exc
        current = apply_replacement(choice, all_effects, selected)
    try:
        next(supplied)
    except StopIteration:
        return current
    raise ReplacementEffectError(
        "Replacement choice sequence contains unused choices"
    )
