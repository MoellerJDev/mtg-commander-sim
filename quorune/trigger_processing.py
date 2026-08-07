from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from .errors import GameRuleError, StateInvariantError
from .model import DelayedTrigger, StackItem
from .trigger_batches import (
    PendingTriggerItem,
    TriggerBatchError,
    begin_pending_trigger_placement,
    complete_pending_trigger_group,
    create_pending_trigger_batch,
    merge_pending_trigger_batch,
)


class TriggerProcessingHost(Protocol):
    """Narrow authoritative services around the pure CR 603.3 owner."""

    state: Any
    active_seats: Sequence[str]
    seats: Sequence[str]

    def apnap_order(self) -> Sequence[str]: ...

    def _dispatch_semantic_event(
        self,
        event_kind: str,
        context: Mapping[str, Any],
        *,
        trigger_batch: list[StackItem],
    ) -> Any: ...

    def _semantic_pause_annotation(self) -> Any: ...

    def _matching_delayed_triggers(
        self,
        event_kind: str,
        context: Mapping[str, Any],
    ) -> list[DelayedTrigger]: ...

    def _delayed_trigger_stack_item(
        self,
        trigger: DelayedTrigger,
    ) -> StackItem: ...

    def _process_trigger_groups(
        self,
        controller: str,
        options: Sequence[tuple[str, str]],
        continuation: Mapping[str, Any],
    ) -> None: ...

    def _next_ref(self, prefix: str) -> str: ...

    def _stable_runtime_id(self, kind: str, ref: str) -> str: ...

    def _grant_priority(self, seat: str | None) -> None: ...

    def _log(self, *args: Any, **kwargs: Any) -> None: ...


def collect_trigger_items(
    host: TriggerProcessingHost,
    event_kind: str,
    context: Mapping[str, Any],
    *,
    held_triggers: Sequence[StackItem] = (),
) -> list[StackItem]:
    """Discover represented abilities into one ordinary occurrence type."""

    triggered = list(held_triggers)
    host._dispatch_semantic_event(
        event_kind,
        context,
        trigger_batch=triggered,
    )
    if host._semantic_pause_annotation() is not None:
        return triggered
    triggered.extend(
        host._delayed_trigger_stack_item(trigger)
        for trigger in host._matching_delayed_triggers(event_kind, context)
    )
    return triggered


def enqueue_trigger_batch(
    host: TriggerProcessingHost,
    items: Sequence[StackItem],
) -> None:
    """Merge already-detected occurrences until CR 603.3 placement starts."""

    if not items:
        return
    pending_items = [
        PendingTriggerItem.from_dict(item.to_dict())
        for item in items
        if item.controller in host.active_seats
    ]
    if not pending_items:
        return
    if host.state.pending_trigger_batches:
        pending = host.state.pending_trigger_batches[-1]
        try:
            merged = merge_pending_trigger_batch(
                pending,
                pending_items,
                apnap_order=host.apnap_order(),
                priority_epoch=host.state.priority_epoch,
            )
        except TriggerBatchError as exc:
            raise StateInvariantError(str(exc)) from exc
        if merged is not None:
            host.state.pending_trigger_batches[-1] = merged
            return
    batch_ref = host._next_ref("TB")
    try:
        batch = create_pending_trigger_batch(
            batch_id=host._stable_runtime_id("trigger-batch", batch_ref),
            ref=batch_ref,
            items=pending_items,
            apnap_order=host.apnap_order(),
            turn_sequence=host.state.turn_sequence,
            priority_epoch=host.state.priority_epoch,
        )
    except TriggerBatchError as exc:
        raise StateInvariantError(str(exc)) from exc
    host.state.pending_trigger_batches.append(batch)


def place_trigger_items(
    host: TriggerProcessingHost,
    values: Sequence[PendingTriggerItem | Mapping[str, Any]],
) -> None:
    """Append validated ordinary triggered abilities to the public stack."""

    for value in values:
        payload = (
            value.to_dict()
            if isinstance(value, PendingTriggerItem)
            else copy.deepcopy(dict(value))
        )
        item = StackItem.from_dict(payload)
        host.state.stack.append(item)
        source = (
            host.state.cards.get(item.source_object_id)
            if item.source_object_id
            else None
        )
        host._log(
            item.controller,
            "stack.trigger",
            f"Queued {item.ref}: {item.label}.",
            {
                "stack": item.ref,
                "source": source.ref if source else None,
                "semantic_program": item.semantic_key,
                "event": item.context.get("event"),
                "trigger": item.context.get("delayed_trigger_ref"),
            },
            importance=2,
            changed_objects=(
                [source.object_id] if source is not None else []
            ),
        )


