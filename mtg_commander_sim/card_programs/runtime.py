from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING, Callable, Mapping, Protocol, Sequence

from ..attachments import attached_object_identity
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


@dataclass(slots=True)
class ContinuousEffectCollectionMetrics:
    collection_calls: int = 0
    battlefield_objects_inspected: int = 0
    card_program_lookups: int = 0
    descriptors_inspected: int = 0
    effects_produced: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "collection_calls": self.collection_calls,
            "battlefield_objects_inspected": self.battlefield_objects_inspected,
            "card_program_lookups": self.card_program_lookups,
            "descriptors_inspected": self.descriptors_inspected,
            "effects_produced": self.effects_produced,
        }


def collect_card_program_continuous_effects(
    state: ContinuousRuntimeState,
    semantics: "SemanticRegistry",
    program_is_trusted: Callable[["SemanticProgram"], bool],
    *,
    metrics: ContinuousEffectCollectionMetrics | None = None,
) -> tuple[ContinuousEffect, ...]:
    registry = default_continuous_effect_component_registry()
    if metrics is not None:
        metrics.collection_calls += 1
    effects: list[ContinuousEffect] = []
    for seat in state.turn_order:
        player = state.players[seat]
        for object_id in list(player.zones["battlefield"]):
            if metrics is not None:
                metrics.battlefield_objects_inspected += 1
            source = state.cards[object_id]
            if source.controller != seat or source.phased_out:
                continue
            programs = semantics.runtime_handler_programs_for_oracle(
                source.oracle_id,
                active_zone="battlefield",
                event="characteristics.evaluate",
            )
            if metrics is not None:
                metrics.card_program_lookups += 1
            for program in programs:
                if not program_is_trusted(program):
                    continue
                for descriptor_index, descriptor in enumerate(
                    program.handlers
                ):
                    if metrics is not None:
                        metrics.descriptors_inspected += 1
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
                        attached_object=(
                            attached_object_identity(state.cards, source)
                            if getattr(source, "attached_to", None)
                            else None
                        ),
                    )
                    lowered = registry.lower(descriptor, context)
                    effects.extend(lowered)
                    if metrics is not None:
                        metrics.effects_produced += len(lowered)
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
