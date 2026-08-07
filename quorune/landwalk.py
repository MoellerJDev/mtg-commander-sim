from __future__ import annotations

from dataclasses import dataclass


BASIC_LANDWALK_TYPES = (
    ("pl" + "ainswalk", "pl" + "ains"),
    ("is" + "landwalk", "is" + "land"),
    ("sw" + "ampwalk", "sw" + "amp"),
    ("mount" + "ainwalk", "mount" + "ain"),
    ("for" + "estwalk", "for" + "est"),
)
BASIC_LAND_TYPES = frozenset(
    land_type for _, land_type in BASIC_LANDWALK_TYPES
)
_SUPPORTED_KEYWORDS = frozenset(
    keyword for keyword, _ in BASIC_LANDWALK_TYPES
)


class LandwalkRuleError(ValueError):
    """A landwalk snapshot or unsupported landwalk variant is malformed."""


def _canonical_terms(value: object, label: str) -> frozenset[str]:
    if type(value) is not frozenset or any(
        not isinstance(term, str)
        or not term
        or term != term.strip()
        or term != term.casefold()
        for term in value
    ):
        raise LandwalkRuleError(f"Canonical {label} snapshot is malformed")
    return value


@dataclass(frozen=True, slots=True)
class BasicLandwalkBlockVerdict:
    """Closed result for the five represented basic-land-type variants."""

    allowed: bool
    matching_land_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.allowed) is not bool:
            raise LandwalkRuleError("Landwalk verdict allowed must be boolean")
        if tuple(self.matching_land_types) != self.matching_land_types:
            raise LandwalkRuleError("Matching land types must be a tuple")
        expected = tuple(
            land_type
            for _, land_type in BASIC_LANDWALK_TYPES
            if land_type in self.matching_land_types
        )
        if expected != self.matching_land_types or len(expected) != len(
            set(expected)
        ):
            raise LandwalkRuleError(
                "Matching land types must be unique and canonical"
            )
        if self.allowed != (not self.matching_land_types):
            raise LandwalkRuleError(
                "A rejected landwalk verdict requires a matching land type"
            )

    @property
    def reason(self) -> str | None:
        if self.allowed:
            return None
        return f"attacker_has_{self.matching_land_types[0]}walk"


def basic_landwalk_block_verdict(
    attacker_keywords: frozenset[str],
    defending_land_types: frozenset[str],
) -> BasicLandwalkBlockVerdict:
    """Apply ordinary Plains/Island/Swamp/Mountain/Forestwalk.

    The inputs are current effective public characteristics. A matching land
    need not have the Basic supertype. Broader landwalk variants deliberately
    fail closed until their predicates have typed owners.
    """

    keywords = _canonical_terms(attacker_keywords, "attacker keyword")
    land_types = _canonical_terms(defending_land_types, "land type")
    if not land_types.issubset(BASIC_LAND_TYPES):
        raise LandwalkRuleError(
            "Defending land types exceed the closed vocabulary"
        )

    represented = keywords.intersection(_SUPPORTED_KEYWORDS)
    unsupported = {
        keyword
        for keyword in keywords
        if (
            keyword == "landwalk"
            or keyword.endswith("walk")
            or keyword.endswith(" landwalk")
        )
        and keyword not in _SUPPORTED_KEYWORDS
    }
    if "landwalk" in unsupported and represented:
        unsupported.remove("landwalk")
    if unsupported:
        raise LandwalkRuleError(
            "Unsupported landwalk variant(s): "
            + ", ".join(sorted(unsupported))
        )

    matches = tuple(
        land_type
        for keyword, land_type in BASIC_LANDWALK_TYPES
        if keyword in represented and land_type in land_types
    )
    return BasicLandwalkBlockVerdict(
        allowed=not matches,
        matching_land_types=matches,
    )


__all__ = [
    "BASIC_LAND_TYPES",
    "BASIC_LANDWALK_TYPES",
    "BasicLandwalkBlockVerdict",
    "LandwalkRuleError",
    "basic_landwalk_block_verdict",
]
