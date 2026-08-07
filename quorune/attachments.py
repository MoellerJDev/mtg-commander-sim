from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, MutableMapping

from .continuous_effect_model import ContinuousObjectIdentity
from .model import CardInstance


class AttachmentRelationError(ValueError):
    """An authoritative attachment relation is malformed or cannot commit."""


@dataclass(frozen=True, slots=True)
class AttachmentTransition:
    source_id: str
    previous_target_id: str | None
    target_id: str | None
    changed: bool
    source_timestamp: int


@dataclass(frozen=True, slots=True)
class PendingAttachment:
    target_ref: str
    target_zone: str


def take_pending_attachment(source: CardInstance) -> PendingAttachment | None:
    """Consume one represented deferred attachment instruction."""

    target_ref = source.annotations.pop("pending_aura_target", None)
    if not target_ref:
        return None
    return PendingAttachment(
        target_ref=str(target_ref),
        target_zone=str(
            source.annotations.pop("pending_aura_zone", "graveyard")
        ),
    )


def attached_object_identity(
    cards: Mapping[str, CardInstance],
    source: CardInstance,
) -> ContinuousObjectIdentity | None:
    """Return the exact live object affected by an attached-source effect.

    Both halves of the relation are checked.  Stale copied annotations or a
    one-sided object ID therefore cannot grant characteristics.
    """

    target_id = source.attached_to
    if (
        source.zone != "battlefield"
        or source.phased_out
        or not target_id
    ):
        return None
    target = cards.get(target_id)
    if (
        target is None
        or target.zone != "battlefield"
        or target.phased_out
        or source.object_id not in target.attachments
    ):
        return None
    return ContinuousObjectIdentity(
        object_id=target.object_id,
        logical_object_id=target.logical_object_id,
    )


def attach_objects(
    cards: MutableMapping[str, CardInstance],
    source: CardInstance,
    target: CardInstance,
    *,
    source_timestamp: int,
) -> AttachmentTransition:
    """Commit one CR 701.3 relation and its source timestamp atomically.

    The caller owns game-specific legality.  This function owns reciprocal
    identity integrity and CR 701.3c's new timestamp when the source becomes
    attached to a different object.
    """

    if source.object_id == target.object_id:
        raise AttachmentRelationError("An object cannot attach to itself")
    if cards.get(source.object_id) is not source:
        raise AttachmentRelationError("Attachment source is not authoritative")
    if cards.get(target.object_id) is not target:
        raise AttachmentRelationError("Attachment target is not authoritative")
    if type(source_timestamp) is not int or source_timestamp < 0:
        raise AttachmentRelationError(
            "Attachment timestamps must be nonnegative integers"
        )

    previous_id = source.attached_to
    previous = cards.get(previous_id or "")
    if previous_id is not None and previous is None:
        raise AttachmentRelationError(
            "Attachment source names a missing previous target"
        )
    if previous is not None and source.object_id not in previous.attachments:
        raise AttachmentRelationError(
            "Attachment source and previous target are not reciprocal"
        )
    target_mentions_source = source.object_id in target.attachments
    if previous_id == target.object_id:
        if not target_mentions_source:
            raise AttachmentRelationError(
                "Attachment source and target are not reciprocal"
            )
        return AttachmentTransition(
            source_id=source.object_id,
            previous_target_id=previous_id,
            target_id=target.object_id,
            changed=False,
            source_timestamp=source.zone_timestamp,
        )
    if target_mentions_source:
        raise AttachmentRelationError(
            "Attachment target already names an unrelated source relation"
        )

    if previous is not None:
        previous.attachments.remove(source.object_id)
    source.attached_to = target.object_id
    target.attachments.append(source.object_id)
    source.zone_timestamp = source_timestamp
    return AttachmentTransition(
        source_id=source.object_id,
        previous_target_id=previous_id,
        target_id=target.object_id,
        changed=True,
        source_timestamp=source_timestamp,
    )


def detach_object(
    cards: MutableMapping[str, CardInstance],
    source: CardInstance,
) -> AttachmentTransition:
    """Remove one reciprocal attachment relation without changing timestamp."""

    if cards.get(source.object_id) is not source:
        raise AttachmentRelationError("Attachment source is not authoritative")
    previous_id = source.attached_to
    if previous_id is None:
        return AttachmentTransition(
            source_id=source.object_id,
            previous_target_id=None,
            target_id=None,
            changed=False,
            source_timestamp=source.zone_timestamp,
        )
    previous = cards.get(previous_id)
    if previous is None or source.object_id not in previous.attachments:
        raise AttachmentRelationError(
            "Attachment source and target are not reciprocal"
        )
    previous.attachments.remove(source.object_id)
    source.attached_to = None
    return AttachmentTransition(
        source_id=source.object_id,
        previous_target_id=previous_id,
        target_id=None,
        changed=True,
        source_timestamp=source.zone_timestamp,
    )


def clear_object_attachment_relations(
    cards: MutableMapping[str, CardInstance],
    card: CardInstance,
) -> tuple[AttachmentTransition, ...]:
    """Detach an object and everything attached to it before a zone change."""

    transitions: list[AttachmentTransition] = []
    if card.attached_to is not None:
        transitions.append(detach_object(cards, card))
    for source_id in tuple(card.attachments):
        source = cards.get(source_id)
        if source is None or source.attached_to != card.object_id:
            raise AttachmentRelationError(
                "Attached object and target are not reciprocal"
            )
        transitions.append(detach_object(cards, source))
    return tuple(transitions)


__all__ = [
    "AttachmentRelationError",
    "AttachmentTransition",
    "PendingAttachment",
    "attach_objects",
    "attached_object_identity",
    "clear_object_attachment_relations",
    "detach_object",
    "take_pending_attachment",
]
