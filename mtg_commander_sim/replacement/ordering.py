from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from .applicability import canonical_effects, replacement_choice
from .application import (
    apply_replacement,
    canonical_replacement_selection,
)
from .model import (
    PreventionAllocationChoice,
    ReplaceableEvent,
    ReplacementBatchChoice,
    ReplacementBatchProgress,
    ReplacementChoice,
    ReplacementEffect,
    ReplacementEffectError,
    ReplacementEventBatch,
    ReplacementSelection,
    ReplacementTreeChoice,
)
from .immutable import thaw_value
from .operations import PreventUsingShield


class ReplacementChoiceRequired(ReplacementEffectError):
    """Raised only at an engine suspension boundary before event commit."""

    def __init__(
        self,
        *,
        batch: ReplacementEventBatch,
        effects: Sequence[ReplacementEffect],
        pending: ReplacementBatchChoice,
    ) -> None:
        super().__init__(
            f"{pending.choice.chooser} must choose a replacement effect"
        )
        self.batch = batch
        self.effects = canonical_effects(effects)
        self.pending = pending


def replacement_tree_choice(
    event: ReplaceableEvent,
    effects: Iterable[ReplacementEffect],
) -> ReplacementTreeChoice | None:
    """Return the first choice in containing-before-contained order."""

    all_effects = canonical_effects(effects)

    def visit(
        current: ReplaceableEvent, path: tuple[int, ...]
    ) -> ReplacementTreeChoice | None:
        choice = replacement_choice(current, all_effects)
        if choice is not None:
            return ReplacementTreeChoice(path=path, choice=choice)
        for index, child in enumerate(current.children):
            nested = visit(child, (*path, index))
            if nested is not None:
                return nested
        return None

    return visit(event, ())


def _replace_event_at_path(
    event: ReplaceableEvent,
    path: tuple[int, ...],
    replacement: ReplaceableEvent,
) -> ReplaceableEvent:
    if not path:
        return replacement
    index = path[0]
    if index < 0 or index >= len(event.children):
        raise ReplacementEffectError(
            "Replacement event path is no longer valid"
        )
    children = list(event.children)
    children[index] = _replace_event_at_path(
        children[index], path[1:], replacement
    )
    return ReplaceableEvent(
        event_id=event.event_id,
        kind=event.kind,
        affected_player=event.affected_player,
        affected_object=event.affected_object,
        payload=event.payload,
        applied_effects=event.applied_effects,
        children=tuple(children),
        entry_scope=event.entry_scope,
    )


def apply_tree_replacement(
    event: ReplaceableEvent,
    effects: Iterable[ReplacementEffect],
    pending: ReplacementTreeChoice,
    selected_effect_id: str | None,
) -> ReplaceableEvent:
    all_effects = canonical_effects(effects)
    current = replacement_tree_choice(event, all_effects)
    if current is None or current != pending:
        raise ReplacementEffectError(
            "Replacement tree choice is stale or out of order"
        )
    changed = apply_replacement(
        pending.choice, all_effects, selected_effect_id
    )
    return _replace_event_at_path(event, pending.path, changed)


