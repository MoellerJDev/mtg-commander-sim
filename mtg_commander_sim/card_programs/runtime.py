from __future__ import annotations

from typing import Any, TYPE_CHECKING, Callable, Mapping, Protocol, Sequence

from ..continuous_effects import ContinuousEffect
from ..semantic_runtime import (
    ContinuousEffectSourceContext,
    default_continuous_effect_component_registry,
)

if TYPE_CHECKING:
    from ..semantics import SemanticRegistry
    from ..semantics import SemanticProgram


class ContinuousRuntimeState(Protocol):
    turn_order: Sequence[str]
    players: Mapping[str, Any]
    cards: Mapping[str, Any]


def collect_card_program_continuous_effects(
    state: ContinuousRuntimeState,
    semantics: "SemanticRegistry",
    program_is_trusted: Callable[["SemanticProgram"], bool],
) -> tuple[ContinuousEffect, ...]:
    registry = default_continuous_effect_component_registry()
    effects: list[ContinuousEffect] = []
    for seat in state.turn_order:
        player = state.players[seat]
        for object_id in list(player.zones["battlefield"]):
            source = state.cards[object_id]
            if source.controller != seat or source.phased_out:
                continue
            programs = semantics.runtime_handler_programs_for_oracle(
                source.oracle_id,
                active_zone="battlefield",
                event="characteristics.evaluate",
            )
            for program in programs:
                if not program_is_trusted(program):
                    continue
                for descriptor_index, descriptor in enumerate(
                    program.handlers
                ):
                    context = ContinuousEffectSourceContext(
                        source_object_id=source.object_id,
                        source_ref=source.ref,
                        source_controller=source.controller,
                        source_timestamp=max(
                            0, int(source.zone_timestamp)
                        ),
                        component_id=(
                            f"{program.key}:{descriptor_index}"
                        ),
                    )
                    effects.extend(registry.lower(descriptor, context))
    return tuple(
        sorted(
            effects,
            key=lambda effect: (
                int(effect.layer),
                effect.sublayer,
                effect.timestamp,
                effect.effect_id,
            ),
        )
    )
