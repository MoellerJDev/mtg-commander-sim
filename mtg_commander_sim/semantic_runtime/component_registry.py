from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Generic, Iterable, Mapping, Protocol, Self, TypeVar

from .context import SemanticNodeError


_STABLE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+$")


class RuntimeComponentHandler(Protocol):
    handler_id: str
    schema_version: int
    event: str
    rule_references: tuple[str, ...]
    capability_dependencies: tuple[str, ...]

    def validate(self, descriptor: Mapping[str, Any]) -> Any: ...

    def lower(
        self,
        descriptor: Mapping[str, Any],
        context: Any,
    ) -> tuple[Any, ...]: ...


ContextT = TypeVar("ContextT")
IntentT = TypeVar("IntentT")


class RuntimeComponentRegistry(Generic[ContextT, IntentT]):
    def __init__(
        self, handlers: Iterable[RuntimeComponentHandler] = ()
    ) -> None:
        self._handlers: dict[str, RuntimeComponentHandler] = {}
        self._frozen = False
        for handler in handlers:
            self.register(handler)

    def register(self, handler: RuntimeComponentHandler) -> None:
        if self._frozen:
            raise SemanticNodeError("The runtime handler registry is frozen")
        if _STABLE_ID.fullmatch(handler.handler_id) is None:
            raise SemanticNodeError(
                f"Invalid runtime handler ID {handler.handler_id!r}"
            )
        if handler.handler_id in self._handlers:
            raise SemanticNodeError(
                f"Duplicate runtime handler ID {handler.handler_id!r}"
            )
        self._handlers[handler.handler_id] = handler

    def freeze(self) -> Self:
        self._frozen = True
        return self

    def require_registered_capabilities(self, capabilities: Any) -> None:
        missing = sorted(
            dependency
            for handler in self.inventory()
            for dependency in handler["capability_dependencies"]
            if capabilities.capability(dependency) is None
        )
        if missing:
            raise SemanticNodeError(
                "Runtime handlers reference unknown capabilities: "
                + ", ".join(missing)
            )

    def _handler(
        self, descriptor: Mapping[str, Any]
    ) -> RuntimeComponentHandler:
        handler_id = str(descriptor.get("handler_id") or "")
        handler = self._handlers.get(handler_id)
        if handler is None:
            raise SemanticNodeError(
                f"Unknown runtime handler ID {handler_id!r}"
            )
        return handler

    def validate(self, descriptor: Mapping[str, Any]) -> None:
        self._handler(descriptor).validate(descriptor)

    def lower(
        self,
        descriptor: Mapping[str, Any],
        context: ContextT,
    ) -> tuple[IntentT, ...]:
        return self._handler(descriptor).lower(descriptor, context)

    def inventory(self) -> list[dict[str, Any]]:
        return [
            {
                "handler_id": handler.handler_id,
                "schema_version": handler.schema_version,
                "event": handler.event,
                "rule_references": list(handler.rule_references),
                "capability_dependencies": list(
                    handler.capability_dependencies
                ),
            }
            for handler in (
                self._handlers[handler_id]
                for handler_id in sorted(self._handlers)
            )
        ]

    def describe(self, handler_id: str) -> dict[str, Any] | None:
        return next(
            (
                descriptor
                for descriptor in self.inventory()
                if descriptor["handler_id"] == handler_id
            ),
            None,
        )

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            {"schema_version": 1, "handlers": self.inventory()},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def exact_fields(
    value: Mapping[str, Any],
    expected: set[str],
    *,
    field: str,
) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise SemanticNodeError(
            f"{field} is missing required fields: {', '.join(missing)}"
        )
    if unknown:
        raise SemanticNodeError(
            f"{field} has unknown fields: {', '.join(unknown)}"
        )


def nonempty_strings(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise SemanticNodeError(f"{field} must be a list of nonempty strings")
    result = tuple(str(item) for item in value)
    if len(result) != len(set(result)):
        raise SemanticNodeError(f"{field} must contain unique values")
    return result