def begin_pending_trigger_batch(host: TriggerProcessingHost) -> bool:
    """Place waiting groups or issue one same-controller order decision."""

    while host.state.pending_trigger_batches:
        batch = host.state.pending_trigger_batches[0]
        try:
            started = begin_pending_trigger_placement(
                batch,
                apnap_order=host.apnap_order(),
            )
        except TriggerBatchError as exc:
            raise StateInvariantError(str(exc)) from exc
        if started is None:
            host.state.pending_trigger_batches.pop(0)
            continue
        if started is not batch:
            host.state.pending_trigger_batches[0] = started
        batch = started
        group = batch.groups[0]
        if len(group.items) > 1:
            host._process_trigger_groups(
                group.controller,
                [(item.ref, item.label) for item in group.items],
                {
                    "trigger_batch_id": batch.batch_id,
                    "trigger_refs": [item.ref for item in group.items],
                },
            )
            return True
        try:
            ordered, remaining = complete_pending_trigger_group(
                batch,
                controller=group.controller,
                refs=[group.items[0].ref],
            )
        except TriggerBatchError as exc:
            raise StateInvariantError(str(exc)) from exc
        place_trigger_items(host, ordered)
        if remaining is None:
            host.state.pending_trigger_batches.pop(0)
        else:
            host.state.pending_trigger_batches[0] = remaining
    return False


def start_delayed_trigger_batch(
    host: TriggerProcessingHost,
    triggers: Sequence[DelayedTrigger],
    *,
    after: str,
) -> None:
    """Compatibility entry point for callers holding delayed records."""

    if after != "grant_priority":
        raise GameRuleError(
            "The generic trigger batch supports only priority placement"
        )
    enqueue_trigger_batch(
        host,
        [host._delayed_trigger_stack_item(trigger) for trigger in triggers],
    )
    if begin_pending_trigger_batch(host):
        return
    host._grant_priority(host.state.active_player)


def complete_trigger_order(
    host: TriggerProcessingHost,
    *,
    controller: str,
    values: Sequence[Any],
    continuation: Mapping[str, Any],
) -> None:
    """Complete a current or explicitly compatible historical order frame."""

    batch_id = continuation.get("trigger_batch_id") or continuation.get(
        "semantic_trigger_batch_id"
    )
    if batch_id is None and "trigger_ids" in continuation:
        _complete_legacy_delayed_trigger_order(
            host,
            controller=controller,
            values=values,
            continuation=continuation,
        )
        return
    if type(batch_id) is not str or not batch_id:
        raise GameRuleError("Trigger-order continuation is malformed")
    batch_key = (
        "trigger_batch_id"
        if "trigger_batch_id" in continuation
        else "semantic_trigger_batch_id"
    )
    if set(continuation) != {batch_key, "trigger_refs"}:
        raise GameRuleError("Trigger-order continuation is malformed")
    continuation_refs = continuation.get("trigger_refs")
    if (
        not isinstance(continuation_refs, list)
        or not continuation_refs
        or any(
            type(value) is not str or not value
            for value in continuation_refs
        )
        or len(set(continuation_refs)) != len(continuation_refs)
    ):
        raise GameRuleError("Trigger-order continuation is malformed")
    batch_index = next(
        (
            index
            for index, batch in enumerate(host.state.pending_trigger_batches)
            if batch.batch_id == batch_id
        ),
        None,
    )
    if batch_index is None:
        raise GameRuleError("Trigger batch is no longer pending")
    batch = host.state.pending_trigger_batches[batch_index]
    if (
        not batch.groups
        or sorted(continuation_refs)
        != sorted(item.ref for item in batch.groups[0].items)
    ):
        raise GameRuleError("Trigger-order continuation is stale")
    try:
        ordered, remaining = complete_pending_trigger_group(
            batch,
            controller=controller,
            refs=values,
        )
    except TriggerBatchError as exc:
        raise GameRuleError(str(exc)) from exc
    place_trigger_items(host, ordered)
    if remaining is None:
        host.state.pending_trigger_batches.pop(batch_index)
    else:
        host.state.pending_trigger_batches[batch_index] = remaining
    if begin_pending_trigger_batch(host):
        return
    host._grant_priority(host.state.active_player)


