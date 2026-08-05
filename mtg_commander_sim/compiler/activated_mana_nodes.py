from __future__ import annotations

"""Closed Oracle-IR lowering for fixed-output activated mana abilities."""

from dataclasses import replace
from typing import Any, Callable, Mapping, Sequence

from ..abilities import parse_activated_abilities
from ..fixed_mana_abilities import (
    compile_fixed_activated_mana_ability,
    fixed_mana_handler_descriptor,
)
from ..rules.capabilities import CapabilityRegistry
from .activated_costs import activated_ability_cost
from .dependency_gate import explicit_capability_gate
from .ir_model import (
    append_residual,
    OracleNode,
    OracleResidual,
    SourceSpan,
)


def fixed_activated_mana_node(
    ability: Any,
    node_id: str,
    line: str,
    span: SourceSpan,
    capability_registry: CapabilityRegistry | None,
    capability_profile: str,
    residuals: list[OracleResidual],
) -> tuple[Any, OracleNode | None]:
    ability = replace(
        ability,
        ability_id=f"ab{span.line}",
        line_index=span.line - 1,
    )
    spec = compile_fixed_activated_mana_ability(ability)
    if spec is None:
        return ability, None
    gate = explicit_capability_gate(
        "mana.activated.fixed_output",
        capability_registry=capability_registry,
        capability_profile=capability_profile,
    )
    residual_ids = (
        (
            append_residual(
                residuals,
                kind="dependency_contract",
                text=line,
                span=span,
                reason=(
                    "fixed-output activated mana ability lacks a trusted "
                    "capability closure"
                ),
                blockers=gate.blockers,
            ),
        )
        if gate.blockers
        else ()
    )
    return ability, OracleNode(
        node_id=node_id,
        kind="mana_ability",
        text=line,
        span=span,
        active_zone="battlefield",
        event="activate",
        lowerable=True,
        exact=not gate.blockers,
        template_id="activated-mana-fixed-output-v1",
        cost=activated_ability_cost(ability),
        handlers=(fixed_mana_handler_descriptor(spec),),
        residual_ids=residual_ids,
        capability_dependencies=gate.capabilities,
        capability_closure=(
            gate.closure.reachable if gate.closure is not None else ()
        ),
        capability_profile=(
            gate.closure.profile if gate.closure is not None else None
        ),
        capability_fingerprint=(
            gate.closure.fingerprint if gate.closure is not None else None
        ),
    )


def unresolved_activated_mana_residual(
    ability: Any, span: SourceSpan, residuals: list[OracleResidual]
) -> str:
    return append_residual(
        residuals,
        kind="mana_ability",
        text=ability.effect_text,
        span=span,
        reason=(
            "activated mana ability is outside the typed fixed-output grammar"
        ),
        blockers=(
            "dynamic or conditional mana output",
            "restricted mana or effect-clause side effects",
            "unrepresented activation-cost variant",
        ),
    )


def activated_oracle_node(
    *,
    node_id: str,
    line: str,
    span: SourceSpan,
    card_name: str,
    keywords: Sequence[str],
    trusted_mechanics: frozenset[str],
    capability_registry: CapabilityRegistry | None,
    capability_profile: str,
    residuals: list[OracleResidual],
    effect_template: Callable[..., tuple[
        str | None,
        tuple[Mapping[str, Any], ...],
        Mapping[str, Any] | None,
        tuple[str, ...],
    ]],
) -> OracleNode | None:
    """Compile one complete colon-form activated-ability Oracle line."""

    abilities = parse_activated_abilities(
        card_name=card_name,
        oracle_text=line,
        keywords=keywords,
    )
    if not abilities:
        return None
    ability, fixed_mana = fixed_activated_mana_node(
        abilities[0], node_id, line, span, capability_registry,
        capability_profile, residuals,
    )
    if fixed_mana is not None:
        return fixed_mana
    template, effects, target_schema, mechanics = effect_template(
        ability.effect_text,
        card_name=card_name,
    )
    residual_ids: list[str] = []
    if not ability.compiled_cost:
        residual_ids.append(
            append_residual(
                residuals,
                kind="cost",
                text=ability.cost_text,
                span=span,
                reason="mandatory activated cost is not compiled",
                blockers=(
                    "complete alternate/additional-cost grammar",
                    "restricted payment predicates",
                ),
            )
        )
    if template is None and not ability.mana_ability:
        residual_ids.append(
            append_residual(
                residuals,
                kind="effect",
                text=ability.effect_text,
                span=span,
                reason="activated effect has no exact generic template",
            )
        )
    if ability.mana_ability:
        residual_ids.append(
            unresolved_activated_mana_residual(ability, span, residuals)
        )
    lowerable = not residual_ids and (
        template is not None or ability.mana_ability
    )
    dependencies = mechanics if template is not None else ()
    missing = sorted(set(dependencies) - trusted_mechanics)
    if lowerable and missing:
        residual_ids.append(
            append_residual(
                residuals,
                kind="dependency_contract",
                text=line,
                span=span,
                reason=(
                    "lowerable ability depends on untrusted mechanic contracts"
                ),
                blockers=tuple(
                    f"mechanic:{mechanic}" for mechanic in missing
                ),
            )
        )
    return OracleNode(
        node_id=node_id,
        kind=(
            "mana_ability" if ability.mana_ability else "activated_ability"
        ),
        text=line,
        span=span,
        active_zone=ability.zones[0],
        event="activate",
        lowerable=lowerable,
        exact=lowerable and not missing,
        template_id=(
            "intrinsic-mana-ability-v1"
            if ability.mana_ability and template is None
            else template
        ),
        cost=activated_ability_cost(ability),
        effects=effects,
        target_schema=target_schema,
        mechanics=mechanics,
        residual_ids=tuple(residual_ids),
    )


__all__ = [
    "activated_oracle_node",
    "fixed_activated_mana_node",
    "unresolved_activated_mana_residual",
]
