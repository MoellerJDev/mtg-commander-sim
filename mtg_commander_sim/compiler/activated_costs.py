from __future__ import annotations

from typing import Any

from ..abilities import ActivatedAbility


def activated_ability_cost(ability: ActivatedAbility) -> dict[str, Any]:
    """Serialize the compiler-facing cost facts for one activated ability."""

    return {
        "text": ability.cost_text,
        "mana": dict(ability.mana),
        "complex_symbols": list(ability.complex_symbols),
        "tap_source": ability.tap_source,
        "untap_source": ability.untap_source,
        "discard_source": ability.discard_source,
        "sacrifice_source": ability.sacrifice_source,
        "exile_source": ability.exile_source,
        "life_payment": ability.life_payment,
        "energy_payment": ability.energy_payment,
        "loyalty_delta": ability.loyalty_delta,
        "choices": [choice.compact() for choice in ability.choices],
        "uncompiled_costs": list(ability.uncompiled_costs),
    }


__all__ = ["activated_ability_cost"]
