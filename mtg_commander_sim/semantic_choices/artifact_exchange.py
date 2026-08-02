from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..replacement.immutable import FrozenMap
from ..semantic_runtime.intents import (
    CreateTokenIntent,
    PayManaCostIntent,
    RecordChoiceIntent,
    ShuffleLibraryIntent,
    ZoneMoveIntent,
)
from .context import SemanticChoiceContext, SemanticChoiceQuery
from .model import (
    AutoContinue,
    ObjectChoice,
    ScalarChoice,
    SemanticChoiceCompletion,
    SemanticChoiceContinuation,
    SemanticChoiceError,
    SemanticChoicePreparation,
    SemanticChoiceRequest,
)


def _artifacts(
    query: SemanticChoiceQuery,
    actor: str,
    *,
    zone: str,
    controlled: bool = False,
) -> tuple[Any, ...]:
    return tuple(
        row
        for row in query.objects(
            zones=(zone,),
            owner=actor if zone != "battlefield" else None,
            controller=actor if controlled else None,
        )
        if "artifact" in row.types
    )


@dataclass(frozen=True, slots=True)
class DarettiExchangeChoiceHandler:
    operation: str = "daretti_exchange"
    handler_id: str = "choice.artifact.sacrifice-return.v1"
    schema_version: int = 1
    rule_references: tuple[str, ...] = ("CR 701.17", "CR 701.14")
    capability_dependencies: tuple[str, ...] = ()
    continuation_fields: tuple[str, ...] = (
        "card",
        "_choice_actor",
        "_legal_refs",
        "_stack_label",
    )
    private_data: tuple[str, ...] = ()
    projected_fields: tuple[str, ...] = (
        "prompt",
        "objects",
        "legal_actions.choice_schema.legal_refs",
    )
    mutation_path: tuple[str, ...] = ("ZoneMoveIntent",)
    replay_fixture: str = "semantic-choice-daretti-exchange"
    test_modules: tuple[str, ...] = ("tests.test_exact_mishra_closure",)

    def prepare(
        self,
        effect: Mapping[str, Any],
        context: SemanticChoiceContext,
    ) -> SemanticChoicePreparation:
        rows = _artifacts(
            context.query,
            context.actor,
            zone="battlefield",
            controlled=True,
        )
        if not rows:
            return SemanticChoicePreparation(
                request=None,
                continuation_effect=FrozenMap(effect),
                auto_continue=AutoContinue(reason="no artifact to sacrifice"),
            )
        refs = tuple(row.ref for row in rows)
        return SemanticChoicePreparation(
            request=SemanticChoiceRequest(
                prompt="Choose an artifact you control to sacrifice.",
                choice=ObjectChoice(
                    field_name="card",
                    legal_refs=refs,
                    zones=("battlefield",),
                    controller_relation="actor",
                    predicates=FrozenMap({"types": ["artifact"]}),
                ),
                public_context=FrozenMap(
                    {
                        "stack": context.stack_ref,
                        "operation": self.operation,
                        "objects": refs,
                    }
                ),
            ),
            continuation_effect=FrozenMap(
                {
                    **dict(effect),
                    "_choice_actor": context.actor,
                    "_legal_refs": refs,
                    "_stack_label": context.stack_label,
                }
            ),
        )

    def complete(
        self,
        continuation: SemanticChoiceContinuation,
        response: Mapping[str, Any],
        query: SemanticChoiceQuery,
    ) -> SemanticChoiceCompletion:
        effect = continuation.effect
        selected = str(response.get("card") or "")
        legal = {str(value) for value in effect.get("_legal_refs", ())}
        sacrificed = query.object(selected, zones=("battlefield",))
        if (
            selected not in legal
            or sacrificed is None
            or "artifact" not in sacrificed.types
        ):
            raise SemanticChoiceError("Choose a legal artifact to sacrifice")
        actor = str(effect["_choice_actor"])
        target_ref = str(effect.get("card") or "")
        target = query.object(target_ref, zones=("graveyard",))
        return_ref = (
            target.ref
            if target is not None
            and target.owner == actor
            and "artifact" in target.types
            else None
        )
        intents: list[Any] = [
            ZoneMoveIntent(
                actor=actor,
                object_ref=sacrificed.ref,
                expected_zones=("battlefield",),
                destination="graveyard",
                reason=str(effect["_stack_label"]),
                controlled_only=True,
                required_types=("artifact",),
            )
        ]
        if return_ref is not None:
            intents.append(
                ZoneMoveIntent(
                    actor=actor,
                    object_ref=return_ref,
                    expected_zones=("graveyard",),
                    destination="battlefield",
                    reason=str(effect["_stack_label"]),
                    owned_only=True,
                    required_types=("artifact",),
                    new_controller=actor,
                    optional_if_missing=True,
                )
            )
        intents.append(
            RecordChoiceIntent(
                actor=actor,
                event_code="daretti.exchange",
                message=f"{actor} sacrificed {sacrificed.ref} for Daretti.",
                details=FrozenMap(
                    {"sacrificed": sacrificed.ref, "returned": return_ref}
                ),
                importance=2,
                changed_players=(actor,),
            )
        )
        return SemanticChoiceCompletion(intents=tuple(intents))


