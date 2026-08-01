from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from .context import ReadOnlyHandlerContext
from .handlers import SemanticNodeHandler
from .intents import IntentPlan


_STABLE_ID = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)+$")
_OPERATION = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


class SemanticHandlerRegistryError(ValueError):
    """The typed semantic handler registry is malformed."""


class SemanticHandlerRegistry:
    def __init__(self, handlers: Iterable[SemanticNodeHandler] = ()):
        self._by_operation: dict[str, SemanticNodeHandler] = {}
        self._handler_ids: set[str] = set()
        self._frozen = False
        for handler in handlers:
            self.register(handler)

    def register(self, handler: SemanticNodeHandler) -> None:
        if self._frozen:
            raise SemanticHandlerRegistryError(
                "The semantic handler registry is frozen"
            )
        operation = str(handler.operation)
        handler_id = str(handler.handler_id)
        if _OPERATION.fullmatch(operation) is None:
            raise SemanticHandlerRegistryError(
                f"Invalid semantic operation {operation!r}"
            )
        if _STABLE_ID.fullmatch(handler_id) is None:
            raise SemanticHandlerRegistryError(
                f"Invalid semantic handler id {handler_id!r}"
            )
        if type(handler.schema_version) is not int or handler.schema_version < 1:
            raise SemanticHandlerRegistryError(
                f"Handler {handler_id} has an invalid schema version"
            )
        dependencies = tuple(handler.capability_dependencies)
        if len(dependencies) != len(set(dependencies)) or any(
            _STABLE_ID.fullmatch(value) is None for value in dependencies
        ):
            raise SemanticHandlerRegistryError(
                f"Handler {handler_id} has invalid capability dependencies"
            )
        if operation in self._by_operation:
            raise SemanticHandlerRegistryError(
                f"Duplicate semantic operation {operation!r}"
            )
        if handler_id in self._handler_ids:
            raise SemanticHandlerRegistryError(
                f"Duplicate semantic handler id {handler_id!r}"
            )
        self._by_operation[operation] = handler
        self._handler_ids.add(handler_id)

    def freeze(self) -> "SemanticHandlerRegistry":
        self._frozen = True
        return self

    def lower(
        self,
        effect: Mapping[str, Any],
        context: ReadOnlyHandlerContext,
    ) -> IntentPlan | None:
        operation = str(effect.get("op") or "").casefold()
        handler = self._by_operation.get(operation)
        if handler is None:
            return None
        return handler.lower(effect, context)

    def describe(self, operation: str) -> dict[str, Any] | None:
        handler = self._by_operation.get(str(operation).casefold())
        if handler is None:
            return None
        return {
            "operation": handler.operation,
            "handler_id": handler.handler_id,
            "schema_version": handler.schema_version,
            "capability_dependencies": list(
                handler.capability_dependencies
            ),
        }

    def inventory(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for operation in sorted(self._by_operation):
            descriptor = self.describe(operation)
            if descriptor is None:  # Defensive against internal index drift.
                raise SemanticHandlerRegistryError(
                    f"Handler index lost operation {operation!r}"
                )
            result.append(descriptor)
        return result

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            {"schema_version": 1, "handlers": self.inventory()},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