def next_batch_replacement_choice(
    batch: ReplacementEventBatch,
    effects: Iterable[ReplacementEffect],
) -> ReplacementBatchChoice | None:
    all_effects = canonical_effects(effects)
    order = {seat: index for index, seat in enumerate(batch.apnap_order)}
    candidates: list[tuple[int, str, int, ReplacementTreeChoice]] = []
    for event_index, event in enumerate(batch.events):
        pending = replacement_tree_choice(event, all_effects)
        if pending is None:
            continue
        chooser_index = order.get(pending.choice.chooser)
        if chooser_index is None:
            raise ReplacementEffectError(
                "Nested replacement chooser is absent from APNAP order"
            )
        candidates.append(
            (chooser_index, event.event_id, event_index, pending)
        )
    if not candidates:
        return None
    _, event_id, event_index, pending = min(
        candidates,
        key=lambda value: (
            value[0],
            value[1],
            value[3].path,
            value[2],
        ),
    )
    base = ReplacementBatchChoice(
        batch_id=batch.batch_id,
        event_index=event_index,
        event_id=event_id,
        tree_choice=pending,
        prior_public_choices=batch.journal,
    )
    allocations: list[PreventionAllocationChoice] = []
    effects_by_id = {effect.effect_id: effect for effect in all_effects}
    for effect_id in pending.choice.options:
        effect = effects_by_id[effect_id]
        shield_operations = tuple(
            operation
            for operation in effect.operations
            if isinstance(operation, PreventUsingShield)
        )
        if not shield_operations:
            continue
        if len(effect.operations) != 1 or len(shield_operations) != 1:
            raise ReplacementEffectError(
                "Durable shield effects require one typed prevention operation"
            )
        operation = shield_operations[0]
        matching: list[tuple[str, int, bool]] = []
        for candidate in batch.events:
            candidate_choice = replacement_tree_choice(candidate, all_effects)
            if (
                candidate_choice is None
                or candidate_choice.path
                or candidate_choice.choice.chooser != pending.choice.chooser
                or effect_id not in candidate_choice.choice.options
            ):
                continue
            amount = candidate.payload.get("amount")
            if type(amount) is not int or amount < 0:
                raise ReplacementEffectError(
                    "Shield prevention requires nonnegative damage amounts"
                )
            matching.append(
                (
                    candidate.event_id,
                    amount,
                    bool(candidate.payload.get("unpreventable")),
                )
            )
        preventable = [
            amount
            for _event_id, amount, unpreventable in matching
            if not unpreventable and amount > 0
        ]
        required = bool(
            operation.remaining is not None
            and len(preventable) > 1
            and sum(preventable) > operation.remaining
        )
        allocations.append(
            PreventionAllocationChoice(
                effect_id=effect_id,
                shield_id=operation.shield_id,
                available=operation.remaining,
                events=tuple(sorted(matching)),
                allocation_required=required,
            )
        )
    if not allocations:
        return base
    return ReplacementBatchChoice(
        batch_id=base.batch_id,
        event_index=base.event_index,
        event_id=base.event_id,
        tree_choice=base.tree_choice,
        prior_public_choices=base.prior_public_choices,
        prevention_allocations=tuple(allocations),
    )


def _selection_parts(
    selected: str | None | Mapping[str, Any],
) -> tuple[str | None, Mapping[str, Any] | None]:
    if selected is None or isinstance(selected, str):
        return selected, None
    if not isinstance(selected, Mapping):
        raise ReplacementEffectError(
            "Replacement selections must be strings or typed objects"
        )
    actual = set(selected)
    expected = {"effect_id", "allocation"}
    if actual != expected:
        raise ReplacementEffectError(
            "Typed replacement selections require effect_id and allocation"
        )
    effect_id = selected["effect_id"]
    allocation = selected["allocation"]
    if not isinstance(effect_id, str) or not effect_id:
        raise ReplacementEffectError(
            "Typed replacement selections require a stable effect ID"
        )
    if not isinstance(allocation, Mapping):
        raise ReplacementEffectError(
            "Typed replacement prevention allocation must be an object"
        )
    return effect_id, allocation


def _validated_allocation(
    choice: PreventionAllocationChoice,
    supplied: Mapping[str, Any] | None,
) -> dict[str, int]:
    automatic = choice.automatic_allocation
    if supplied is None:
        if automatic is None:
            raise ReplacementEffectError(
                "The affected player must divide the prevention amount"
            )
        return automatic
    event_amounts = {
        event_id: (amount, unpreventable)
        for event_id, amount, unpreventable in choice.events
    }
    unknown = sorted(str(value) for value in set(supplied) - set(event_amounts))
    if unknown:
        raise ReplacementEffectError(
            "Prevention allocation contains unknown damage event(s): "
            + ", ".join(unknown)
        )
    allocation: dict[str, int] = {}
    for event_id in event_amounts:
        amount = supplied.get(event_id, 0)
        maximum, unpreventable = event_amounts[event_id]
        if type(amount) is not int or amount < 0 or amount > maximum:
            raise ReplacementEffectError(
                "Prevention allocations must be nonnegative and no greater "
                "than the current damage amount"
            )
        if unpreventable and amount:
            raise ReplacementEffectError(
                "Unpreventable damage cannot receive a prevention allocation"
            )
        allocation[event_id] = amount
    preventable_total = sum(
        amount
        for _event_id, amount, unpreventable in choice.events
        if not unpreventable
    )
    required_total = (
        preventable_total
        if choice.available is None
        else min(choice.available, preventable_total)
    )
    if sum(allocation.values()) != required_total:
        raise ReplacementEffectError(
            f"Prevention allocation must total {required_total}"
        )
    return allocation


