from __future__ import annotations

from collections.abc import Iterator, Mapping
import hashlib
import math
from typing import Any

from ..util import stable_json


class ImmutableValueError(ValueError):
    pass


class FrozenMap(Mapping[str, Any]):
    """Small hashable mapping whose complete value tree is immutable."""

    __slots__ = ("_items", "_lookup", "_hash")

    def __init__(self, values: Mapping[str, Any] | None = None):
        source = values or {}
        if any(not isinstance(key, str) for key in source):
            raise ImmutableValueError("Immutable mappings require string keys")
        items = tuple(
            (key, freeze_value(source[key], field=f"mapping.{key}"))
            for key in sorted(source)
        )
        self._items = items
        self._lookup = dict(items)
        self._hash = hash(items)

    def __getitem__(self, key: str) -> Any:
        return self._lookup[key]

    def __iter__(self) -> Iterator[str]:
        return (key for key, _value in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __hash__(self) -> int:
        return self._hash

    def __repr__(self) -> str:
        return f"FrozenMap({dict(self._items)!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return dict(self.items()) == dict(other.items())
        return False


def freeze_value(value: Any, *, field: str = "value") -> Any:
    """Deep-freeze one canonical JSON-compatible value."""

    if isinstance(value, FrozenMap):
        return value
    if isinstance(value, Mapping):
        return FrozenMap(value)
    if isinstance(value, (list, tuple)):
        return tuple(
            freeze_value(item, field=f"{field}[{index}]")
            for index, item in enumerate(value)
        )
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise ImmutableValueError(
        f"{field} must contain only canonical JSON values"
    )


def thaw_value(value: Any) -> Any:
    """Return a fresh JSON-compatible representation of a frozen value."""

    if isinstance(value, FrozenMap):
        return {key: thaw_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_value(item) for item in value]
    return value


def immutable_fingerprint(value: Any) -> str:
    return hashlib.sha256(
        stable_json(thaw_value(freeze_value(value))).encode("utf-8")
    ).hexdigest()
