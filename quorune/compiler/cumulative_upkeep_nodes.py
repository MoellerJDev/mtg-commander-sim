from __future__ import annotations

from ..cumulative_upkeep import (
    CUMULATIVE_UPKEEP_MECHANIC_ID,
    compile_fixed_mana_cumulative_upkeep,
)
from ..rules.capabilities import CapabilityRegistry
from .dependency_gate import explicit_capability_gate
from .ir_model import append_residual, OracleNode, OracleResidual, SourceSpan


def fixed_mana_cumulative_upkeep_node(
    *,
    node_id: str,
    line: str,
    material_line: str,
    span: SourceSpan,
    mechanics: tuple[str, ...],
    capability_registry: CapabilityRegistry | None,
    capability_profile: str,
    residuals: list[OracleResidual],
) -> OracleNode | None:
    """Lower the closed fixed ordinary mana cumulative-upkeep family."""

    if mechanics != (CUMULATIVE_UPKEEP_MECHANIC_ID,):
        return None
    spec = compile_fixed_mana_cumulative_upkeep(material_line)
    if spec is None:
        residual_id = append_residual(
            residuals,
            kind="unsupported_cumulative_upkeep_cost",
            text=line,
            span=span,
            reason=(
                "Cumulative upkeep cost is outside the closed fixed ordinary mana grammar"
            ),
            blockers=(
                "alternative, snow, hybrid, Phyrexian, and variable costs",
                "nonmana costs, modifiers, and multiple instances",
            ),
        )
        return OracleNode(
            node_id=node_id,
            kind="triggered_ability",
            text=line,
            span=span,
            active_zone="battlefield",
            event="step.begin",
            lowerable=False,
            exact=False,
            template_id="fixed-mana-cumulative-upkeep-residual-v1",
            mechanics=mechanics,
            residual_ids=(residual_id,),
        )
    gate = explicit_capability_gate(
        "counter.producer.cumulative_upkeep_fixed_mana",
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
                    "fixed-mana cumulative upkeep lacks a trusted capability closure"
                ),
                blockers=gate.blockers,
            ),
        )
        if gate.blockers
        else ()
    )
    return OracleNode(
        node_id=node_id,
        kind="triggered_ability",
        text=line,
        span=span,
        active_zone="battlefield",
        event="step.begin",
        event_condition={
            "all": [
                {
                    "field": "player",
                    "op": "eq",
                    "value": "$source.controller",
                },
                {"field": "step", "op": "eq", "value": "upkeep"},
            ]
        },
        lowerable=True,
        exact=not residual_ids,
        template_id="fixed-mana-cumulative-upkeep-v1",
        effects=(spec.effect_descriptor(),),
        mechanics=mechanics,
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


__all__ = ["fixed_mana_cumulative_upkeep_node"]
