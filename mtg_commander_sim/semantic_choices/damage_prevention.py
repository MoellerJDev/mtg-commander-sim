from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..replacement.immutable import FrozenMap, thaw_value
from .context import SemanticChoiceContext, SemanticChoiceQuery
from .model import (
    ObjectChoice,
    SemanticChoiceCompletion,
    SemanticChoiceContinuation,
    SemanticChoiceError,
    SemanticChoicePreparation,
    SemanticChoiceRequest,
)


_EXILE_ZONE = "".join(("ex", "ile"))
_PUBLIC_SOURCE_ZONES = (
    "battlefield",
    "command",
    _EXILE_ZONE,
    "graveyard",
    "stack",
)


def _normalized(value: Any, *, upper: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise SemanticChoiceError("Chosen-source filters must be arrays")
    normalizer = str.upper if upper else str.casefold
    result = tuple(sorted({normalizer(str(item)) for item in value if str(item)}))
    if len(result) != len(value):
        raise SemanticChoiceError(
            "Chosen-source filters require unique nonempty values"
        )
    return result


def _candidates(
    query: SemanticChoiceQuery,
    *,
    required_colors: tuple[str, ...],
    allowed_colors: tuple[str, ...],
    required_types: tuple[str, ...],
    required_subtypes: tuple[str, ...],
    required_supertypes: tuple[str, ...],
    required_keywords: tuple[str, ...],
) -> tuple[Any, ...]:
    colors = set(required_colors)
    any_colors = set(allowed_colors)
    types = set(required_types)
    subtypes = set(required_subtypes)
    supertypes = set(required_supertypes)
    keywords = set(required_keywords)
    rows = query.objects(zones=_PUBLIC_SOURCE_ZONES)
    legal_refs = frozenset(query.damage_source_candidate_refs())
    if not query.damage_source_candidates_are_complete:
        # Compatibility for manually constructed/query-v1 snapshots. Live
        # engine snapshots always materialize the full candidate provenance.
        legal_refs = frozenset(
            row.ref
            for row in rows
            if row.zone in {"battlefield", "command", "stack"}
        )
    return tuple(
        sorted(
            (
                row
                for row in rows
                if row.known_to_actor
                and row.ref in legal_refs
                and colors.issubset(row.colors)
                and (not any_colors or any_colors.intersection(row.colors))
                and types.issubset(row.types)
                and subtypes.issubset(row.subtypes)
                and supertypes.issubset(row.supertypes)
                and keywords.issubset(row.keywords)
            ),
            key=lambda row: row.ref,
        )
    )


@dataclass(frozen=True, slots=True)
class ChooseDamageSourceHandler:
    operation: str = "choose_damage_source"
    handler_id: str = "choice.damage.choose-source.v1"
    schema_version: int = 1
    rule_references: tuple[str, ...] = ("CR 609.7a", "CR 615.1")
    capability_dependencies: tuple[str, ...] = (
        "damage.prevention.persistent_amount",
    )
    continuation_fields: tuple[str, ...] = (
        "shield",
        "required_colors",
        "allowed_colors",
        "required_types",
        "required_subtypes",
        "required_supertypes",
        "required_keywords",
        "_legal_refs",
    )
    private_data: tuple[str, ...] = ()
    projected_fields: tuple[str, ...] = (
        "prompt",
        "objects",
        "legal_actions.choice_schema.legal_refs",
    )
    mutation_path: tuple[str, ...] = (
        "PreventionShieldCreationRequest",
        "commit_prevention_shield_creation",
    )
    replay_fixture: str = "damage-prevention-chosen-source"
    test_modules: tuple[str, ...] = (
        "tests.test_damage_prevention_creation",
    )

    def prepare(
        self,
        effect: Mapping[str, Any],
        context: SemanticChoiceContext,
    ) -> SemanticChoicePreparation:
        shield = effect.get("shield")
        if not isinstance(shield, Mapping) or shield.get("op") != (
            "create_damage_prevention_shield"
        ):
            raise SemanticChoiceError(
                "A chosen source must continue into a prevention shield"
            )
        required_colors = _normalized(
            effect.get("required_colors", ()), upper=True
        )
        allowed_colors = _normalized(
            effect.get("allowed_colors", ()), upper=True
        )
        if required_colors and allowed_colors:
            raise SemanticChoiceError(
                "Damage-source colors cannot require both all and any modes"
            )
        required_types = _normalized(effect.get("required_types", ()))
        required_subtypes = _normalized(effect.get("required_subtypes", ()))
        required_supertypes = _normalized(
            effect.get("required_supertypes", ())
        )
        required_keywords = _normalized(effect.get("required_keywords", ()))
        candidates = _candidates(
            context.query,
            required_colors=required_colors,
            allowed_colors=allowed_colors,
            required_types=required_types,
            required_subtypes=required_subtypes,
            required_supertypes=required_supertypes,
            required_keywords=required_keywords,
        )
        if not candidates:
            raise SemanticChoiceError(
                "No legally known damage source is available to choose"
            )
        legal_refs = tuple(row.ref for row in candidates)
        continuation = FrozenMap(
            {
                **dict(effect),
                "required_colors": list(required_colors),
                "allowed_colors": list(allowed_colors),
                "required_types": list(required_types),
                "required_subtypes": list(required_subtypes),
                "required_supertypes": list(required_supertypes),
                "required_keywords": list(required_keywords),
                "_legal_refs": list(legal_refs),
            }
        )
        return SemanticChoicePreparation(
            request=SemanticChoiceRequest(
                prompt=str(effect.get("prompt") or "Choose a damage source."),
                choice=ObjectChoice(
                    field_name="source",
                    legal_refs=legal_refs,
                    zones=_PUBLIC_SOURCE_ZONES,
                    visibility="public",
                    predicates=FrozenMap(
                        {
                            "colors_all": list(required_colors),
                            "colors_any": list(allowed_colors),
                            "types_all": list(required_types),
                            "subtypes_all": list(required_subtypes),
                            "supertypes_all": list(required_supertypes),
                            "keywords_all": list(required_keywords),
                        }
                    ),
                ),
                public_context=FrozenMap(
                    {
                        "operation": self.operation,
                        "objects": [
                            {
                                "id": row.ref,
                                "name": row.printed_name,
                                "zone": row.zone,
                            }
                            for row in candidates
                        ],
                    }
                ),
            ),
            continuation_effect=continuation,
        )

    def complete(
        self,
        continuation: SemanticChoiceContinuation,
        response: Mapping[str, Any],
        query: SemanticChoiceQuery,
    ) -> SemanticChoiceCompletion:
        selected = response.get("source")
        if not isinstance(selected, str) or not selected:
            raise SemanticChoiceError("A damage source selection is required")
        legal_refs = tuple(
            str(value) for value in continuation.effect.get("_legal_refs", ())
        )
        if selected not in legal_refs:
            raise SemanticChoiceError(
                "The selected damage source was not offered to this seat"
            )
        required_colors = _normalized(
            thaw_value(continuation.effect.get("required_colors", ())),
            upper=True,
        )
        required_types = _normalized(
            thaw_value(continuation.effect.get("required_types", ()))
        )
        allowed_colors = _normalized(
            thaw_value(continuation.effect.get("allowed_colors", ())),
            upper=True,
        )
        required_subtypes = _normalized(
            thaw_value(continuation.effect.get("required_subtypes", ()))
        )
        required_supertypes = _normalized(
            thaw_value(continuation.effect.get("required_supertypes", ()))
        )
        required_keywords = _normalized(
            thaw_value(continuation.effect.get("required_keywords", ()))
        )
        current = {
            row.ref: row
            for row in _candidates(
                query,
                required_colors=required_colors,
                allowed_colors=allowed_colors,
                required_types=required_types,
                required_subtypes=required_subtypes,
                required_supertypes=required_supertypes,
                required_keywords=required_keywords,
            )
        }
        if selected not in current:
            raise SemanticChoiceError(
                "The selected damage source is no longer a legal candidate"
            )
        shield = continuation.effect.get("shield")
        if not isinstance(shield, Mapping):
            raise SemanticChoiceError(
                "The chosen-source continuation lost its shield"
            )
        return SemanticChoiceCompletion(
            prepend_effects=(
                FrozenMap(
                    {
                        **thaw_value(shield),
                        "chosen_source": selected,
                        "source_colors": list(required_colors),
                        "source_colors_any": list(allowed_colors),
                        "source_types": list(required_types),
                        "source_subtypes": list(required_subtypes),
                        "source_supertypes": list(required_supertypes),
                        "source_keywords": list(required_keywords),
                    }
                ),
            )
        )


DAMAGE_PREVENTION_CHOICE_HANDLERS = (ChooseDamageSourceHandler(),)


__all__ = [
    "ChooseDamageSourceHandler",
    "DAMAGE_PREVENTION_CHOICE_HANDLERS",
]
