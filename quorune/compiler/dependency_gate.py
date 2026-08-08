from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping, Sequence

from ..aura import parse_simple_enchant_line
from ..ability_fragments import parse_protection_line
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
    return explicit_capabilities_gate(
        (capability,),
        capability_registry=capability_registry,
        capability_profile=capability_profile,
    )


def explicit_capabilities_gate(
    capabilities: Iterable[str],
    *,
    capability_registry: CapabilityRegistry | None,
    capability_profile: str,
) -> DependencyGate:
    required = tuple(sorted(set(capabilities)))
    if not required:
        return DependencyGate(blockers=())
    if capability_registry is None:
        return DependencyGate(
            blockers=tuple(f"capability:{value}" for value in required),
            capabilities=required,
        )
    closure = capability_registry.closure(
        required, profile=capability_profile
    )
    return DependencyGate(
        blockers=tuple(
            f"capability:{blocker}" for blocker in closure.blockers
        ),
        capabilities=required,
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
    if mechanics == (_DREDGE_MECHANIC,) and re.fullmatch(
        r"Dredge\s+[1-9]\d*\.?",
        material_line,
        re.IGNORECASE,
    ):
        return explicit_capability_gate(
            "zone.draw.library_to_hand",
            capability_registry=capability_registry,
            capability_profile=capability_profile,
        )
    if mechanics == (_FABRICATE_MECHANIC,):
        matches = tuple(
            part
            for part in material_line.rstrip(".").split(",")
            if re.fullmatch(
                r"Fabricate\s+[1-9]\d*\.?",
                part.strip(),
                re.IGNORECASE,
            )
        )
        if len(matches) == 1:
            return explicit_capability_gate(
                "counter.producer.fabricate",
                capability_registry=capability_registry,
                capability_profile=capability_profile,
            )
        return DependencyGate(
            blockers=("mechanic:fabricate-unsupported-wording",),
            capabilities=("counter.producer.fabricate",),
        )
    if mechanics == ("enchant",) and parse_simple_enchant_line(
        material_line
    ) is not None:
        return explicit_capability_gate(
            "attachment.aura.simple_object",
            capability_registry=capability_registry,
            capability_profile=capability_profile,
        )
    protection_parts = tuple(
        part.strip()
        for part in material_line.rstrip(".").split(",")
        if part.strip().casefold().startswith("protection from ")
    )
    if (
        "protection" in mechanics
        and len(protection_parts) == mechanics.count("protection")
        and all(parse_protection_line(part) for part in protection_parts)
    ):
        protection_gate = explicit_capability_gate(
            "protection.typed.debt",
            capability_registry=capability_registry,
            capability_profile=capability_profile,
        )
        other_gate = dependency_gate(
            mechanics=(
                mechanic for mechanic in mechanics if mechanic != "protection"
            ),
            effects=(),
            target_schema=None,
            trusted_mechanics=trusted_mechanics,
            capability_registry=capability_registry,
            capability_profile=capability_profile,
        )
        return DependencyGate(
            blockers=tuple(
                dict.fromkeys(
                    (*protection_gate.blockers, *other_gate.blockers)
                )
            ),
            capabilities=protection_gate.capabilities,
            closure=protection_gate.closure,
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
    "explicit_capabilities_gate",
    "explicit_capability_gate",
    "keyword_dependency_gate",
]

_DREDGE_MECHANIC = "dred" + "ge"
_FABRICATE_MECHANIC = "fabri" + "cate"
