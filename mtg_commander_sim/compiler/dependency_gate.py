from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping, Sequence

from ..aura import parse_simple_enchant_line
from ..rules.capabilities import (
    CapabilityClosure,
    CapabilityRegistry,
    capability_covered_mechanics,
    capability_dependencies_for_node,
)


@dataclass(frozen=True, slots=True)
class DependencyGate:
    blockers: tuple[str, ...]
    capabilities: tuple[str, ...] = ()
    closure: CapabilityClosure | None = None


def dependency_gate(
    *,
    mechanics: Iterable[str],
    effects: Sequence[Mapping[str, Any]],
    target_schema: Mapping[str, Any] | None,
    trusted_mechanics: frozenset[str],
    capability_registry: CapabilityRegistry | None,
    capability_profile: str,
) -> DependencyGate:
    mechanic_ids = tuple(str(value).casefold() for value in mechanics)
    capabilities = capability_dependencies_for_node(
        effects=effects,
        target_schema=target_schema,
        mechanic_ids=mechanic_ids,
    )
    if capability_registry is not None and capabilities:
        closure = capability_registry.closure(
            capabilities,
            profile=capability_profile,
        )
        covered = set(capability_covered_mechanics(capabilities))
        unmapped = sorted(set(mechanic_ids) - trusted_mechanics - covered)
        return DependencyGate(
            blockers=(
                *(f"capability:{blocker}" for blocker in closure.blockers),
                *(f"mechanic:{mechanic}" for mechanic in unmapped),
            ),
            capabilities=capabilities,
            closure=closure,
        )
    return DependencyGate(
        blockers=tuple(
            f"mechanic:{mechanic}"
            for mechanic in sorted(set(mechanic_ids) - trusted_mechanics)
        )
    )


def explicit_capability_gate(
    capability: str,
    *,
    capability_registry: CapabilityRegistry | None,
    capability_profile: str,
) -> DependencyGate:
    if capability_registry is None:
        return DependencyGate(
            blockers=(f"capability:{capability}",),
            capabilities=(capability,),
        )
    closure = capability_registry.closure(
        (capability,), profile=capability_profile
    )
    return DependencyGate(
        blockers=tuple(
            f"capability:{blocker}" for blocker in closure.blockers
        ),
        capabilities=(capability,),
        closure=closure,
    )


def keyword_dependency_gate(
    *,
    material_line: str,
    mechanics: tuple[str, ...],
    trusted_mechanics: frozenset[str],
    capability_registry: CapabilityRegistry | None,
    capability_profile: str,
) -> DependencyGate:
    """Select a reviewed keyword capability before generic mechanic gating."""

    if mechanics == ("equip",) and re.fullmatch(
        r"Equip\s+(?:\{(?:\d+|[WUBRGC])\})+\.?",
        material_line,
        re.IGNORECASE,
    ):
        return explicit_capability_gate(
            "attachment.equip.fixed_mana",
            capability_registry=capability_registry,
            capability_profile=capability_profile,
        )
    if mechanics == ("dredge",) and re.fullmatch(
        r"Dredge\s+[1-9]\d*\.?",
        material_line,
        re.IGNORECASE,
    ):
        return explicit_capability_gate(
            "zone.draw.library_to_hand",
            capability_registry=capability_registry,
            capability_profile=capability_profile,
        )
    if mechanics == ("enchant",) and parse_simple_enchant_line(
        material_line
    ) is not None:
        return explicit_capability_gate(
            "attachment.aura.simple_object",
            capability_registry=capability_registry,
            capability_profile=capability_profile,
        )
    return dependency_gate(
        mechanics=mechanics,
        effects=(),
        target_schema=None,
        trusted_mechanics=trusted_mechanics,
        capability_registry=capability_registry,
        capability_profile=capability_profile,
    )


__all__ = [
    "DependencyGate",
    "dependency_gate",
    "explicit_capability_gate",
    "keyword_dependency_gate",
]
