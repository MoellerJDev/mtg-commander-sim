from __future__ import annotations

from dataclasses import dataclass

from . import aerial_blocking
from .landwalk import basic_landwalk_block_verdict


SHADOW_KEYWORD = "shadow"
_REJECTION_REASONS = frozenset(
    {
        "attacker_has_shadow",
        "blocker_has_shadow",
        "attacker_has_flying",
        "attacker_has_plainswalk",
        "attacker_has_islandwalk",
        "attacker_has_swampwalk",
        "attacker_has_mountainwalk",
        "attacker_has_forestwalk",
    }
)


@dataclass(frozen=True, slots=True)
class CombatEvasionVerdict:
    """Cumulative verdict for represented keyword block restrictions."""

    allowed: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        if type(self.allowed) is not bool:
            raise ValueError("Combat evasion verdict allowed must be boolean")
        if self.allowed != (self.reason is None):
            raise ValueError("An allowed combat evasion verdict has no reason")
        if self.reason is not None and self.reason not in _REJECTION_REASONS:
            raise ValueError("Unknown combat evasion rejection reason")


def combat_evasion_verdict(
    attacker_keywords: frozenset[str],
    blocker_keywords: frozenset[str],
    defending_land_types: frozenset[str],
) -> CombatEvasionVerdict:
    """Compose Shadow, Flying/Reach, and Basic Landwalk fail-closed."""

    # Validate every represented family before returning a restriction from
    # another family, so an unsupported landwalk variant cannot be masked.
    landwalk = basic_landwalk_block_verdict(
        attacker_keywords,
        defending_land_types,
    )
    aerial = aerial_blocking.aerial_block_verdict(
        attacker_keywords,
        blocker_keywords,
    )
    if SHADOW_KEYWORD in attacker_keywords and SHADOW_KEYWORD not in blocker_keywords:
        return CombatEvasionVerdict(False, "attacker_has_shadow")
    if SHADOW_KEYWORD in blocker_keywords and SHADOW_KEYWORD not in attacker_keywords:
        return CombatEvasionVerdict(False, "blocker_has_shadow")
    if not aerial.allowed:
        return CombatEvasionVerdict(False, aerial.reason)
    if not landwalk.allowed:
        return CombatEvasionVerdict(False, landwalk.reason)
    return CombatEvasionVerdict(True)


__all__ = [
    "CombatEvasionVerdict",
    "SHADOW_KEYWORD",
    "combat_evasion_verdict",
]
