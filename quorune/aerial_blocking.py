from __future__ import annotations

from dataclasses import dataclass


FLYING_KEYWORD = "flying"
AERIAL_BLOCKER_KEYWORDS = frozenset({"flying", "reach"})


@dataclass(frozen=True, slots=True)
class AerialBlockVerdict:
    """Closed result for the represented Flying/Reach block restriction."""

    allowed: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        if type(self.allowed) is not bool:
            raise ValueError("Aerial block verdict allowed must be boolean")
        if self.allowed != (self.reason is None):
            raise ValueError(
                "An allowed aerial block has no rejection reason"
            )
        if self.reason is not None and self.reason != "attacker_has_flying":
            raise ValueError("Unknown aerial block rejection reason")


def aerial_block_verdict(
    attacker_keywords: frozenset[str],
    blocker_keywords: frozenset[str],
) -> AerialBlockVerdict:
    """Apply CR 702.9b and the CR 702.17b Reach exception.

    The declaration coordinator owns every other blocker and attacker
    eligibility rule. This read-only boundary consumes their current effective
    keyword snapshots and answers only the coupled Flying/Reach question.
    """

    for label, keywords in (
        ("attacker", attacker_keywords),
        ("blocker", blocker_keywords),
    ):
        if type(keywords) is not frozenset or any(
            not isinstance(keyword, str)
            or not keyword
            or keyword != keyword.casefold()
            or keyword != keyword.strip()
            for keyword in keywords
        ):
            raise ValueError(
                f"Canonical {label} keyword snapshot is malformed"
            )
    if FLYING_KEYWORD not in attacker_keywords:
        return AerialBlockVerdict(allowed=True)
    if blocker_keywords.intersection(AERIAL_BLOCKER_KEYWORDS):
        return AerialBlockVerdict(allowed=True)
    return AerialBlockVerdict(
        allowed=False,
        reason="attacker_has_flying",
    )


__all__ = [
    "AERIAL_BLOCKER_KEYWORDS",
    "FLYING_KEYWORD",
    "AerialBlockVerdict",
    "aerial_block_verdict",
]
