from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..replacement.immutable import FrozenMap
from ..semantic_runtime.intents import (
    LifeChangeIntent,
    RecordZoneMoveIntent,
    ZoneMoveIntent,
)
from .context import SemanticChoiceContext, SemanticChoiceQuery
from .model import (
    AutoContinue,
    ObjectChoice,
    SemanticChoiceCompletion,
    SemanticChoiceContinuation,
    SemanticChoiceError,
    SemanticChoicePreparation,
    SemanticChoiceRequest,
)


@dataclass(frozen=True, slots=True)
class PutCardFromHandHandler:
    operation: str
    handler_id: str
    required_type: str
    prompt: str
    event_code: str
    schema_version: int = 1
    rule_references: tuple[str, ...] = ("CR 400.7", "CR 608.2d")
    capability_dependencies: tuple[str, ...] = ()
    continuation_fields: tuple[str, ...] = (
        "player",
        "cave_life",
        "_choice_actor",
        "_legal_refs",
        "_stack_label",
    )
    private_data: tuple[str, ...] = ("actor hand",)
    projected_fields: tuple[str, ...] = (
        "prompt",
        "objects",
        "legal_actions.choice_schema.legal_refs",
    )
    mutation_path: tuple[str, ...] = (
        "ZoneMoveIntent",
        "CommanderEngine.move_object_intent",
    )
    replay_fixture: str = "semantic-choice-put-from-hand"
    test_modules: tuple[str, ...] = (
        "tests.test_semantic_choice_characterization",
        "tests.test_exact_zimone_closure",
    )

    def prepare(
        self,
        effect: Mapping[str, Any],
        context: SemanticChoiceContext,
    ) -> SemanticChoicePreparation:
        options = tuple(
            row
            for row in context.query.objects(
                zones=("hand",),
                owner=context.actor,
            )
            if self.required_type in row.types
        )
        if not options:
            return SemanticChoicePreparation(
                request=None,
                continuation_effect=FrozenMap(effect),
                auto_continue=AutoContinue(
                    reason=f"no {self.required_type} card in hand"
                ),
            )
        legal_refs = tuple(row.ref for row in options)
        continuation_effect = FrozenMap(
            {
                **dict(effect),
                "_choice_actor": context.actor,
                "_legal_refs": legal_refs,
                "_stack_label": context.stack_label,
            }
        )
        return SemanticChoicePreparation(
            request=SemanticChoiceRequest(
                prompt=str(effect.get("prompt") or self.prompt),
                choice=ObjectChoice(
                    field_name="card",
                    legal_refs=legal_refs,
                    zones=("hand",),
                    minimum=0,
                    maximum=1,
                    optional=True,
                    visibility="actor_private",
                    owner_relation="actor",
                    predicates=FrozenMap({"types": [self.required_type]}),
                ),
                public_context=FrozenMap(
                    {
                        "stack": context.stack_ref,
                        "operation": self.operation,
                        "objects": [
                            {"id": row.ref, "name": row.printed_name}
                            for row in options
                        ],
                    }
                ),
            ),
            continuation_effect=continuation_effect,
        )

    def complete(
        self,
        continuation: SemanticChoiceContinuation,
        response: Mapping[str, Any],
        query: SemanticChoiceQuery,
    ) -> SemanticChoiceCompletion:
        selected = str(response.get("card") or "")
        legal = {
            str(value)
            for value in continuation.effect.get("_legal_refs", ())
        }
        if selected and selected not in legal:
            raise SemanticChoiceError(
                f"Selected card is not an authoritative {self.required_type} option"
            )
        if not selected:
            return SemanticChoiceCompletion()
        actor = str(continuation.effect["_choice_actor"])
        row = query.object(selected, zones=("hand",))
        if row is None or row.owner != actor or self.required_type not in row.types:
            raise SemanticChoiceError(
                f"Selected object is no longer a {self.required_type} card in hand"
            )
        label = str(continuation.effect["_stack_label"])
        move = ZoneMoveIntent(
            actor=actor,
            object_ref=selected,
            expected_zones=("hand",),
            destination="battlefield",
            reason=label,
            required_types=(self.required_type,),
            owned_only=True,
            new_controller=actor,
            tapped_policy=(
                "land_entry" if self.required_type == "land" else "preserve"
            ),
        )
        intents: list[Any] = [move]
        cave_life = int(continuation.effect.get("cave_life", 0))
        if self.required_type == "land" and "cave" in row.subtypes and cave_life:
            intents.append(
                LifeChangeIntent(
                    actor=actor,
                    player=actor,
                    amount=cave_life,
                    reason=label,
                )
            )
        message = (
            f"{actor} put {selected} onto the battlefield."
            if self.required_type == "land"
            else f"{actor} put {selected} onto the battlefield from hand."
        )
        details: dict[str, Any] = {
            "card": selected,
            "source": continuation.stack_ref,
        }
        if self.required_type == "land":
            details["include_tapped_state"] = True
        intents.append(
            RecordZoneMoveIntent(
                actor=actor,
                object_ref=selected,
                event_code=self.event_code,
                message=message,
                details=FrozenMap(details),
                changed_player=actor,
            )
        )
        return SemanticChoiceCompletion(intents=tuple(intents))


OBJECT_SELECTION_HANDLERS = (
    PutCardFromHandHandler(
        operation="put_land_from_hand",
        handler_id="choice.object.put-land-from-hand.v1",
        required_type="land",
        prompt="You may put a land card from your hand onto the battlefield.",
        event_code="land.put",
    ),
    PutCardFromHandHandler(
        operation="put_artifact_from_hand",
        handler_id="choice.object.put-artifact-from-hand.v1",
        required_type="artifact",
        prompt=(
            "You may put an artifact card from your hand onto the battlefield."
        ),
        event_code="artifact.put",
    ),
)
