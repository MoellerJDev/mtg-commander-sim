from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..effect_contracts import EffectFamilyContract, effect_operation_contracts
from ..replacement.immutable import FrozenMap
from .context import ReadOnlyHandlerContext, SemanticNodeError
from .intents import DomainEffectIntent, IntentPlan


@dataclass(frozen=True, slots=True)
class DomainEffectHandler:
    operation: str
    contract: EffectFamilyContract
    schema_version: int = 1
    capability_dependencies: tuple[str, ...] = ()

    @property
    def handler_id(self) -> str:
        return f"{self.contract.semantic_family}.{self.operation}.v1"

    @property
    def family(self) -> str:
        return self.contract.semantic_family

    @property
    def rule_references(self) -> tuple[str, ...]:
        return self.contract.rule_references

    def lower(
        self,
        effect: Mapping[str, Any],
        context: ReadOnlyHandlerContext,
    ) -> IntentPlan:
        operation = str(effect.get("op") or "").casefold()
        if operation != self.operation:
            raise SemanticNodeError(
                f"Handler {self.handler_id} cannot lower {operation!r}"
            )
        reason = str(effect.get("reason") or context.default_reason)
        if not reason:
            raise SemanticNodeError("A domain effect requires a reason")
        return IntentPlan(
            operation=self.operation,
            handler_id=self.handler_id,
            intents=(
                DomainEffectIntent(
                    actor=context.actor,
                    operation=self.operation,
                    effect=FrozenMap(effect),
                    reason=reason,
                ),
            ),
        )


DOMAIN_EFFECT_HANDLERS = tuple(
    DomainEffectHandler(operation=operation, contract=contract)
    for operation, contract in effect_operation_contracts()
)
