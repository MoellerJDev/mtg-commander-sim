from __future__ import annotations

import re

from .dependency_gate import DependencyGate
from .ir_model import OracleNode, SourceSpan


_DREDGE_MECHANIC = "dred" + "ge"
_FABRICATE_MECHANIC = "fabri" + "cate"


def fabricate_keyword_node(
    *,
    node_id: str,
    line: str,
    material_line: str,
    span: SourceSpan,
    mechanics: tuple[str, ...],
    gate: DependencyGate,
    residual_ids: tuple[str, ...],
) -> OracleNode | None:
    matches = tuple(
        match
        for part in material_line.rstrip(".").split(",")
        for match in (
            re.fullmatch(
                r"Fabricate\s+(?P<count>[1-9]\d*)\.?",
                part.strip(),
                re.IGNORECASE,
            ),
        )
        if match is not None
    )
    if mechanics != (_FABRICATE_MECHANIC,) or len(matches) != 1:
        return None
    return OracleNode(
        node_id=node_id,
        kind="triggered_ability",
        text=line,
        span=span,
        active_zone="battlefield",
        event="permanent.enter.self",
        lowerable=True,
        exact=not gate.blockers,
        template_id="fabricate-enter-choice-v1",
        mechanics=mechanics,
        effects=(
            {
                "op": _FABRICATE_MECHANIC,
                "amount": int(matches[0].group("count")),
            },
        ),
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


def dredge_keyword_node(
    *,
    node_id: str,
    line: str,
    material_line: str,
    span: SourceSpan,
    mechanics: tuple[str, ...],
    gate: DependencyGate,
    residual_ids: tuple[str, ...],
) -> OracleNode | None:
    match = re.fullmatch(
        r"Dredge\s+(?P<count>[1-9]\d*)\.?",
        material_line,
        re.IGNORECASE,
    )
    if mechanics != (_DREDGE_MECHANIC,) or match is None:
        return None
    return OracleNode(
        node_id=node_id,
        kind="keyword_ability",
        text=line,
        span=span,
        active_zone="graveyard",
        event="draw",
        lowerable=True,
        exact=not gate.blockers,
        template_id="dredge-keyword-replacement-v1",
        mechanics=mechanics,
        handlers=(
            {
                "handler_id": "replacement.draw.dredge.v1",
                "schema_version": 1,
                "event": "draw",
                "modification": {"mill_count": int(match.group("count"))},
            },
        ),
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


__all__ = ["dredge_keyword_node", "fabricate_keyword_node"]
