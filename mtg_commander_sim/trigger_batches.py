from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from .replacement.immutable import FrozenMap, thaw_value


class TriggerBatchError(ValueError):
    """A pending triggered-ability batch is malformed or stale."""


_STACK_ITEM_FIELDS = frozenset(
    {
        "stack_id",
        "ref",
        "kind",
        "controller",
        "label",
        "card_object_id",
        "source_object_id",
        "semantic_key",
        "targets",
        "modes",
        "x_value",
        "chosen_face",
        "notes",
        "default_destination",
        "visibility",
        "context",
        "referred_object_ids",
    }
)
_REQUIRED_STACK_ITEM_FIELDS = frozenset(
    {"stack_id", "ref", "kind", "controller", "label"}
)


def _exact_mapping(value: Any, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TriggerBatchError(f"{field} must be a mapping")
    if any(type(key) is not str for key in value):
        raise TriggerBatchError(f"{field} keys must be strings")
    return value


def _exact_string(value: Any, *, field: str) -> str:
    if type(value) is not str or not value:
        raise TriggerBatchError(f"{field} must be a nonempty string")
    return value


def _exact_integer(value: Any, *, field: str) -> int:
    if type(value) is not int or value < 0:
        raise TriggerBatchError(f"{field} must be a nonnegative integer")
    return value


def _string_tuple(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TriggerBatchError(f"{field} must be an array")
    result = tuple(
        _exact_string(item, field=f"{field}[{index}]")
        for index, item in enumerate(value)
    )
    if len(set(result)) != len(result):
        raise TriggerBatchError(f"{field} must not contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class PendingTriggerItem(Mapping[str, Any]):
    """One immutable ordinary stack object waiting for CR 603.3 placement."""

    payload: FrozenMap

    def __post_init__(self) -> None:
        if not isinstance(self.payload, FrozenMap):
            object.__setattr__(self, "payload", FrozenMap(self.payload))
        data = self.payload
        unknown = set(data) - _STACK_ITEM_FIELDS
        missing = _REQUIRED_STACK_ITEM_FIELDS - set(data)
        if unknown:
            raise TriggerBatchError(
                "Pending trigger item has unknown fields: "
                + ", ".join(sorted(unknown))
            )
        if missing:
            raise TriggerBatchError(
                "Pending trigger item is missing fields: "
                + ", ".join(sorted(missing))
            )
        for field in _REQUIRED_STACK_ITEM_FIELDS:
            _exact_string(data[field], field=f"trigger_item.{field}")
        if "triggered" not in data["kind"].casefold():
            raise TriggerBatchError(
                "Pending trigger items must be triggered abilities"
            )
        for field in (
            "card_object_id",
            "source_object_id",
            "semantic_key",
            "chosen_face",
            "default_destination",
        ):
            value = data.get(field)
            if value is not None:
                _exact_string(value, field=f"trigger_item.{field}")
        if "notes" in data and type(data["notes"]) is not str:
            raise TriggerBatchError("trigger_item.notes must be a string")
        x_value = data.get("x_value")
        if x_value is not None and type(x_value) is not int:
            raise TriggerBatchError("trigger_item.x_value must be an integer")
        for field in ("targets", "modes", "visibility", "referred_object_ids"):
            value = data.get(field, ())
            if not isinstance(value, tuple):
                raise TriggerBatchError(f"trigger_item.{field} must be an array")
        context = data.get("context", FrozenMap())
        if not isinstance(context, FrozenMap):
            raise TriggerBatchError("trigger_item.context must be a mapping")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PendingTriggerItem":
        return cls(FrozenMap(_exact_mapping(data, field="trigger_item")))

    @property
    def ref(self) -> str:
        return self.payload["ref"]

    @property
    def label(self) -> str:
        return self.payload["label"]

    @property
    def controller(self) -> str:
        return self.payload["controller"]

    def to_dict(self) -> dict[str, Any]:
        return thaw_value(self.payload)

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.payload)

    def __len__(self) -> int:
        return len(self.payload)


@dataclass(frozen=True, slots=True)
class TriggerControllerGroup(Mapping[str, Any]):
    controller: str
    items: tuple[PendingTriggerItem, ...]

    def __post_init__(self) -> None:
        _exact_string(self.controller, field="trigger_group.controller")
        if not isinstance(self.items, tuple) or not self.items:
            raise TriggerBatchError("trigger_group.items must be a nonempty array")
        if any(not isinstance(item, PendingTriggerItem) for item in self.items):
            raise TriggerBatchError(
                "trigger_group.items must contain pending trigger items"
            )
        if any(item.controller != self.controller for item in self.items):
            raise TriggerBatchError(
                "Every trigger item must match its group controller"
            )
        refs = [item.ref for item in self.items]
        if len(set(refs)) != len(refs):
            raise TriggerBatchError("A trigger group must not repeat an item")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TriggerControllerGroup":
        value = _exact_mapping(data, field="trigger_group")
        unknown = set(value) - {"controller", "items"}
        missing = {"controller", "items"} - set(value)
        if unknown or missing:
            raise TriggerBatchError(
                "Trigger group fields must be exactly controller and items"
            )
        raw_items = value["items"]
        if not isinstance(raw_items, (list, tuple)):
            raise TriggerBatchError("trigger_group.items must be an array")
        return cls(
            controller=_exact_string(
                value["controller"], field="trigger_group.controller"
            ),
            items=tuple(
                PendingTriggerItem.from_dict(item)
                for item in raw_items
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "controller": self.controller,
            "items": [item.to_dict() for item in self.items],
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(("controller", "items"))

    def __len__(self) -> int:
        return 2


@dataclass(frozen=True, slots=True)
class PendingTriggerBatch(Mapping[str, Any]):
    """Versioned CR 603.3 APNAP batch persisted in Game Record v3 state."""

    batch_id: str
    ref: str
    apnap_order: tuple[str, ...]
    groups: tuple[TriggerControllerGroup, ...]
    turn_sequence: int
    priority_epoch: int
    placement_started: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        _exact_string(self.batch_id, field="trigger_batch.batch_id")
        _exact_string(self.ref, field="trigger_batch.ref")
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise TriggerBatchError("Unsupported trigger-batch schema version")
        _exact_integer(self.turn_sequence, field="trigger_batch.turn_sequence")
        _exact_integer(self.priority_epoch, field="trigger_batch.priority_epoch")
        if type(self.placement_started) is not bool:
            raise TriggerBatchError(
                "trigger_batch.placement_started must be a boolean"
            )
        if not isinstance(self.apnap_order, tuple) or not self.apnap_order:
            raise TriggerBatchError("trigger_batch.apnap_order must be nonempty")
        if any(type(seat) is not str or not seat for seat in self.apnap_order):
            raise TriggerBatchError(
                "trigger_batch.apnap_order must contain nonempty strings"
            )
        if len(set(self.apnap_order)) != len(self.apnap_order):
            raise TriggerBatchError(
                "trigger_batch.apnap_order must not contain duplicates"
            )
        if not isinstance(self.groups, tuple) or not self.groups:
            raise TriggerBatchError("trigger_batch.groups must be nonempty")
        if any(not isinstance(group, TriggerControllerGroup) for group in self.groups):
            raise TriggerBatchError(
                "trigger_batch.groups must contain controller groups"
            )
        group_controllers = tuple(group.controller for group in self.groups)
        if len(set(group_controllers)) != len(group_controllers):
            raise TriggerBatchError(
                "A trigger batch must contain at most one group per controller"
            )
        if any(controller not in self.apnap_order for controller in group_controllers):
            raise TriggerBatchError(
                "Every trigger controller must appear in APNAP order"
            )
        expected = tuple(
            seat for seat in self.apnap_order if seat in group_controllers
        )
        if group_controllers != expected:
            raise TriggerBatchError("Trigger groups must be in APNAP order")
        refs = [item.ref for group in self.groups for item in group.items]
        if len(set(refs)) != len(refs):
            raise TriggerBatchError("A trigger batch must not repeat an item")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PendingTriggerBatch":
        value = _exact_mapping(data, field="trigger_batch")
        legacy_fields = {
            "batch_id",
            "ref",
            "apnap_order",
            "groups",
            "turn_sequence",
            "priority_epoch",
            "placement_started",
        }
        allowed = legacy_fields | {"schema_version"}
        unknown = set(value) - allowed
        missing = legacy_fields - set(value)
        if unknown:
            raise TriggerBatchError(
                "Trigger batch has unknown fields: "
                + ", ".join(sorted(unknown))
            )
        if missing:
            raise TriggerBatchError(
                "Trigger batch is missing fields: "
                + ", ".join(sorted(missing))
            )
        raw_groups = value["groups"]
        if not isinstance(raw_groups, (list, tuple)):
            raise TriggerBatchError("trigger_batch.groups must be an array")
        return cls(
            batch_id=_exact_string(
                value["batch_id"], field="trigger_batch.batch_id"
            ),
            ref=_exact_string(value["ref"], field="trigger_batch.ref"),
            apnap_order=_string_tuple(
                value["apnap_order"], field="trigger_batch.apnap_order"
            ),
            groups=tuple(
                TriggerControllerGroup.from_dict(group)
                for group in raw_groups
            ),
            turn_sequence=_exact_integer(
                value["turn_sequence"], field="trigger_batch.turn_sequence"
            ),
            priority_epoch=_exact_integer(
                value["priority_epoch"], field="trigger_batch.priority_epoch"
            ),
            placement_started=value["placement_started"],
            schema_version=value.get("schema_version", 1),
        )

    @property
    def items(self) -> tuple[PendingTriggerItem, ...]:
        return tuple(item for group in self.groups for item in group.items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "batch_id": self.batch_id,
            "ref": self.ref,
            "apnap_order": list(self.apnap_order),
            "groups": [group.to_dict() for group in self.groups],
            "turn_sequence": self.turn_sequence,
            "priority_epoch": self.priority_epoch,
            "placement_started": self.placement_started,
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())

    def __len__(self) -> int:
        return 8


def group_pending_trigger_items(
    items: Sequence[PendingTriggerItem | Mapping[str, Any]],
    *,
    apnap_order: Sequence[str],
    drop_inactive_controllers: bool = False,
) -> tuple[TriggerControllerGroup, ...]:
    order = _string_tuple(apnap_order, field="apnap_order")
    normalized = tuple(
        item
        if isinstance(item, PendingTriggerItem)
        else PendingTriggerItem.from_dict(item)
        for item in items
    )
    refs = [item.ref for item in normalized]
    if len(set(refs)) != len(refs):
        raise TriggerBatchError("A pending trigger collection must be unique")
    inactive = {
        item.controller
        for item in normalized
        if item.controller not in order
    }
    if inactive and not drop_inactive_controllers:
        raise TriggerBatchError(
            "Trigger controllers are absent from APNAP order: "
            + ", ".join(sorted(inactive))
        )
    return tuple(
        TriggerControllerGroup(
            controller=controller,
            items=tuple(
                item for item in normalized if item.controller == controller
            ),
        )
        for controller in order
        if any(item.controller == controller for item in normalized)
    )


def create_pending_trigger_batch(
    *,
    batch_id: str,
    ref: str,
    items: Sequence[PendingTriggerItem | Mapping[str, Any]],
    apnap_order: Sequence[str],
    turn_sequence: int,
    priority_epoch: int,
) -> PendingTriggerBatch:
    groups = group_pending_trigger_items(items, apnap_order=apnap_order)
    if not groups:
        raise TriggerBatchError("A trigger batch must contain an active controller")
    return PendingTriggerBatch(
        batch_id=batch_id,
        ref=ref,
        apnap_order=tuple(apnap_order),
        groups=groups,
        turn_sequence=turn_sequence,
        priority_epoch=priority_epoch,
    )


def merge_pending_trigger_batch(
    batch: PendingTriggerBatch,
    items: Sequence[PendingTriggerItem | Mapping[str, Any]],
    *,
    apnap_order: Sequence[str],
    priority_epoch: int,
) -> PendingTriggerBatch | None:
    if batch.placement_started or batch.priority_epoch != priority_epoch:
        return None
    combined = (*batch.items, *items)
    groups = group_pending_trigger_items(
        combined,
        apnap_order=apnap_order,
        drop_inactive_controllers=True,
    )
    if not groups:
        return None
    return replace(
        batch,
        apnap_order=tuple(apnap_order),
        groups=groups,
    )


def begin_pending_trigger_placement(
    batch: PendingTriggerBatch,
    *,
    apnap_order: Sequence[str],
) -> PendingTriggerBatch | None:
    if batch.placement_started:
        return batch
    groups = group_pending_trigger_items(
        batch.items,
        apnap_order=apnap_order,
        drop_inactive_controllers=True,
    )
    if not groups:
        return None
    return replace(
        batch,
        apnap_order=tuple(apnap_order),
        groups=groups,
        placement_started=True,
    )


def complete_pending_trigger_group(
    batch: PendingTriggerBatch,
    *,
    controller: str,
    refs: Sequence[str],
) -> tuple[tuple[PendingTriggerItem, ...], PendingTriggerBatch | None]:
    if not batch.placement_started or not batch.groups:
        raise TriggerBatchError("Trigger batch placement has not started")
    group = batch.groups[0]
    if group.controller != controller:
        raise TriggerBatchError(
            "Only the first APNAP controller may place this trigger group"
        )
    ordered_refs = _string_tuple(refs, field="trigger_order")
    by_ref = {item.ref: item for item in group.items}
    if sorted(ordered_refs) != sorted(by_ref):
        raise TriggerBatchError(
            "Trigger order must contain every listed trigger exactly once"
        )
    ordered = tuple(by_ref[ref] for ref in ordered_refs)
    remaining = batch.groups[1:]
    return ordered, (
        replace(batch, groups=remaining) if remaining else None
    )


__all__ = [
    "PendingTriggerBatch",
    "PendingTriggerItem",
    "TriggerBatchError",
    "TriggerControllerGroup",
    "begin_pending_trigger_placement",
    "complete_pending_trigger_group",
    "create_pending_trigger_batch",
    "group_pending_trigger_items",
    "merge_pending_trigger_batch",
]