@dataclass(frozen=True, slots=True)
class TransmuteArtifactChoiceHandler:
    operation: str = "transmute_artifact"
    handler_id: str = "choice.artifact.transmute.v1"
    schema_version: int = 1
    rule_references: tuple[str, ...] = ("CR 608.2c", "CR 701.19")
    capability_dependencies: tuple[str, ...] = ()
    continuation_fields: tuple[str, ...] = (
        "stage",
        "card",
        "difference",
        "sacrificed_mana_value",
        "_choice_actor",
        "_legal_refs",
        "_requirements",
        "_stack_label",
    )
    private_data: tuple[str, ...] = ("searched library",)
    projected_fields: tuple[str, ...] = (
        "prompt",
        "objects",
        "search_cards",
        "cost",
        "legal_actions.choice_schema",
    )
    mutation_path: tuple[str, ...] = (
        "ZoneMoveIntent",
        "PayManaCostIntent",
        "ShuffleLibraryIntent",
    )
    replay_fixture: str = "semantic-choice-transmute-artifact"
    test_modules: tuple[str, ...] = ("tests.test_exact_mishra_closure",)

    @staticmethod
    def _next(effect: Mapping[str, Any], **updates: Any) -> FrozenMap:
        value = dict(effect)
        value.update(updates)
        return FrozenMap(value)

    def prepare(
        self,
        effect: Mapping[str, Any],
        context: SemanticChoiceContext,
    ) -> SemanticChoicePreparation:
        stage = str(effect.get("stage") or "sacrifice")
        if stage == "sacrifice":
            rows = _artifacts(
                context.query,
                context.actor,
                zone="battlefield",
                controlled=True,
            )
            if not rows:
                return SemanticChoicePreparation(
                    request=None,
                    continuation_effect=FrozenMap(effect),
                    auto_continue=AutoContinue(reason="no artifact to sacrifice"),
                )
            refs = tuple(row.ref for row in rows)
            prompt = (
                "Choose exactly one artifact to sacrifice while "
                "Transmute Artifact resolves."
            )
            choice: Any = ObjectChoice(
                field_name="card",
                legal_refs=refs,
                zones=("battlefield",),
                controller_relation="actor",
                predicates=FrozenMap({"types": ["artifact"]}),
            )
            public = {"objects": refs}
        elif stage == "search":
            rows = _artifacts(
                context.query,
                context.actor,
                zone="library",
            )
            refs = tuple(row.ref for row in rows)
            prompt = "Choose an artifact card from your library, or fail to find."
            choice = ObjectChoice(
                field_name="card",
                legal_refs=refs,
                zones=("library",),
                minimum=0,
                maximum=1 if refs else 0,
                optional=True,
                visibility="actor_private",
                owner_relation="actor",
                predicates=FrozenMap({"types": ["artifact"]}),
                schema_extras=FrozenMap({"rules_may_fail_to_find": True}),
            )
            public = {
                "search_cards": [
                    {"id": row.ref, "name": row.printed_name}
                    for row in rows
                ]
            }
        elif stage == "pay":
            card_ref = str(effect.get("card") or "")
            card = context.query.object(card_ref, zones=("library",))
            if card is None or card.owner != context.actor:
                raise SemanticChoiceError(
                    "The Transmute Artifact card left the library"
                )
            difference = max(0, int(effect.get("difference", 0)))
            requirements = {"GENERIC": difference}
            if not context.query.cost_is_affordable(
                context.actor, requirements
            ):
                return SemanticChoicePreparation(
                    request=None,
                    continuation_effect=FrozenMap(effect),
                    preparation_intents=(
                        ZoneMoveIntent(
                            actor=context.actor,
                            object_ref=card.ref,
                            expected_zones=("library",),
                            destination="graveyard",
                            reason="Transmute Artifact payment declined",
                            owned_only=True,
                        ),
                        ShuffleLibraryIntent(
                            actor=context.actor,
                            player=context.actor,
                            reason="Transmute Artifact resolved",
                        ),
                    ),
                    auto_continue=AutoContinue(reason="payment is unavailable"),
                )
            refs = ()
            prompt = (
                f"Pay {difference} generic mana to put {card.ref} "
                "onto the battlefield?"
            )
            choice = ScalarChoice(
                field_name="pay",
                legal_values=(True, False),
            )
            public = {
                "card": {"id": card.ref, "name": card.printed_name},
                "cost": requirements,
            }
        else:
            raise SemanticChoiceError(
                f"Unknown Transmute Artifact stage {stage!r}"
            )
        continuation_effect = {
            **dict(effect),
            "stage": stage,
            "_choice_actor": context.actor,
            "_stack_label": context.stack_label,
        }
        if stage in {"sacrifice", "search"}:
            continuation_effect["_legal_refs"] = refs
        if stage == "pay":
            continuation_effect["_requirements"] = requirements
        return SemanticChoicePreparation(
            request=SemanticChoiceRequest(
                prompt=prompt,
                choice=choice,
                public_context=FrozenMap(
                    {
                        "stack": context.stack_ref,
                        "operation": self.operation,
                        **public,
                    }
                ),
            ),
            continuation_effect=FrozenMap(continuation_effect),
        )

    def complete(
        self,
        continuation: SemanticChoiceContinuation,
        response: Mapping[str, Any],
        query: SemanticChoiceQuery,
    ) -> SemanticChoiceCompletion:
        effect = continuation.effect
        actor = str(effect["_choice_actor"])
        stage = str(effect.get("stage") or "sacrifice")
        legal = {str(value) for value in effect.get("_legal_refs", ())}
        if stage == "sacrifice":
            selected = str(response.get("card") or "")
            row = query.object(selected, zones=("battlefield",))
            if selected not in legal or row is None or "artifact" not in row.types:
                raise SemanticChoiceError("Choose a legal artifact to sacrifice")
            return SemanticChoiceCompletion(
                intents=(
                    ZoneMoveIntent(
                        actor=actor,
                        object_ref=row.ref,
                        expected_zones=("battlefield",),
                        destination="graveyard",
                        reason=str(effect["_stack_label"]),
                        controlled_only=True,
                        required_types=("artifact",),
                    ),
                ),
                prepend_effects=(
                    self._next(
                        effect,
                        stage="search",
                        sacrificed_mana_value=row.mana_value,
                    ),
                ),
            )
        if stage == "search":
            raw = response.get("card")
            selected = None if raw in {None, ""} else str(raw)
            if selected is not None and selected not in legal:
                raise SemanticChoiceError("Selected artifact is not legal")
            if selected is None:
                return SemanticChoiceCompletion(
                    intents=(
                        ShuffleLibraryIntent(
                            actor=actor,
                            player=actor,
                            reason="Transmute Artifact resolved",
                        ),
                    )
                )
            row = query.object(selected, zones=("library",))
            if row is None or row.owner != actor or "artifact" not in row.types:
                raise SemanticChoiceError("The selected artifact is unavailable")
            difference = max(
                0,
                row.mana_value
                - int(effect.get("sacrificed_mana_value", 0)),
            )
            if difference:
                return SemanticChoiceCompletion(
                    prepend_effects=(
                        self._next(
                            effect,
                            stage="pay",
                            card=row.ref,
                            difference=difference,
                        ),
                    )
                )
            return SemanticChoiceCompletion(
                intents=(
                    ZoneMoveIntent(
                        actor=actor,
                        object_ref=row.ref,
                        expected_zones=("library",),
                        destination="battlefield",
                        reason=str(effect["_stack_label"]),
                        owned_only=True,
                        required_types=("artifact",),
                        new_controller=actor,
                    ),
                    ShuffleLibraryIntent(
                        actor=actor,
                        player=actor,
                        reason="Transmute Artifact resolved",
                    ),
                )
            )
        if stage == "pay":
            row = query.object(str(effect.get("card") or ""), zones=("library",))
            if row is None or row.owner != actor:
                raise SemanticChoiceError("The selected artifact is unavailable")
            pay = bool(response.get("pay", False))
            requirements = {
                str(key): int(value)
                for key, value in dict(effect.get("_requirements") or {}).items()
            }
            if pay and not query.cost_is_affordable(actor, requirements):
                raise SemanticChoiceError("The payment is no longer payable")
            intents: list[Any] = []
            if pay:
                intents.append(
                    PayManaCostIntent(
                        actor=actor,
                        player=actor,
                        requirements=FrozenMap(requirements),
                        reason=str(effect["_stack_label"]),
                        event_code="transmute_artifact.pay",
                        message=f"{actor} paid for {row.ref}.",
                        details=FrozenMap(
                            {"card": row.ref, "cost": requirements}
                        ),
                    )
                )
            intents.extend(
                (
                    ZoneMoveIntent(
                        actor=actor,
                        object_ref=row.ref,
                        expected_zones=("library",),
                        destination="battlefield" if pay else "graveyard",
                        reason=str(effect["_stack_label"]),
                        owned_only=True,
                        required_types=("artifact",),
                        new_controller=actor if pay else None,
                    ),
                    ShuffleLibraryIntent(
                        actor=actor,
                        player=actor,
                        reason="Transmute Artifact resolved",
                    ),
                )
            )
            return SemanticChoiceCompletion(intents=tuple(intents))
        raise SemanticChoiceError(f"Unknown Transmute Artifact stage {stage!r}")


