from __future__ import annotations

from typing import Any, Mapping

from .counter_placement_templates import (
    fixed_counter_placement_effect_template,
)
from .counter_templates import targeted_counter_effect_template
from .damage_templates import fixed_damage_effect_template
from .destruction_templates import destruction_effect_template
from .exile_templates import targeted_exile_effect_template
from .proliferate_templates import single_proliferate_effect_template
from .return_to_hand_templates import targeted_return_to_hand_effect_template


CompiledEffectTemplate = tuple[
    str | None,
    tuple[Mapping[str, Any], ...],
    Mapping[str, Any] | None,
    tuple[str, ...],
]


def typed_resolution_effect_template(
    text: str,
    *,
    card_name: str,
) -> CompiledEffectTemplate | None:
    """Lower the closed direct-damage and permanent-transition families."""

    fixed_damage = fixed_damage_effect_template(text, card_name=card_name)
    if fixed_damage is not None:
        return fixed_damage.compiled()
    proliferate = single_proliferate_effect_template(text)
    if proliferate is not None:
        return proliferate.compiled()
    fixed_counter_placement = fixed_counter_placement_effect_template(
        text,
        card_name=card_name,
    )
    if fixed_counter_placement is not None:
        return fixed_counter_placement.compiled()
    for compiler in (
        destruction_effect_template,
        targeted_exile_effect_template,
        targeted_return_to_hand_effect_template,
        targeted_counter_effect_template,
    ):
        compiled = compiler(text)
        if compiled is not None:
            return compiled.compiled()
    return None


__all__ = ["CompiledEffectTemplate", "typed_resolution_effect_template"]
