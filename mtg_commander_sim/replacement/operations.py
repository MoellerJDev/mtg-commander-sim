from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, TypeAlias

from .immutable import FrozenMap, freeze_value, thaw_value


OPERATION_SCHEMA_VERSION = 1


class ReplacementOperationError(ValueError):
    pass


def _exact_fields(
    value: Mapping[str, Any], expected: set[str], *, operation: str
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unknown:
            details.append("unknown " + ", ".join(unknown))
        raise ReplacementOperationError(
            f"Replacement {operation} fields: {'; '.join(details)}"
        )


def _field(value: Any, *, operation: str) -> str:
    result = str(value or "")
    if not result:
        raise ReplacementOperationError(
            f"Replacement {operation} requires a field"
        )
    return result


def _integer(value: Any, *, field: str, minimum: int | None = None) -> int:
    if type(value) is not int or (minimum is not None and value < minimum):
        qualifier = f" at least {minimum}" if minimum is not None else ""
        raise ReplacementOperationError(
            f"Replacement {field} must be an integer{qualifier}"
        )
    return value


@dataclass(frozen=True, slots=True)
class SetField:
    field: str
    value: Any
    schema_version: int = OPERATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "field", _field(self.field, operation="set"))
        object.__setattr__(self, "value", freeze_value(self.value))

    def to_dict(self) -> dict[str, Any]:
        return {"op": "set", "field": self.field, "value": thaw_value(self.value)}


@dataclass(frozen=True, slots=True)
class AddAmount:
    field: str
    amount: int
    schema_version: int = OPERATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "field", _field(self.field, operation="add"))
        _integer(self.amount, field="add amount")

    def to_dict(self) -> dict[str, Any]:
        return {"op": "add", "field": self.field, "amount": self.amount}


@dataclass(frozen=True, slots=True)
class MultiplyAmount:
    field: str
    factor: int
    schema_version: int = OPERATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "field", _field(self.field, operation="multiply")
        )
        _integer(self.factor, field="multiply factor", minimum=0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "op": "multiply",
            "field": self.field,
            "factor": self.factor,
        }


@dataclass(frozen=True, slots=True)
class PreventAmount:
    amount: int | None = None
    schema_version: int = OPERATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.amount is not None:
            _integer(self.amount, field="prevent amount", minimum=0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "op": "prevent",
            **({"amount": self.amount} if self.amount is not None else {}),
        }


@dataclass(frozen=True, slots=True)
class AppendValues:
    field: str
    values: tuple[Any, ...]
    schema_version: int = OPERATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "field", _field(self.field, operation="append")
        )
        if not isinstance(self.values, (list, tuple)):
            raise ReplacementOperationError(
                "Replacement append values must be an array"
            )
        object.__setattr__(
            self,
            "values",
            tuple(freeze_value(value) for value in self.values),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "op": "append",
            "field": self.field,
            "values": [thaw_value(value) for value in self.values],
        }


@dataclass(frozen=True, slots=True)
class UnionValues:
    field: str
    values: tuple[Any, ...]
    schema_version: int = OPERATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "field", _field(self.field, operation="union")
        )
        if not isinstance(self.values, (list, tuple)):
            raise ReplacementOperationError(
                "Replacement union values must be an array"
            )
        object.__setattr__(
            self,
            "values",
            tuple(freeze_value(value) for value in self.values),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "op": "union",
            "field": self.field,
            "values": [thaw_value(value) for value in self.values],
        }


@dataclass(frozen=True, slots=True)
class CreateNestedEvent:
    event: FrozenMap
    schema_version: int = OPERATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.event, Mapping):
            raise ReplacementOperationError(
                "Nested replacement operation requires an event object"
            )
        object.__setattr__(self, "event", FrozenMap(self.event))

    def to_dict(self) -> dict[str, Any]:
        return {"op": "nested_event", "event": thaw_value(self.event)}


@dataclass(frozen=True, slots=True)
class ReserveZoneChange:
    objects: tuple[str, ...] = ()
    from_field: str | None = None
    schema_version: int = OPERATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        values = tuple(str(value) for value in self.objects)
        if any(not value for value in values):
            raise ReplacementOperationError(
                "Zone-change reservation requires stable object IDs"
            )
        field = str(self.from_field or "") or None
        if bool(values) == bool(field):
            raise ReplacementOperationError(
                "Zone-change reservation requires exactly one object source"
            )
        object.__setattr__(self, "objects", values)
        object.__setattr__(self, "from_field", field)

    def to_dict(self) -> dict[str, Any]:
        return {
            "op": "reserve_zone_change",
            **(
                {"objects": list(self.objects)}
                if self.objects
                else {"from_field": self.from_field}
            ),
        }