def _apply_shield_prevention(
    batch: ReplacementEventBatch,
    pending: ReplacementBatchChoice,
    allocation_choice: PreventionAllocationChoice,
    supplied: Mapping[str, Any] | None,
) -> ReplacementEventBatch:
    allocation = _validated_allocation(allocation_choice, supplied)
    matching = {event_id for event_id, _amount, _flag in allocation_choice.events}
    events: list[ReplaceableEvent] = []
    for event in batch.events:
        if event.event_id not in matching:
            events.append(event)
            continue
        payload = thaw_value(event.payload)
        prevented = allocation.get(event.event_id, 0)
        available = int(payload.get("amount", 0))
        if prevented > available:
            raise ReplacementEffectError(
                "Prevention allocation exceeds current damage"
            )
        payload["amount"] = available - prevented
        payload["prevented"] = int(payload.get("prevented", 0)) + prevented
        by_effect = dict(payload.get("prevention_applied") or {})
        by_effect[allocation_choice.effect_id] = prevented
        payload["prevention_applied"] = by_effect
        chooser_history = dict(payload.get("replacement_choosers") or {})
        chooser_history[allocation_choice.effect_id] = (
            pending.choice.chooser
        )
        payload["replacement_choosers"] = chooser_history
        events.append(
            ReplaceableEvent(
                event_id=event.event_id,
                kind=event.kind,
                affected_player=event.affected_player,
                affected_object=event.affected_object,
                payload=payload,
                applied_effects=(
                    *event.applied_effects,
                    allocation_choice.effect_id,
                ),
                children=event.children,
                entry_scope=event.entry_scope,
            )
        )
    journal_allocation = {
        event_id: amount for event_id, amount in allocation.items() if amount
    }
    return ReplacementEventBatch(
        batch_id=batch.batch_id,
        events=tuple(events),
        apnap_order=batch.apnap_order,
        journal=(
            *batch.journal,
            ReplacementSelection(
                event_id=pending.event_id,
                path=pending.path,
                chooser=pending.choice.chooser,
                effect_id=allocation_choice.effect_id,
                allocation=(journal_allocation or None),
            ),
        ),
    )


def apply_batch_replacement(
    batch: ReplacementEventBatch,
    effects: Iterable[ReplacementEffect],
    pending: ReplacementBatchChoice,
    selected_effect_id: str | None | Mapping[str, Any],
) -> ReplacementEventBatch:
    all_effects = canonical_effects(effects)
    current = next_batch_replacement_choice(batch, all_effects)
    if current is None or current != pending:
        raise ReplacementEffectError(
            "Replacement batch choice is stale or violates APNAP order"
        )
    selected_value, supplied_allocation = _selection_parts(
        selected_effect_id
    )
    canonical_selection = canonical_replacement_selection(
        pending.choice, selected_value
    )
    allocation_choice = next(
        (
            value
            for value in pending.prevention_allocations
            if value.effect_id == canonical_selection
        ),
        None,
    )
    if allocation_choice is not None:
        return _apply_shield_prevention(
            batch,
            pending,
            allocation_choice,
            supplied_allocation,
        )
    if supplied_allocation is not None:
        raise ReplacementEffectError(
            "Only a durable prevention shield accepts an allocation"
        )
    events = list(batch.events)
    events[pending.event_index] = apply_tree_replacement(
        events[pending.event_index],
        all_effects,
        pending.tree_choice,
        canonical_selection,
    )
    return ReplacementEventBatch(
        batch_id=batch.batch_id,
        events=tuple(events),
        apnap_order=batch.apnap_order,
        journal=(
            *batch.journal,
            ReplacementSelection(
                event_id=pending.event_id,
                path=pending.path,
                chooser=pending.choice.chooser,
                effect_id=canonical_selection,
            ),
        ),
    )


