from __future__ import annotations

from collections import Counter
import hashlib

from .model import GameState
from .util import stable_json


def deck_list_fingerprints(state: GameState) -> dict[str, str]:
    """Hash each seat's exact physical deck list for record provenance."""

    result: dict[str, str] = {}
    for seat in state.turn_order:
        counts = Counter(
            (
                card.printed_name,
                "commander" if card.is_commander else "mainboard",
            )
            for card in state.cards.values()
            if card.owner == seat and card.is_card_object
        )
        payload = {
            "commanders": sorted(
                card.printed_name
                for card in state.cards.values()
                if card.owner == seat
                and card.is_card_object
                and card.is_commander
            ),
            "cards": sorted(
                (name, quantity, board)
                for (name, board), quantity in counts.items()
            ),
        }
        result[seat] = hashlib.sha256(
            stable_json(payload).encode("utf-8")
        ).hexdigest()
    return result


def deck_fingerprints(state: GameState) -> dict[str, str]:
    """Compatibility alias for the exact Game Record v3 deck-list hash."""

    return deck_list_fingerprints(state)