@dataclass(frozen=True, slots=True)
class CapResultLifeLoss:
    minimum: int
    schema_version: int = OPERATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _integer(self.minimum, field="result life floor minimum")

    def to_dict(self) -> dict[str, Any]:
        return {"op": "cap_result_life_loss", "minimum": self.minimum}


ReplacementOperation: TypeAlias = (
    SetField
    | AddAmount
    | MultiplyAmount
    | PreventAmount
    | AppendValues
    | UnionValues
    | CreateNestedEvent
    | ReserveZoneChange
    | CapResultLifeLoss
)


_TYPED_OPERATION_TYPES = (
    SetField,
    AddAmount,
    MultiplyAmount,
    PreventAmount,
    AppendValues,
    UnionValues,
    CreateNestedEvent,
    ReserveZoneChange,
    CapResultLifeLoss,
)


def operation_from_dict(value: Mapping[str, Any]) -> ReplacementOperation:
    if not isinstance(value, Mapping):
        raise ReplacementOperationError(
            "Replacement operations must be objects"
        )
    op = str(value.get("op") or "")
    if op == "set":
        _exact_fields(value, {"op", "field", "value"}, operation=op)
        return SetField(_field(value["field"], operation=op), value["value"])
    if op == "add":
        _exact_fields(value, {"op", "field", "amount"}, operation=op)
        return AddAmount(
            _field(value["field"], operation=op),
            _integer(value["amount"], field="add amount"),
        )
    if op == "multiply":
        _exact_fields(value, {"op", "field", "factor"}, operation=op)
        return MultiplyAmount(
            _field(value["field"], operation=op),
            _integer(value["factor"], field="multiply factor", minimum=0),
        )
    if op == "prevent":
        expected = {"op", "amount"} if "amount" in value else {"op"}
        _exact_fields(value, expected, operation=op)
        return PreventAmount(
            _integer(value["amount"], field="prevent amount", minimum=0)
            if "amount" in value
            else None
        )
    if op in {"append", "union"}:
        _exact_fields(value, {"op", "field", "values"}, operation=op)
        values = value["values"]
        if not isinstance(values, (list, tuple)):
            raise ReplacementOperationError(
                f"Replacement {op} values must be an array"
            )
        operation_type = AppendValues if op == "append" else UnionValues
        return operation_type(
            _field(value["field"], operation=op), tuple(values)
        )
    if op == "nested_event":
        _exact_fields(value, {"op", "event"}, operation=op)
        event = value["event"]
        if not isinstance(event, Mapping):
            raise ReplacementOperationError(
                "Nested replacement operation requires an event object"
            )
        return CreateNestedEvent(FrozenMap(event))
    if op == "reserve_zone_change":
        if "objects" in value:
            _exact_fields(value, {"op", "objects"}, operation=op)
            objects = value["objects"]
            if not isinstance(objects, (list, tuple)):
                raise ReplacementOperationError(
                    "Zone-change reservation objects must be an array"
                )
            return ReserveZoneChange(objects=tuple(str(item) for item in objects))
        _exact_fields(value, {"op", "from_field"}, operation=op)
        return ReserveZoneChange(from_field=_field(value["from_field"], operation=op))
    if op == "cap_result_life_loss":
        _exact_fields(value, {"op", "minimum"}, operation=op)
        return CapResultLifeLoss(
            _integer(value["minimum"], field="result life floor minimum")
        )
    raise ReplacementOperationError(
        f"Unsupported replacement operation {op!r}"
    )


def lower_operation(value: Any) -> ReplacementOperation:
    if isinstance(value, _TYPED_OPERATION_TYPES):
        return value
    if not isinstance(value, Mapping):
        raise ReplacementOperationError(
            "Replacement operations must lower from objects"
        )
    return operation_from_dict(value)


def operation_to_dict(value: ReplacementOperation) -> dict[str, Any]:
    if not isinstance(value, _TYPED_OPERATION_TYPES):
        raise ReplacementOperationError("Unknown typed replacement operation")
    return value.to_dict()
