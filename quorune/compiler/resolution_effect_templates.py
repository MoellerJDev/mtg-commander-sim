from __future__ import annotations

from typing import Any, Mapping

from .counter_placement_templates import (
    fixed_counter_placement_effect_template,
    fixed_counter_placement_set_effect_template,
    fixed_counter_placement_target_set_effect_template,
    fixed_player_counter_placement_effect_template,
    support_counter_placement_effect_template,
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
    source_is_permanent: bool | None = None,
) -> CompiledEffectTemplate | None:
    """Lower the closed direct-damage and permanent-transition families."""

    fixed_damage = fixed_damage_effect_template(text, card_name=card_name)
    if fixed_damage is not None:
        return fixed_damage.compiled()
    proliferate = single_proliferate_effect_template(text)
    if proliferate is not None:
        return proliferate.compiled()
    if source_is_permanent is not None:
        support = support_counter_placement_effect_template(
            text,
            source_is_permanent=source_is_permanent,
        )
        if support is not None:
            return support.compiled()
    fixed_player_counter_placement = (
        fixed_player_counter_placement_effect_template(text)
    )
    if fixed_player_counter_placement is not None:
        return fixed_player_counter_placement.compiled()
    fixed_counter_placement_target_set = (
        fixed_counter_placement_target_set_effect_template(text)
    )
    if fixed_counter_placement_target_set is not None:
        return fixed_counter_placement_target_set.compiled()
    fixed_counter_placement_set = fixed_counter_placement_set_effect_template(
        text
    )
    if fixed_counter_placement_set is not None:
        return fixed_counter_placement_set.compiled()
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
