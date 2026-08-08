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
    AutoContinue,
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


def _strict_cumulative_requirements(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        raise SemanticChoiceError(
            "Cumulative upkeep requires a fixed mana cost per age counter"
        )
    unknown = sorted(set(value) - set(_MANA_KEYS))
    if unknown:
        raise SemanticChoiceError(
            "Cumulative upkeep cost has unknown mana fields: "
            + ", ".join(str(field) for field in unknown)
        )
    if any(type(amount) is not int or amount < 0 for amount in value.values()):
        raise SemanticChoiceError(
            "Cumulative upkeep mana amounts must be nonnegative integers"
        )
    result = {key: int(value.get(key, 0)) for key in _MANA_KEYS}
    if not any(result.values()):
        raise SemanticChoiceError(
            "Cumulative upkeep fixed mana cost must be positive"
        )
    return result


def _current_cumulative_source(
    query: SemanticChoiceQuery,
    source_ref: str,
    logical_object_id: str | None,
) -> Any | None:
    source = query.object(source_ref, zones=("battlefield",))
    if source is None or source.phased_out:
        return None
    if logical_object_id and source.logical_object_id != logical_object_id:
        return None
    return source


@dataclass(frozen=True, slots=True)
class OptionalPaymentHandler:
    operation: str
    handler_id: str
    mode: str
    prompt: str
    default_cost: FrozenMap
    schema_version: int = 1
    rule_references: tuple[str, ...] = ("CR 118.12", "CR 608.2d")
    capability_dependencies: tuple[str, ...] = ()
    continuation_fields: tuple[str, ...] = (
        "player",
        "cost",
        "source",
        "stack",
        "beneficiary",
        "stage",
        "_choice_actor",
        "_requirements",
        "_source_ref",
        "_source_logical_object_id",
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
        source = _current_cumulative_source(
            context.query,
            source_ref,
            context.source_logical_object_id,
        )
        if source is None:
            raise SemanticChoiceError(
                "The cumulative-upkeep source condition is no longer true"
            )
        per_counter = _strict_cumulative_requirements(
            effect.get("cost_per_counter")
        )
        age = int(source.counters.get("age", 0))
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
        if self.mode == "cumulative":
            allowed = {"op", "player", "source", "cost_per_counter", "stage"}
            unknown = sorted(set(effect) - allowed)
            required = {"op", "player", "source", "cost_per_counter"}
            missing = sorted(required - set(effect))
            if missing or unknown:
                details = []
                if missing:
                    details.append("missing " + ", ".join(missing))
                if unknown:
                    details.append("unknown " + ", ".join(unknown))
                raise SemanticChoiceError(
                    "Malformed cumulative upkeep effect: " + "; ".join(details)
                )
            stage = effect.get("stage")
            if stage not in {None, "pay"}:
                raise SemanticChoiceError("Unknown cumulative upkeep stage")
            per_counter = _strict_cumulative_requirements(
                effect.get("cost_per_counter")
            )
            source_ref = str(effect.get("source") or "")
            source = _current_cumulative_source(
                context.query,
                source_ref,
                context.source_logical_object_id,
            )
            if source is None:
                return SemanticChoicePreparation(
                    request=None,
                    continuation_effect=FrozenMap(effect),
                    auto_continue=AutoContinue(
                        reason=(
                            "cumulative-upkeep intervening condition is false"
                        )
                    ),
                )
            if stage is None:
                pay_effect = FrozenMap({**dict(effect), "stage": "pay"})
                return SemanticChoicePreparation(
                    request=None,
                    continuation_effect=FrozenMap(effect),
                    preparation_intents=(
                        PlaceCountersIntent(
                            actor=source.controller,
                            object_refs=(source_ref,),
                            counter_name="age",
                            amount=1,
                            reason=context.stack_label,
                            source_ref=context.source_ref,
                        ),
                    ),
                    auto_continue=AutoContinue(
                        reason="age counter placement committed",
                        prepend_effects=(pay_effect,),
                    ),
                )
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
                "_source_logical_object_id": (
                    context.source_logical_object_id
                ),
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
            preparation_intents=(),
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
                expected_logical = str(
                    effect.get("_source_logical_object_id") or ""
                )
                source = _current_cumulative_source(
                    query,
                    source_ref or "",
                    expected_logical,
                )
                if source is None:
                    raise SemanticChoiceError(
                        "The cumulative-upkeep source condition changed during its choice"
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
            expected_logical = str(
                effect.get("_source_logical_object_id") or ""
            )
            source = _current_cumulative_source(
                query,
                source_ref,
                expected_logical,
            )
            if source is None or source.controller != actor:
                return SemanticChoiceCompletion()
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
        capability_dependencies=(
            "counter.producer.cumulative_upkeep_fixed_mana",
        ),
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
