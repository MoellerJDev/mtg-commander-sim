from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..replacement.immutable import FrozenMap
from ..semantic_runtime.intents import (
    MoveLibraryCardsToBottomIntent,
    ReorderLibraryTopIntent,
    RevealLibraryCardsIntent,
)
from .context import SemanticChoiceContext, SemanticChoiceQuery
from .model import (
    AutoContinue,
    ObjectChoice,
    OrderingChoice,
    SemanticChoiceCompletion,
    SemanticChoiceContinuation,
    SemanticChoiceError,
    SemanticChoicePreparation,
    SemanticChoiceRequest,
)


@dataclass(frozen=True, slots=True)
class LibraryOrderingHandler:
    operation: str
    handler_id: str
    mode: str
    schema_version: int = 1
    rule_references: tuple[str, ...] = ("CR 701.18", "CR 701.24")
    capability_dependencies: tuple[str, ...] = ()
    continuation_fields: tuple[str, ...] = (
        "count",
        "player",
        "_choice_actor",
        "_looked_refs",
        "_stack_label",
    )
    private_data: tuple[str, ...] = ("actor library top",)
    projected_fields: tuple[str, ...] = (
        "prompt",
        "objects or cards",
        "legal_actions.choice_schema.legal_refs",
    )
    mutation_path: tuple[str, ...] = (
        "RevealLibraryCardsIntent",
        "MoveLibraryCardsToBottomIntent or ReorderLibraryTopIntent",
    )
    replay_fixture: str = "semantic-choice-library-ordering"
    test_modules: tuple[str, ...] = (
        "tests.test_semantic_choice_characterization",
        "tests.test_exact_zimone_closure",
    )

    def prepare(
        self,
        effect: Mapping[str, Any],
        context: SemanticChoiceContext,
    ) -> SemanticChoicePreparation:
        count = max(0, int(effect.get("count", 1)))
        refs = context.query.library_refs(context.actor, top_first=True)[:count]
        if not refs:
            return SemanticChoicePreparation(
                request=None,
                continuation_effect=FrozenMap(effect),
                auto_continue=AutoContinue(reason="no library cards to inspect"),
            )
        rows = []
        for ref in refs:
            row = context.query.object(ref, zones=("library",))
            if row is None:
                raise SemanticChoiceError(
                    "A looked-at card is absent from the actor query"
                )
            rows.append(row)
        continuation_effect = FrozenMap(
            {
                **dict(effect),
                "_choice_actor": context.actor,
                "_looked_refs": refs,
                "_stack_label": context.stack_label,
            }
        )
        if self.mode == "scry":
            choice = ObjectChoice(
                field_name="cards",
                legal_refs=refs,
                zones=("library",),
                minimum=0,
                maximum=len(refs),
                optional=True,
                visibility="actor_private",
                owner_relation="actor",
                schema_extras=FrozenMap({"destination": "library_bottom"}),
            )
            prompt = (
                "Choose which looked-at cards to put on the bottom of your library."
            )
            public_key = "objects"
        else:
            choice = OrderingChoice(
                field_name="cards",
                legal_refs=refs,
                visibility="actor_private",
                schema_extras=FrozenMap({"order": "top_to_bottom"}),
            )
            prompt = "Put the looked-at cards back in top-to-bottom order."
            public_key = "cards"
        return SemanticChoicePreparation(
            request=SemanticChoiceRequest(
                prompt=prompt,
                choice=choice,
                public_context=FrozenMap(
                    {
                        "stack": context.stack_ref,
                        "operation": self.operation,
                        public_key: [
                            {"id": row.ref, "name": row.printed_name}
                            for row in rows
                        ],
                    }
                ),
            ),
            continuation_effect=continuation_effect,
            preparation_intents=(
                RevealLibraryCardsIntent(
                    actor=context.stack_controller,
                    player=context.actor,
                    viewer=context.actor,
                    refs_top_first=refs,
                    reason=context.stack_label,
                ),
            ),
        )

    def complete(
        self,
        continuation: SemanticChoiceContinuation,
        response: Mapping[str, Any],
        query: SemanticChoiceQuery,
    ) -> SemanticChoiceCompletion:
        expected = tuple(
            str(value)
            for value in continuation.effect.get("_looked_refs", ())
        )
        actor = str(continuation.effect["_choice_actor"])
        if self.mode == "scry":
            selected = tuple(str(value) for value in response.get("cards", ()))
            if len(selected) != len(set(selected)) or any(
                value not in expected for value in selected
            ):
                raise SemanticChoiceError(
                    "Scry bottom choices must be distinct looked-at cards"
                )
            return SemanticChoiceCompletion(
                intents=(
                    MoveLibraryCardsToBottomIntent(
                        actor=actor,
                        player=actor,
                        refs=selected,
                        looked_count=len(expected),
                        reason=str(continuation.effect["_stack_label"]),
                    ),
                )
            )
        selected = tuple(
            str(value)
            for value in response.get("cards", response.get("order", ()))
        )
        if len(selected) != len(set(selected)) or sorted(selected) != sorted(
            expected
        ):
            raise SemanticChoiceError(
                "Top-card order must contain every looked-at card exactly once"
            )
        return SemanticChoiceCompletion(
            intents=(
                ReorderLibraryTopIntent(
                    actor=actor,
                    player=actor,
                    viewer=actor,
                    refs_top_first=selected,
                    reason=str(continuation.effect["_stack_label"]),
                ),
            )
        )


ORDERING_CHOICE_HANDLERS = (
    LibraryOrderingHandler(
        operation="scry",
        handler_id="choice.ordering.scry.v1",
        mode="scry",
    ),
    LibraryOrderingHandler(
        operation="look_reorder_top",
        handler_id="choice.ordering.library-top.v1",
        mode="reorder",
    ),
)