def resolve_replacement_batch(
    batch: ReplacementEventBatch,
    effects: Iterable[ReplacementEffect],
    *,
    selections: Iterable[ReplacementSelection],
) -> ReplacementEventBatch:
    all_effects = canonical_effects(effects)
    current = batch
    for selection in selections:
        if not isinstance(selection, ReplacementSelection):
            raise ReplacementEffectError(
                "Replacement replay selections must be typed"
            )
        pending = next_batch_replacement_choice(current, all_effects)
        if pending is None:
            raise ReplacementEffectError(
                "Replacement replay contains unused selections"
            )
        if (
            selection.event_id != pending.event_id
            or selection.path != pending.path
            or selection.chooser != pending.choice.chooser
        ):
            raise ReplacementEffectError(
                "Replacement replay selection path or chooser diverged"
            )
        current = apply_batch_replacement(
            current,
            all_effects,
            pending,
            (
                {
                    "effect_id": selection.effect_id,
                    "allocation": thaw_value(selection.allocation),
                }
                if selection.allocation is not None
                else selection.effect_id
            ),
        )
    if next_batch_replacement_choice(current, all_effects) is not None:
        raise ReplacementEffectError(
            "Replacement replay selection sequence ended early"
        )
    return current


def advance_replacement_batch(
    batch: ReplacementEventBatch,
    effects: Iterable[ReplacementEffect],
    *,
    selections: Iterable[str | None | Mapping[str, Any]] = (),
    require_all_selections: bool = True,
) -> ReplacementBatchProgress:
    all_effects = canonical_effects(effects)
    supplied = iter(selections)
    consumed = 0
    current = batch
    while pending := next_batch_replacement_choice(current, all_effects):
        allocation_required = any(
            value.effect_id in pending.choice.options
            and value.allocation_required
            for value in pending.prevention_allocations
        )
        if (
            len(pending.choice.options) == 1
            and not pending.choice.optional_options
            and not allocation_required
        ):
            selected: str | None | Mapping[str, Any] = (
                pending.choice.options[0]
            )
        else:
            try:
                selected = next(supplied)
                consumed += 1
            except StopIteration:
                return ReplacementBatchProgress(
                    batch=current,
                    pending=pending,
                    consumed_selections=consumed,
                )
        current = apply_batch_replacement(
            current, all_effects, pending, selected
        )
    if not require_all_selections:
        return ReplacementBatchProgress(
            batch=current,
            pending=None,
            consumed_selections=consumed,
        )
    try:
        next(supplied)
    except StopIteration:
        return ReplacementBatchProgress(
            batch=current,
            pending=None,
            consumed_selections=consumed,
        )
    raise ReplacementEffectError(
        "Replacement selection sequence contains unused choices"
    )


def replacement_choice_payload(
    pending: ReplacementBatchChoice,
    effects: Iterable[ReplacementEffect],
) -> dict[str, object]:
    by_id = {
        effect.effect_id: effect for effect in canonical_effects(effects)
    }
    options: list[dict[str, object]] = []
    for value in pending.choice.legal_selections:
        declined = value.startswith("decline:")
        effect_id = value.removeprefix("decline:") if declined else value
        effect = by_id[effect_id]
        label = effect.label or effect.effect_id
        options.append(
            {
                "id": value,
                "label": f"Decline {label}" if declined else label,
                "source": effect.source_id,
                "decline": declined,
            }
        )
    legal_values = [str(option["id"]) for option in options]
    allocation_by_effect = {
        choice.effect_id: {
            "shield_id": choice.shield_id,
            "available": choice.available,
            "required": choice.allocation_required,
            "events": [
                {
                    "event_id": event_id,
                    "amount": amount,
                    "unpreventable": unpreventable,
                }
                for event_id, amount, unpreventable in choice.events
            ],
        }
        for choice in pending.prevention_allocations
    }
    allocation_event_ids = sorted(
        {
            event_id
            for choice in pending.prevention_allocations
            for event_id, _amount, _unpreventable in choice.events
        }
    )
    maximum_allocation = max(
        (
            amount
            for choice in pending.prevention_allocations
            for _event_id, amount, _unpreventable in choice.events
        ),
        default=0,
    )
    choice_schema: dict[str, object] = {
        "replacement": {"legal_values": legal_values}
    }
    if allocation_event_ids:
        choice_schema["prevention_allocation"] = {
            "shape": "object_map",
            "legal_refs": allocation_event_ids,
            "legal_values": list(range(maximum_allocation + 1)),
            "required": False,
            "label": "Divide prevention (only when required)",
        }
    return {
        "chooser": pending.choice.chooser,
        "prompt": "Choose the next replacement or prevention effect.",
        "options": options,
        **(
            {"prevention_allocations": allocation_by_effect}
            if allocation_by_effect
            else {}
        ),
        "legal_actions": [
            {
                "id": "choose",
                "action": "choose",
                "label": "Choose replacement",
                "choice_schema": {
                    **choice_schema,
                },
            }
        ],
    }