@dataclass(frozen=True, slots=True)
class LegacyWarformChoiceHandler:
    operation: str = "choose_warform"
    handler_id: str = "choice.compat.warform.v1"
    schema_version: int = 1
    rule_references: tuple[str, ...] = ("CR 707.2", "CR 603.7")
    capability_dependencies: tuple[str, ...] = ()
    continuation_fields: tuple[str, ...] = (
        "_choice_actor",
        "_legal_refs",
        "_stack_label",
    )
    private_data: tuple[str, ...] = ()
    projected_fields: tuple[str, ...] = (
        "prompt",
        "options",
        "legal_actions.choice_schema.legal_refs",
    )
    mutation_path: tuple[str, ...] = ("CreateTokenIntent",)
    replay_fixture: str = "semantic-choice-warform-compat"
    test_modules: tuple[str, ...] = ("tests.test_end_step_rules",)

    def prepare(
        self,
        effect: Mapping[str, Any],
        context: SemanticChoiceContext,
    ) -> SemanticChoicePreparation:
        rows = tuple(
            row
            for row in _artifacts(
                context.query,
                context.actor,
                zone="battlefield",
                controlled=True,
            )
            if "creature" not in row.types
        )
        if not rows:
            return SemanticChoicePreparation(
                request=None,
                continuation_effect=FrozenMap(effect),
                auto_continue=AutoContinue(reason="no noncreature artifact"),
            )
        refs = tuple(row.ref for row in rows)
        return SemanticChoicePreparation(
            request=SemanticChoiceRequest(
                prompt=(
                    "Choose a noncreature artifact you control for the "
                    "modified token copy."
                ),
                choice=ObjectChoice(
                    field_name="card",
                    legal_refs=refs,
                    zones=("battlefield",),
                    controller_relation="actor",
                    predicates=FrozenMap(
                        {"types": ["artifact"], "excluded_types": ["creature"]}
                    ),
                ),
                public_context=FrozenMap(
                    {
                        "stack": context.stack_ref,
                        "operation": self.operation,
                        "options": refs,
                    }
                ),
            ),
            continuation_effect=FrozenMap(
                {
                    **dict(effect),
                    "_choice_actor": context.actor,
                    "_legal_refs": refs,
                    "_stack_label": context.stack_label,
                }
            ),
        )

    def complete(
        self,
        continuation: SemanticChoiceContinuation,
        response: Mapping[str, Any],
        query: SemanticChoiceQuery,
    ) -> SemanticChoiceCompletion:
        effect = continuation.effect
        selected = str(response.get("card") or "")
        legal = {str(value) for value in effect.get("_legal_refs", ())}
        row = query.object(selected, zones=("battlefield",))
        if (
            selected not in legal
            or row is None
            or "artifact" not in row.types
            or "creature" in row.types
        ):
            raise SemanticChoiceError("Selected artifact is not legal")
        actor = str(effect["_choice_actor"])
        return SemanticChoiceCompletion(
            intents=(
                CreateTokenIntent(
                    actor=actor,
                    controller=actor,
                    name="Mishra's Warform",
                    quantity=1,
                    copy_of=row.ref,
                    characteristics=FrozenMap(
                        {
                            "name": "Mishra's Warform",
                            "type_line": "Artifact Creature — Construct",
                            "power": "4",
                            "toughness": "4",
                            "mana_value": 0,
                        }
                    ),
                    temporary_keywords=("Haste",),
                    sacrifice_on_controller_end_step=True,
                    reason=str(effect["_stack_label"]),
                ),
            )
        )


ARTIFACT_EXCHANGE_CHOICE_HANDLERS = (
    DarettiExchangeChoiceHandler(),
    TransmuteArtifactChoiceHandler(),
    LegacyWarformChoiceHandler(),
)
