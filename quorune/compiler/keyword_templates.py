from __future__ import annotations

import re
from typing import Sequence


_KEYWORD_WITH_VALUE = re.compile(
    r"^(?P<name>ward|equip|enchant|bushido|cycling|crew|dredge|kicker|toxic|"
    r"cumulative upkeep|echo|fabricate|morph|bestow|evoke|unearth)"
    r"(?:\s+(?P<value>.+))?$",
    re.IGNORECASE,
)
_KNOWN_BARE_KEYWORDS = frozenset(
    "deathtouch|defender|double strike|first strike|flash|flying|haste|"
    "flanking|hexproof|indestructible|infect|lifelink|menace|reach|shadow|shroud|"
    "trample|vigilance|wither".split("|")
)


def keyword_mechanics(
    text: str,
    card_keywords: Sequence[str],
) -> tuple[str, ...] | None:
    """Recognize a complete Oracle line made only of printed keywords."""

    parts = [part.strip() for part in text.rstrip(".").split(",")]
    if not parts:
        return None
    known = {keyword.casefold() for keyword in card_keywords}
    mechanics: list[str] = []
    for part in parts:
        lower = part.casefold()
        if lower in _KNOWN_BARE_KEYWORDS or lower in known:
            mechanics.append(lower)
            continue
        match = _KEYWORD_WITH_VALUE.fullmatch(part)
        if match and match.group("name").casefold() in known:
            mechanics.append(match.group("name").casefold())
            continue
        if lower.startswith("protection from ") and "protection" in known:
            mechanics.append("protection")
            continue
        return None
    return tuple(mechanics)
