from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping, Protocol

from ..rules.capabilities import load_default_capability_registry
from .component_registry import (
    RuntimeComponentRegistry,
    exact_fields,
    nonempty_strings,
)
from .context import SemanticNodeError


_ADDITIONAL_TOKEN_HANDLER_ID = "replacement.token.additional.v1"


@dataclass(frozen=True, slots=True)
class TokenDefinition:
    name: str
    type_line: str
    colors: tuple[str, ...] = ()
    power: str | None = None
    toughness: str | None = None
    keywords: tuple[str, ...] = ()
    oracle_text: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TokenDefinition":
        allowed = {
            "name",
            "type_line",
            "colors",
            "power",
            "toughness",
            "keywords",
            "oracle_text",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise SemanticNodeError(
                "additional token has unknown fields: " + ", ".join(unknown)
            )
        name = str(value.get("name") or "").strip()
        type_line = str(value.get("type_line") or "").strip()
        if not name or not type_line:
            raise SemanticNodeError(
                "additional token requires nonempty name and type_line"
            )
        colors = nonempty_strings(
            value.get("colors", []), field="token.colors"
        )
        keywords = nonempty_strings(
            value.get("keywords", []), field="token.keywords"
        )
        power = value.get("power")
        toughness = value.get("toughness")
        if (power is None) != (toughness is None):
            raise SemanticNodeError(
                "additional token power and toughness must appear together"
            )
        return cls(
            name=name,
            type_line=type_line,
            colors=colors,
            power=None if power is None else str(power),
            toughness=None if toughness is None else str(toughness),
            keywords=keywords,
            oracle_text=str(value.get("oracle_text") or ""),
        )

    def characteristics(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "type_line": self.type_line,
            "colors": list(self.colors),
            "keywords": list(self.keywords),
        }
        if self.power is not None:
            value["power"] = self.power
            value["toughness"] = self.toughness
        if self.oracle_text:
            value["oracle_text"] = self.oracle_text
        return value


@dataclass(frozen=True, slots=True)
class AdditionalTokenReplacementNode:
    created_types_all: tuple[str, ...]
    event_controller: str
    quantity: int
    token: TokenDefinition


@dataclass(frozen=True, slots=True)
class TokenCreationReplacementContext:
    source_ref: str
    source_controller: str
    event_controller: str
    created_types: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.source_ref:
            raise SemanticNodeError("A token replacement source ref is required")
        if not self.source_controller or not self.event_controller:
            raise SemanticNodeError(
                "Token replacement controllers must be nonempty"
            )
        if len(self.created_types) != len(set(self.created_types)):
            raise SemanticNodeError("Created token types must be unique")


@dataclass(frozen=True, slots=True)
class AdditionalTokenIntent:
    handler_id: str
    source_ref: str
    quantity: int
    token: TokenDefinition


class TokenCreationReplacementHandler(Protocol):
    handler_id: str
    schema_version: int
    event: str
    rule_references: tuple[str, ...]
    capability_dependencies: tuple[str, ...]

    def validate(
        self, descriptor: Mapping[str, Any]
    ) -> AdditionalTokenReplacementNode: ...

    def lower(
        self,
        descriptor: Mapping[str, Any],
        context: TokenCreationReplacementContext,
    ) -> tuple[AdditionalTokenIntent, ...]: ...


@dataclass(frozen=True, slots=True)
class AdditionalTokenReplacementHandler:
    handler_id: str = _ADDITIONAL_TOKEN_HANDLER_ID
    schema_version: int = 1
    event: str = "token.create"
    rule_references: tuple[str, ...] = (
        "111.2",
        "614.1",
        "614.1a",
        "614.4",
        "614.5",
        "614.6",
        "614.16",
    )
    capability_dependencies: tuple[str, ...] = (
        "token.creation.additional_replacement",
    )

    def validate(
        self, descriptor: Mapping[str, Any]
    ) -> AdditionalTokenReplacementNode:
        exact_fields(
            descriptor,
            {
                "handler_id",
                "schema_version",
                "event",
                "condition",
                "quantity",
                "token",
            },
            field="runtime handler",
        )
        if descriptor["handler_id"] != self.handler_id:
            raise SemanticNodeError("Runtime handler ID does not match registry")
        if descriptor["schema_version"] != self.schema_version:
            raise SemanticNodeError(
                f"Unsupported {self.handler_id} schema version"
            )
        if descriptor["event"] != self.event:
            raise SemanticNodeError(
                f"{self.handler_id} must handle {self.event}"
            )
        condition = descriptor["condition"]
        if not isinstance(condition, Mapping):
            raise SemanticNodeError("runtime handler condition must be an object")
        exact_fields(
            condition,
            {"event_controller", "created_types_all"},
            field="runtime handler condition",
        )
        event_controller = str(condition["event_controller"])
        if event_controller != "source_controller":
            raise SemanticNodeError(
                "additional token replacement currently requires "
                "event_controller=source_controller"
            )
        created_types = tuple(
            value.casefold()
            for value in nonempty_strings(
                condition["created_types_all"],
                field="condition.created_types_all",
            )
        )
        if not created_types:
            raise SemanticNodeError(
                "additional token replacement requires a created token type"
            )
        quantity = descriptor["quantity"]
        if type(quantity) is not int or quantity < 1:
            raise SemanticNodeError(
                "additional token replacement quantity must be positive"
            )
        token = descriptor["token"]
        if not isinstance(token, Mapping):
            raise SemanticNodeError("runtime handler token must be an object")
        return AdditionalTokenReplacementNode(
            created_types_all=created_types,
            event_controller=event_controller,
            quantity=quantity,
            token=TokenDefinition.from_mapping(token),
        )

    def lower(
        self,
        descriptor: Mapping[str, Any],
        context: TokenCreationReplacementContext,
    ) -> tuple[AdditionalTokenIntent, ...]:
        node = self.validate(descriptor)
        if context.event_controller != context.source_controller:
            return ()
        event_types = {value.casefold() for value in context.created_types}
        if not set(node.created_types_all).issubset(event_types):
            return ()
        return (
            AdditionalTokenIntent(
                handler_id=self.handler_id,
                source_ref=context.source_ref,
                quantity=node.quantity,
                token=node.token,
            ),
        )


class TokenCreationReplacementRegistry(
    RuntimeComponentRegistry[
        TokenCreationReplacementContext,
        AdditionalTokenIntent,
    ]
):
    pass


@lru_cache(maxsize=1)
def default_token_creation_replacement_registry(
) -> TokenCreationReplacementRegistry:
    registry = TokenCreationReplacementRegistry(
        (AdditionalTokenReplacementHandler(),)
    )
    registry.require_registered_capabilities(
        load_default_capability_registry()
    )
    return registry.freeze()
