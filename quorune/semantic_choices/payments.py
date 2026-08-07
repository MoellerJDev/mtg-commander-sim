from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..replacement.immutable import FrozenMap
from ..semantic_runtime.intents import (
    CounterStackIntent,
    EliminatePlayersIntent,
    PayManaCostIntent,
    PlaceCountersIntent,
    ZoneMoveIntent,
)
from .context import SemanticChoiceContext, SemanticChoiceQuery
from .model import (
    ScalarChoice,
    SemanticChoiceCompletion,
    SemanticChoiceContinuation,
    SemanticChoiceError,
    SemanticChoicePreparation,
    SemanticChoiceRequest,
)


_MANA_KEYS = ("GENERIC", "W", "U", "B", "R", "G", "C")


def _requirements(value: Mapping[str, Any]) -> dict[str, int]:
    result = {key: int(value.get(key, 0)) for key in _MANA_KEYS}
    if any(amount < 0 for amount in result.values()):
        raise SemanticChoiceError("Payment costs cannot be negative")
    return result


@dataclass(frozen=True, slots=True)
class OptionalPaymentHandler:
    operation: str
    handler_id: str
    mode: str
    prompt: str
    default_cost: FrozenMap
    schema_version: int = 1
    rule_references: tuple[str, ...] = ("CR 117.12", "CR 608.2d")
    capability_dependencies: tuple[str, ...] = ()
    continuation_fields: tuple[str, ...] = (
        "player",
        "cost",
        "source",
        "stack",
        "beneficiary",
        "_choice_actor",
        "_requirements",
        "_source_ref",
        "_stack_label",
    )
    private_data: tuple[str, ...] = ("actor payable mana",)
    projected_fields: tuple[str, ...] = (
        "prompt",
        "cost",
        "payable",
        "legal_actions.choice_schema.legal_values",
    )
    mutation_path: tuple[str, ...] = (
        "PayManaCostIntent",
        "typed decline intent",
    )
    replay_fixture: str = "semantic-choice-optional-payment"
    test_modules: tuple[str, ...] = (
        "tests.test_semantic_choice_characterization",
        "tests.test_exact_zimone_closure",
    )

    def _cost_and_source(
        self,
        effect: Mapping[str, Any],
        context: SemanticChoiceContext,
    ) -> tuple[dict[str, int], str | None, int | None]:
        if self.mode != "cumulative":
            return (
                _requirements(
                    effect.get("cost")
                    if isinstance(effect.get("cost"), Mapping)
                    else self.default_cost
                ),
                None,
                None,
            )
        source_ref = str(effect.get("source") or "")
        source = context.query.object(source_ref, zones=("battlefield",))
        if source is None or source.controller != context.actor:
            raise SemanticChoiceError(
                "The cumulative-upkeep source is no longer controlled"
            )
        per_counter = _requirements(
            effect.get("cost_per_counter")
            if isinstance(effect.get("cost_per_counter"), Mapping)
            else self.default_cost
        )
        age = int(source.counters.get("age", 0)) + 1
        return (
            {key: amount * age for key, amount in per_counter.items()},
            source.ref,
            age,
        )

    def prepare(
        self,
        effect: Mapping[str, Any],
        context: SemanticChoiceContext,
    ) -> SemanticChoicePreparation:
        requirements, source_ref, age = self._cost_and_source(effect, context)
        payable = context.query.cost_is_affordable(
            context.actor,
            requirements,
        )
        continuation_effect = FrozenMap(
            {
                **dict(effect),
                "_choice_actor": context.actor,
                "_requirements": requirements,
                "_source_ref": source_ref,
                "_stack_label": context.stack_label,
            }
        )
        public: dict[str, Any] = {
            "stack": context.stack_ref,
            "operation": self.operation,
            "cost": requirements,
            "payable": payable,
        }
        if self.mode == "counter":
            public["target_stack"] = effect.get("stack")
        elif self.mode == "remora":
            public["beneficiary"] = effect.get("beneficiary")
        elif self.mode == "cumulative":
            source = context.query.object(source_ref or "")
            public["age_counters"] = age
            prompt = (
                f"Pay cumulative upkeep {requirements} or sacrifice "
                f"{source.printed_name if source else source_ref}."
            )
        else:
            prompt = self.prompt
        preparation_intents = ()
        if self.mode == "cumulative":
            preparation_intents = (
                PlaceCountersIntent(
                    actor=context.actor,
                    object_refs=(str(source_ref),),
                    counter_name="age",
                    amount=1,
                    reason=context.stack_label,
                    source_ref=context.source_ref,
                ),
            )
        return SemanticChoicePreparation(
            request=SemanticChoiceRequest(
                prompt=prompt if self.mode == "cumulative" else self.prompt,
                choice=ScalarChoice(
                    field_name="pay",
                    legal_values=(True, False) if payable else (False,),
                ),
                public_context=FrozenMap(public),
            ),
            continuation_effect=continuation_effect,
            preparation_intents=preparation_intents,
        )

    def complete(
        self,
        continuation: SemanticChoiceContinuation,
        response: Mapping[str, Any],
        query: SemanticChoiceQuery,
    ) -> SemanticChoiceCompletion:
        effect = continuation.effect
        actor = str(effect["_choice_actor"])
        requirements = _requirements(effect.get("_requirements", FrozenMap()))
        pay = bool(response.get("pay", False))
        if pay and not query.cost_is_affordable(actor, requirements):
            raise SemanticChoiceError(
                "The optional payment is no longer payable"
            )
        label = str(effect["_stack_label"])
        if pay:
            event_code = {
                "counter": "counter.unless.paid",
                "cumulative": "cumulative_upkeep.paid",
                "remora": "mystic_remora.paid",
                "pact": "pact.paid",
            }[self.mode]
            source_ref = str(effect.get("_source_ref") or "") or None
            message = {
                "counter": (
                    f"{actor} paid to prevent {effect.get('stack')} from being countered."
                ),
                "cumulative": f"{actor} paid cumulative upkeep for {source_ref}.",
                "remora": f"{actor} paid for Mystic Remora.",
                "pact": f"{actor} paid the delayed Pact cost.",
            }[self.mode]
            details: dict[str, Any] = {"cost": requirements}
            if self.mode == "counter":
                details["stack"] = effect.get("stack")
            elif self.mode == "cumulative":
                source = query.object(source_ref or "", zones=("battlefield",))
                if source is None or source.controller != actor:
                    raise SemanticChoiceError(
                        "The cumulative-upkeep source is no longer controlled"
                    )
                details.update(
                    {
                        "source": source_ref,
                        "age_counters": source.counters.get("age", 0),
                    }
                )
            else:
                details["stack"] = continuation.stack_ref
            return SemanticChoiceCompletion(
                intents=(
                    PayManaCostIntent(
                        actor=actor,
                        player=actor,
                        requirements=FrozenMap(requirements),
                        reason=label,
                        event_code=event_code,
                        message=message,
                        details=FrozenMap(details),
                        changed_object_ref=source_ref,
                    ),
                )
            )
        if self.mode == "counter":
            target = str(effect.get("stack") or "")
            if query.stack_object(target) is None:
                return SemanticChoiceCompletion()
            return SemanticChoiceCompletion(
                intents=(
                    CounterStackIntent(
                        actor=actor,
                        stack_ref=target,
                        reason=label,
                        countered_by=actor,
                    ),
                )
            )
        if self.mode == "cumulative":
            source_ref = str(effect.get("_source_ref") or "")
            source = query.object(source_ref, zones=("battlefield",))
            if source is None or source.controller != actor:
                raise SemanticChoiceError(
                    "The cumulative-upkeep source is no longer controlled"
                )
            return SemanticChoiceCompletion(
                intents=(
                    ZoneMoveIntent(
                        actor=actor,
                        object_ref=source_ref,
                        expected_zones=("battlefield",),
                        destination="graveyard",
                        reason="cumulative upkeep not paid",
                        controlled_only=True,
                    ),
                )
            )
        if self.mode == "pact":
            return SemanticChoiceCompletion(
                intents=(
                    EliminatePlayersIntent(
                        actor=actor,
                        players=(actor,),
                        reason="failed to pay Pact of Negation",
                    ),
                )
            )
        beneficiary = str(effect.get("beneficiary") or "")
        if beneficiary not in query.active_seats:
            return SemanticChoiceCompletion()
        return SemanticChoiceCompletion(
            prepend_effects=(
                FrozenMap(
                    {
                        "op": "choose_option",
                        "player": beneficiary,
                        "prompt": "Draw a card with Mystic Remora?",
                        "options": [
                            {"id": "draw", "label": "Draw a card"},
                            {"id": "decline", "label": "Do not draw"},
                        ],
                        "then_by_choice": {
                            "draw": [
                                {
                                    "op": "draw",
                                    "player": beneficiary,
                                    "count": 1,
                                    "private": True,
                                }
                            ],
                            "decline": [],
                        },
                    }
                ),
            )
        )


PAYMENT_CHOICE_HANDLERS = (
    OptionalPaymentHandler(
        operation="counter_unless_pay",
        handler_id="choice.payment.counter-unless.v1",
        mode="counter",
        prompt="Pay the stated cost to prevent the spell from being countered.",
        default_cost=FrozenMap(),
    ),
    OptionalPaymentHandler(
        operation="cumulative_upkeep",
        handler_id="choice.payment.cumulative-upkeep.v1",
        mode="cumulative",
        prompt="Pay cumulative upkeep or sacrifice the permanent.",
        default_cost=FrozenMap({"GENERIC": 1}),
    ),
    OptionalPaymentHandler(
        operation="remora_tax",
        handler_id="choice.payment.remora-tax.v1",
        mode="remora",
        prompt=(
            "Pay {4} to prevent Mystic Remora's controller from drawing a card."
        ),
        default_cost=FrozenMap({"GENERIC": 4}),
    ),
    OptionalPaymentHandler(
        operation="pay_or_lose",
        handler_id="choice.payment-pay-or-lose.v1",
        mode="pact",
        prompt="Pay the delayed Pact cost or lose the game.",
        default_cost=FrozenMap(),
    ),
)
