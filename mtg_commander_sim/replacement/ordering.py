from __future__ import annotations

from typing import Iterable, Sequence

from .applicability import canonical_effects, replacement_choice
from .application import (
    apply_replacement,
    canonical_replacement_selection,
)
from .model import (
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
    return ReplacementBatchChoice(
        batch_id=batch.batch_id,
        event_index=event_index,
        event_id=event_id,
        tree_choice=pending,
        prior_public_choices=batch.journal,
    )


def apply_batch_replacement(
    batch: ReplacementEventBatch,
    effects: Iterable[ReplacementEffect],
    pending: ReplacementBatchChoice,
    selected_effect_id: str | None,
) -> ReplacementEventBatch:
    all_effects = canonical_effects(effects)
    current = next_batch_replacement_choice(batch, all_effects)
    if current is None or current != pending:
        raise ReplacementEffectError(
            "Replacement batch choice is stale or violates APNAP order"
        )
    canonical_selection = canonical_replacement_selection(
        pending.choice, selected_effect_id
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
            selection.effect_id,
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
    selections: Iterable[str | None] = (),
    require_all_selections: bool = True,
) -> ReplacementBatchProgress:
    all_effects = canonical_effects(effects)
    supplied = iter(selections)
    consumed = 0
    current = batch
    while pending := next_batch_replacement_choice(current, all_effects):
        if (
            len(pending.choice.options) == 1
            and not pending.choice.optional_options
        ):
            selected: str | None = pending.choice.options[0]
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
    return {
        "chooser": pending.choice.chooser,
        "prompt": "Choose the next replacement or prevention effect.",
        "options": options,
        "legal_actions": [
            {
                "id": "choose",
                "action": "choose",
                "label": "Choose replacement",
                "choice_schema": {
                    "replacement": {"legal_values": legal_values}
                },
            }
        ],
    }