def _complete_legacy_delayed_trigger_order(
    host: TriggerProcessingHost,
    *,
    controller: str,
    values: Sequence[Any],
    continuation: Mapping[str, Any],
) -> None:
    if set(continuation) != {"groups", "after", "trigger_ids"} or (
        continuation.get("after") != "grant_priority"
    ):
        raise GameRuleError(
            "Historical delayed-trigger continuation is malformed"
        )
    raw_ids = continuation.get("trigger_ids")
    if not isinstance(raw_ids, list):
        raise GameRuleError(
            "Historical delayed-trigger continuation is malformed"
        )
    ids = list(raw_ids)
    if (
        not ids
        or len(set(ids)) != len(ids)
        or any(type(value) is not str or not value for value in ids)
    ):
        raise GameRuleError(
            "Historical delayed-trigger continuation is malformed"
        )
    available = {
        trigger.trigger_id: trigger
        for trigger in host.state.delayed_triggers
        if trigger.trigger_id in ids
    }
    if any(trigger.controller != controller for trigger in available.values()):
        raise GameRuleError("Only the trigger controller may order this group")
    by_ref = {
        trigger.ref: trigger_id for trigger_id, trigger in available.items()
    }
    resolved = [by_ref.get(str(value), str(value)) for value in values]
    if sorted(resolved) != sorted(ids) or len(available) != len(ids):
        raise GameRuleError(
            "Trigger order must contain every listed trigger exactly once"
        )
    groups = continuation.get("groups", [])
    if not isinstance(groups, list):
        raise GameRuleError("Historical delayed-trigger groups are malformed")
    _validate_legacy_delayed_trigger_groups(
        host,
        groups,
        already_seen=ids,
    )
    place_trigger_items(
        host,
        [
            PendingTriggerItem.from_dict(
                host._delayed_trigger_stack_item(available[trigger_id]).to_dict()
            )
            for trigger_id in resolved
        ],
    )
    _resume_legacy_delayed_trigger_groups(host, groups)


def _validate_legacy_delayed_trigger_groups(
    host: TriggerProcessingHost,
    groups: Sequence[Any],
    *,
    already_seen: Sequence[str],
) -> None:
    seen = set(already_seen)
    for raw_group in groups:
        if not isinstance(raw_group, Mapping) or set(raw_group) != {
            "controller",
            "trigger_ids",
        }:
            raise GameRuleError("Historical delayed-trigger group is malformed")
        controller = raw_group["controller"]
        ids = raw_group["trigger_ids"]
        if (
            type(controller) is not str
            or not controller
            or not isinstance(ids, list)
            or not ids
            or any(type(value) is not str or not value for value in ids)
            or len(set(ids)) != len(ids)
            or seen.intersection(ids)
        ):
            raise GameRuleError("Historical delayed-trigger group is malformed")
        triggers = {
            trigger.trigger_id: trigger
            for trigger in host.state.delayed_triggers
            if trigger.trigger_id in ids
        }
        if len(triggers) != len(ids) or any(
            trigger.controller != controller for trigger in triggers.values()
        ):
            raise GameRuleError(
                "Historical delayed trigger is no longer available"
            )
        seen.update(ids)


def _resume_legacy_delayed_trigger_groups(
    host: TriggerProcessingHost,
    groups: Sequence[Any],
) -> None:
    remaining = list(groups)
    while remaining:
        raw_group = remaining.pop(0)
        controller = raw_group["controller"]
        ids = raw_group["trigger_ids"]
        triggers = [
            next(
                trigger
                for trigger in host.state.delayed_triggers
                if trigger.trigger_id == trigger_id
            )
            for trigger_id in ids
        ]
        if len(triggers) > 1:
            host._process_trigger_groups(
                controller,
                [(trigger.ref, trigger.label) for trigger in triggers],
                {
                    "groups": remaining,
                    "after": "grant_priority",
                    "trigger_ids": ids,
                },
            )
            return
        place_trigger_items(
            host,
            [
                PendingTriggerItem.from_dict(
                    host._delayed_trigger_stack_item(triggers[0]).to_dict()
                )
            ],
        )
    host._grant_priority(host.state.active_player)


__all__ = [
    "TriggerProcessingHost",
    "begin_pending_trigger_batch",
    "collect_trigger_items",
    "complete_trigger_order",
    "enqueue_trigger_batch",
    "place_trigger_items",
    "start_delayed_trigger_batch",
]
