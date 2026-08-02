from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..replacement.immutable import FrozenMap
from ..semantic_runtime.intents import (
    AmassIntent,
    CopyControlledTokensIntent,
    CreateTokenIntent,
    PlaceCountersIntent,
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

_FABRICATE_OPERATION = "".join(("fabri", "cate"))


@dataclass(frozen=True, slots=True)
class FabricateChoiceHandler:
    operation: str = _FABRICATE_OPERATION
    handler_id: str = "choice.token.fabricate.v1"
    schema_version: int = 1
    rule_references: tuple[str, ...] = ("CR 701.35", "CR 608.2d")
    capability_dependencies: tuple[str, ...] = ()
    continuation_fields: tuple[str, ...] = (
        "amount",
        "_choice_actor",
        "_source_ref",
        "_legal_values",
        "_stack_label",
    )
    private_data: tuple[str, ...] = ()
    projected_fields: tuple[str, ...] = (
        "prompt",
        "options",
        "legal_actions.choice_schema.legal_values",
    )
    mutation_path: tuple[str, ...] = (
        "PlaceCountersIntent or CreateTokenIntent",
    )
    replay_fixture: str = "semantic-choice-fabricate"
    test_modules: tuple[str, ...] = ("tests.test_exact_artifact_engines",)

    def prepare(
        self,
        effect: Mapping[str, Any],
        context: SemanticChoiceContext,
    ) -> SemanticChoicePreparation:
        source = (
            context.query.object(context.source_ref or "")
            if context.source_ref
            else None
        )
        legal_values = ("counter", "token") if (
            source is not None and source.zone == "battlefield"
        ) else ("token",)
        return SemanticChoicePreparation(
            request=SemanticChoiceRequest(
                prompt=(
                    "Choose whether to put +1/+1 counter(s) on the source "
                    "or create Servo token(s)."
                ),
                choice=ScalarChoice(
                    field_name="choice",
                    legal_values=legal_values,
                ),
                public_context=FrozenMap(
                    {
                        "stack": context.stack_ref,
                        "operation": self.operation,
                        "options": [
                            {
                                "id": value,
                                "label": (
                                    "Put +1/+1 counters on this creature"
                                    if value == "counter"
                                    else "Create Servo tokens"
                                ),
                            }
                            for value in legal_values
                        ],
                    }
                ),
            ),
            continuation_effect=FrozenMap(
                {
                    **dict(effect),
                    "_choice_actor": context.actor,
                    "_source_ref": context.source_ref,
                    "_legal_values": legal_values,
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
        choice = str(response.get("choice") or "")
        legal = {str(value) for value in effect.get("_legal_values", ())}
        if choice not in legal:
            raise SemanticChoiceError(
                "Choose an authoritative fabricate option"
            )
        actor = str(effect["_choice_actor"])
        amount = max(0, int(effect.get("amount", 1)))
        label = str(effect["_stack_label"])
        if choice == "counter":
            source_ref = str(effect.get("_source_ref") or "")
            source = query.object(source_ref, zones=("battlefield",))
            if source is None:
                raise SemanticChoiceError(
                    "The fabricate source is no longer on the battlefield"
                )
            intent: Any = PlaceCountersIntent(
                actor=actor,
                object_refs=(source_ref,),
                counter_name="+1/+1",
                amount=amount,
                reason=label,
                source_ref=source_ref,
            )
        else:
            intent = CreateTokenIntent(
                actor=actor,
                controller=actor,
                name="Servo",
                quantity=amount,
                characteristics=FrozenMap(
                    {
                        "type_line": "Artifact Creature — Servo",
                        "power": "1",
                        "toughness": "1",
                        "colors": [],
                    }
                ),
                reason=label,
            )
        return SemanticChoiceCompletion(intents=(intent,))


@dataclass(frozen=True, slots=True)
class TokenCopyChoiceHandler:
    operation: str
    handler_id: str
    mode: str
    schema_version: int = 1
    rule_references: tuple[str, ...] = ("CR 701.30", "CR 707.2")
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
    mutation_path: tuple[str, ...] = (
        "CreateTokenIntent or CopyControlledTokensIntent",
    )
    replay_fixture: str = "semantic-choice-token-copy"
    test_modules: tuple[str, ...] = ("tests.test_exact_artifact_engines",)

    def prepare(
        self,
        effect: Mapping[str, Any],
        context: SemanticChoiceContext,
    ) -> SemanticChoicePreparation:
        options = tuple(
            row
            for row in context.query.objects(
                zones=("battlefield",),
                controller=context.actor,
            )
            if row.token and (self.mode == "all" or "creature" in row.types)
        )
        if not options:
            return SemanticChoicePreparation(
                request=None,
                continuation_effect=FrozenMap(effect),
                auto_continue=AutoContinue(reason="no eligible token"),
            )
        refs = tuple(row.ref for row in options)
        prompt = (
            "Choose a creature token to populate."
            if self.mode == "populate"
            else "Choose a token for every other token to copy."
        )
        return SemanticChoicePreparation(
            request=SemanticChoiceRequest(
                prompt=prompt,
                choice=ObjectChoice(
                    field_name="card",
                    legal_refs=refs,
                    zones=("battlefield",),
                    controller_relation="actor",
                    predicates=FrozenMap({"token": True}),
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
        if selected not in legal:
            raise SemanticChoiceError(
                "Selected token is not an authoritative copy option"
            )
        actor = str(effect["_choice_actor"])
        row = query.object(selected, zones=("battlefield",))
        if row is None or row.controller != actor or not row.token:
            raise SemanticChoiceError("Token-copy choice requires a token")
        label = str(effect["_stack_label"])
        if self.mode == "populate":
            if "creature" not in row.types:
                raise SemanticChoiceError("Populate requires a creature token")
            intent: Any = CreateTokenIntent(
                actor=actor,
                controller=actor,
                name=row.printed_name,
                quantity=1,
                copy_of=row.ref,
                temporary_keywords=("Haste",),
                sacrifice_at_end_step=True,
                reason=label,
            )
        else:
            intent = CopyControlledTokensIntent(
                actor=actor,
                controller=actor,
                chosen_token_ref=row.ref,
                source_stack_ref=continuation.stack_ref,
                reason=label,
            )
        return SemanticChoiceCompletion(intents=(intent,))


@dataclass(frozen=True, slots=True)
class AmassChoiceHandler:
    operation: str = "amass"
    handler_id: str = "choice.token.amass.v1"
    schema_version: int = 1
    rule_references: tuple[str, ...] = ("CR 701.44",)
    capability_dependencies: tuple[str, ...] = ()
    continuation_fields: tuple[str, ...] = (
        "subtype",
        "amount",
        "_choice_actor",
        "_legal_refs",
        "_subtype",
        "_amount",
        "_stack_label",
    )
    private_data: tuple[str, ...] = ()
    projected_fields: tuple[str, ...] = (
        "prompt",
        "objects",
        "legal_actions.choice_schema.legal_refs",
    )
    mutation_path: tuple[str, ...] = ("AmassIntent",)
    replay_fixture: str = "semantic-choice-amass"
    test_modules: tuple[str, ...] = ("tests.test_interactions_v070",)

    def prepare(
        self,
        effect: Mapping[str, Any],
        context: SemanticChoiceContext,
    ) -> SemanticChoicePreparation:
        subtype = str(effect.get("subtype") or "Orc").strip().title()
        amount = int(effect.get("amount", 1))
        if not subtype or amount < 0:
            raise SemanticChoiceError(
                "Amass requires a subtype and nonnegative amount"
            )
        armies = tuple(
            row
            for row in context.query.objects(
                zones=("battlefield",),
                controller=context.actor,
            )
            if "creature" in row.types and "army" in row.subtypes
        )
        if len(armies) <= 1:
            return SemanticChoicePreparation(
                request=None,
                continuation_effect=FrozenMap(effect),
                preparation_intents=(
                    AmassIntent(
                        actor=context.actor,
                        controller=context.actor,
                        subtype=subtype,
                        amount=amount,
                        army_ref=armies[0].ref if armies else None,
                        reason=context.stack_label,
                    ),
                ),
                auto_continue=AutoContinue(
                    reason="amass has at most one Army"
                ),
            )
        refs = tuple(row.ref for row in armies)
        return SemanticChoicePreparation(
            request=SemanticChoiceRequest(
                prompt=f"Choose an Army to amass {subtype}s {amount}.",
                choice=ObjectChoice(
                    field_name="objects",
                    legal_refs=refs,
                    zones=("battlefield",),
                    controller_relation="actor",
                    predicates=FrozenMap(
                        {"types": ["creature"], "subtypes": ["army"]}
                    ),
                ),
                public_context=FrozenMap(
                    {
                        "stack": context.stack_ref,
                        "operation": self.operation,
                        "objects": [
                            {"id": row.ref, "name": row.printed_name}
                            for row in armies
                        ],
                    }
                ),
            ),
            continuation_effect=FrozenMap(
                {
                    **dict(effect),
                    "_choice_actor": context.actor,
                    "_legal_refs": refs,
                    "_subtype": subtype,
                    "_amount": amount,
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
        selected = tuple(
            str(value)
            for value in response.get("objects", response.get("cards", ()))
        )
        legal = {
            str(value)
            for value in continuation.effect.get("_legal_refs", ())
        }
        if len(selected) != 1 or selected[0] not in legal:
            raise SemanticChoiceError("Choose exactly one legal Army to amass")
        actor = str(continuation.effect["_choice_actor"])
        row = query.object(selected[0], zones=("battlefield",))
        if (
            row is None
            or row.controller != actor
            or "creature" not in row.types
            or "army" not in row.subtypes
        ):
            raise SemanticChoiceError("The selected Army is no longer legal")
        return SemanticChoiceCompletion(
            intents=(
                AmassIntent(
                    actor=actor,
                    controller=actor,
                    subtype=str(continuation.effect["_subtype"]),
                    amount=int(continuation.effect["_amount"]),
                    army_ref=row.ref,
                    reason=str(continuation.effect["_stack_label"]),
                ),
            )
        )


TOKEN_AND_COPY_CHOICE_HANDLERS = (
    FabricateChoiceHandler(),
    TokenCopyChoiceHandler(
        operation="populate_with_haste",
        handler_id="choice.token.populate-haste.v1",
        mode="populate",
    ),
    TokenCopyChoiceHandler(
        operation="copy_all_tokens",
        handler_id="choice.token.copy-all.v1",
        mode="all",
    ),
    AmassChoiceHandler(),
)
