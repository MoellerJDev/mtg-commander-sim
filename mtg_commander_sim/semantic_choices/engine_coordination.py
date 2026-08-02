from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..errors import GameRuleError
from ..model import StackItem
from ..object_query import object_query_result
from ..replacement.immutable import thaw_value
from ..semantic_runtime import IntentPlan, execute_intent_plan
from ..targets import TargetGroup, available_modes, target_plan
from ..util import unique_preserving_order
from .context import (
    ChoiceObjectView,
    ChoiceStackView,
    SemanticChoiceContext,
    SnapshotSemanticChoiceQuery,
)
from .defaults import default_semantic_choice_registry
from .model import (
    SemanticChoiceContinuation,
    SemanticChoiceError,
    SemanticChoiceFrame,
)


class SemanticChoiceCoordinationMixin:
    def _semantic_choice_object_rows(
        self,
        actor: str,
    ) -> tuple[ChoiceObjectView, ...]:
        public_zones = {
            "battlefield", "graveyard", "exile", "command", "stack"
        }
        rows: list[ChoiceObjectView] = []
        for card in self.state.cards.values():
            if card.zone not in public_zones and card.owner != actor:
                continue
            effective = self._effective_card_data(card)
            types, subtypes, supertypes = self._type_parts(
                str(effective.get("type_line") or "")
            )
            rows.append(
                object_query_result(
                    card,
                    effective,
                    type_parts=(types, subtypes, supertypes),
                    known_to_actor=(
                        actor in card.known_to or card.zone in public_zones
                    ),
                    attached_to_ref=(
                        self.state.cards[card.attached_to].ref
                        if card.attached_to in self.state.cards
                        else None
                    ),
                )
            )
        return tuple(rows)

    def _semantic_choice_stack_rows(self) -> tuple[ChoiceStackView, ...]:
        return tuple(
            ChoiceStackView(
                ref=item.ref,
                controller=item.controller,
                label=item.label,
                semantic_key=item.semantic_key,
                targets=tuple(item.targets),
                modes=tuple(item.modes),
                target_groups=dict(item.context.get("target_groups") or {}),
            )
            for item in self.state.stack
        )

    def _semantic_choice_candidates(
        self,
        actor: str,
        effect: Mapping[str, Any],
        source_ref: str | None,
    ) -> tuple[str, ...]:
        if str(effect.get("op") or "") != "choose_objects":
            return ()
        selector = dict(effect.get("selector") or {})
        selector.setdefault("min", int(effect.get("minimum", 1)))
        selector.setdefault(
            "max", int(effect.get("maximum", selector["min"]))
        )
        group = TargetGroup.from_mapping(selector, default_id="choice")
        return tuple(
            str(row["ref"])
            for row in self._target_candidate_rows(actor, group)
            if self._target_row_matches(
                actor,
                group,
                row,
                source_ref=source_ref,
                as_target=False,
            )
        )

    def _semantic_choice_target_facts(
        self,
        actor: str,
        effect: Mapping[str, Any],
        response: Mapping[str, Any] | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        target_schemas: dict[str, Any] = {}
        validated_targets: dict[str, Any] = {}
        operation = str(effect.get("op") or "")
        if operation not in {"copy_stack_item", "retarget_stack_item"}:
            return target_schemas, validated_targets
        target_ref = str(
            effect.get("_target_stack_ref") or effect.get("stack") or ""
        )
        target_item = next(
            (item for item in self.state.stack if item.ref == target_ref),
            None,
        )
        if target_item is None:
            return target_schemas, validated_targets
        validation_actor = str(
            effect.get("_validation_actor")
            or (
                actor
                if operation == "copy_stack_item"
                else target_item.controller
            )
        )
        raw_schema = effect.get("_target_schema")
        if not isinstance(raw_schema, Mapping):
            raw_schema = self._stack_target_schema(
                target_item,
                self.semantics.get(target_item.semantic_key),
            )
        if not isinstance(raw_schema, Mapping) or not target_item.targets:
            return target_schemas, validated_targets
        public_schema: Mapping[str, Any] | None = None
        if operation == "retarget_stack_item" and available_modes(raw_schema):
            plan = target_plan(
                raw_schema, target_item.modes, require_modes=True
            )
            candidates = self._target_candidate_map(
                target_item.controller,
                plan,
                source_ref=self._stack_source_ref(target_item),
            )
            if self._target_plan_feasible(plan, candidates):
                public_schema = {
                    "groups": [
                        group.public_dict(candidates[group.group_id])
                        for group in plan.groups
                    ],
                    "legal_refs": unique_preserving_order(
                        ref
                        for group in plan.groups
                        for ref in candidates[group.group_id]
                    ),
                }
        else:
            public_schema = self._public_target_schema(
                validation_actor,
                raw_schema,
                source_ref=self._stack_source_ref(target_item),
            )
        if public_schema is None:
            return target_schemas, validated_targets
        key = f"{validation_actor}:{target_ref}"
        target_schemas[key] = {
            "authoritative": dict(raw_schema),
            "public": dict(public_schema),
        }
        submitted = (response or {}).get("targets")
        if submitted is not None:
            selected, grouped = self._validate_semantic_targets(
                validation_actor,
                self.semantics.get(target_item.semantic_key),
                self._normalize_target_submission(submitted),
                modes=list(target_item.modes),
                source_ref=self._stack_source_ref(target_item),
                target_schema=dict(raw_schema),
            )
            validated_targets[key] = {
                "targets": selected,
                "groups": grouped,
            }
        return target_schemas, validated_targets

    def _semantic_choice_canonical_names(
        self,
        response: Mapping[str, Any] | None,
    ) -> dict[str, str]:
        canonical: dict[str, str] = {}
        submitted = {
            str(value).strip()
            for key, value in (response or {}).items()
            if key == "card_name" and str(value).strip()
        }
        for value in submitted:
            try:
                canonical[value.casefold()] = self.card_db.lookup(value).name
            except KeyError:
                continue
        return canonical

    def _semantic_choice_affordable_costs(
        self,
        actor: str,
        effect: Mapping[str, Any],
        object_rows: tuple[ChoiceObjectView, ...],
    ) -> frozenset[str]:
        cost_value: Mapping[str, Any] | None = None
        if isinstance(effect.get("_requirements"), Mapping):
            cost_value = effect["_requirements"]
        elif isinstance(effect.get("cost"), Mapping):
            cost_value = effect["cost"]
        elif str(effect.get("op") or "") == "remora_tax":
            cost_value = {"GENERIC": 4}
        elif (
            str(effect.get("op") or "") == "transmute_artifact"
            and str(effect.get("stage") or "") == "pay"
        ):
            cost_value = {
                "GENERIC": max(0, int(effect.get("difference", 0)))
            }
        elif str(effect.get("op") or "") == "cumulative_upkeep":
            per_counter = self._mana_vector(
                effect.get("cost_per_counter") or {"GENERIC": 1}
            )
            source = next(
                (
                    row
                    for row in object_rows
                    if row.ref == str(effect.get("source") or "")
                ),
                None,
            )
            if source is not None:
                age = int(source.counters.get("age", 0)) + 1
                cost_value = {
                    key: int(value) * age
                    for key, value in per_counter.items()
                }
        if cost_value is None:
            return frozenset()
        requirements = self._mana_vector(cost_value)
        if not self._cost_is_affordable(actor, requirements):
            return frozenset()
        return frozenset(
            {
                SnapshotSemanticChoiceQuery._cost_key(actor, requirements)
            }
        )

    def _semantic_choice_query(
        self,
        actor: str,
        *,
        response: Mapping[str, Any] | None = None,
        effect: Mapping[str, Any] | None = None,
        source_ref: str | None = None,
    ) -> SnapshotSemanticChoiceQuery:
        """Materialize only actor-visible, immutable choice facts."""

        choice_effect = effect or {}
        object_rows = self._semantic_choice_object_rows(actor)
        target_schemas, validated_targets = (
            self._semantic_choice_target_facts(
                actor, choice_effect, response
            )
        )
        return SnapshotSemanticChoiceQuery(
            seat_order=tuple(self.seats),
            active_order=tuple(self.active_seats),
            object_rows=object_rows,
            stack_rows=self._semantic_choice_stack_rows(),
            life_by_seat={
                seat: self.state.players[seat].life for seat in self.seats
            },
            counters_by_seat={
                seat: {
                    "poison": self.state.players[seat].poison,
                    "energy": self.state.players[seat].energy,
                }
                for seat in self.seats
            },
            libraries_by_seat={
                actor: [
                    self.state.cards[object_id].ref
                    for object_id in self.state.players[actor].zones["library"]
                ]
            },
            mana_by_seat={
                actor: dict(self.state.players[actor].mana_pool)
            },
            affordable_costs=self._semantic_choice_affordable_costs(
                actor, choice_effect, object_rows
            ),
            canonical_names=self._semantic_choice_canonical_names(response),
            target_schemas=target_schemas,
            validated_targets=validated_targets,
            drawn_this_turn_by_seat={
                actor: tuple(
                    str(entry.get("object"))
                    for entry in self.state.players[actor].draw_history
                    if entry.get("turn_sequence") == self.state.turn_sequence
                )
            },
            materialized_choice_candidates=self._semantic_choice_candidates(
                actor, choice_effect, source_ref
            ),
            current_turn_sequence=self.state.turn_sequence,
        )
    def _semantic_choice_context(
        self,
        item: StackItem,
        actor: str,
        effect: Mapping[str, Any],
    ) -> SemanticChoiceContext:
        source_id = item.source_object_id or item.card_object_id or ""
        source = self.state.cards.get(source_id)
        program = self.semantics.get(item.semantic_key)
        return SemanticChoiceContext(
            actor=actor,
            stack_ref=item.ref,
            stack_controller=item.controller,
            stack_label=item.label,
            source_ref=source.ref if source is not None else None,
            card_ref=(
                self.state.cards[item.card_object_id].ref
                if item.card_object_id in self.state.cards
                else None
            ),
            semantic_program_id=item.semantic_key,
            semantic_program_version=program.version if program else None,
            query=self._semantic_choice_query(
                actor,
                effect=effect,
                source_ref=source.ref if source is not None else None,
            ),
        )

    def _begin_registered_semantic_choice(
        self,
        *,
        item: StackItem,
        effect: Mapping[str, Any],
        remaining: Sequence[Mapping[str, Any]],
        destination: str | None,
        note: str,
        instruction_pointer: int,
    ) -> None:
        registry = default_semantic_choice_registry()
        handler = registry.handler_for_operation(str(effect.get("op") or ""))
        seat = str(effect.get("player") or item.controller)
        try:
            preparation = handler.prepare(
                effect,
                self._semantic_choice_context(item, seat, effect),
            )
        except SemanticChoiceError as exc:
            raise GameRuleError(str(exc)) from exc
        for intent in preparation.preparation_intents:
            execute_intent_plan(
                self,
                IntentPlan(
                    operation=handler.operation,
                    handler_id=handler.handler_id,
                    intents=(intent,),
                ),
            )
        if preparation.auto_continue is not None:
            self._continue_resolution(
                stack_ref=item.ref,
                effects=[
                    *(
                        dict(value)
                        for value in preparation.auto_continue.prepend_effects
                    ),
                    *(dict(value) for value in remaining),
                ],
                destination=destination,
                note=note,
                instruction_pointer=instruction_pointer + 1,
            )
            return
        assert preparation.request is not None
        continuation = SemanticChoiceContinuation(
            handler_id=handler.handler_id,
            handler_version=handler.schema_version,
            stack_ref=item.ref,
            effect=preparation.continuation_effect,
            remaining=tuple(dict(value) for value in remaining),
            destination=destination,
            note=note,
            semantic_frame=SemanticChoiceFrame(
                semantic_program_id=str(item.semantic_key or ""),
                semantic_program_version=(
                    self.semantics.get(item.semantic_key).version
                    if self.semantics.get(item.semantic_key)
                    else None
                ),
                stack_object=item.ref,
                instruction_pointer=instruction_pointer,
                controller=item.controller,
            ),
        )
        decision = self.permissions.issue(
            kind="semantic.choice",
            role="pilot",
            actors=[seat],
            allowed_actions=["choose"],
            payload_by_actor={seat: preparation.request.payload()},
            continuation=continuation.to_dict(),
        )
        decision.continuation = continuation.with_pending_choice(
            decision.decision_id
        ).to_dict()

    def _complete_registered_semantic_choice(self, decision: Any) -> None:
        seat = decision.actors[0]
        response = decision.responses[seat]
        registry = default_semantic_choice_registry()
        try:
            handler, continuation = registry.decode_continuation(
                decision.continuation
            )
        except SemanticChoiceError as exc:
            raise GameRuleError(str(exc)) from exc
        item = next(
            (
                candidate
                for candidate in self.state.stack
                if candidate.ref == continuation.stack_ref
            ),
            None,
        )
        if item is None:
            raise GameRuleError(
                "The semantic choice's stack object no longer exists"
            )
        self._validate_semantic_frame(
            continuation.semantic_frame.to_dict(),
            item,
        )
        try:
            completion = handler.complete(
                continuation,
                response,
                self._semantic_choice_query(
                    seat,
                    response=response,
                    effect=continuation.effect,
                    source_ref=(
                        self.state.cards[
                            item.source_object_id
                            or item.card_object_id
                            or ""
                        ].ref
                        if (
                            item.source_object_id
                            or item.card_object_id
                            or ""
                        )
                        in self.state.cards
                        else None
                    ),
                ),
            )
        except SemanticChoiceError as exc:
            raise GameRuleError(str(exc)) from exc
        for intent in completion.intents:
            execute_intent_plan(
                self,
                IntentPlan(
                    operation=handler.operation,
                    handler_id=handler.handler_id,
                    intents=(intent,),
                ),
            )
        if item not in self.state.stack:
            return
        remaining = [
            *(dict(value) for value in completion.prepend_effects),
            *(dict(value) for value in continuation.remaining),
        ]
        if completion.repeat_effect is not None:
            remaining.insert(0, dict(completion.repeat_effect))
        self._continue_resolution(
            stack_ref=continuation.stack_ref,
            effects=remaining,
            destination=continuation.destination,
            note=continuation.note,
            instruction_pointer=(
                continuation.semantic_frame.instruction_pointer + 1
            ),
        )

    def _begin_semantic_choice(
        self,
        *,
        item: StackItem,
        effect: Mapping[str, Any],
        remaining: Sequence[Mapping[str, Any]],
        destination: str | None,
        note: str,
        instruction_pointer: int = 0,
    ) -> None:
        operation = str(effect.get("op") or "")
        if operation not in default_semantic_choice_registry().operations:
            raise GameRuleError(
                f"Unregistered semantic choice operation {operation!r}"
            )
        self._begin_registered_semantic_choice(
            item=item,
            effect=effect,
            remaining=remaining,
            destination=destination,
            note=note,
            instruction_pointer=instruction_pointer,
        )

    def _complete_semantic_choice(self, decision: Any) -> None:
        continuation = decision.continuation
        effect = continuation.get("effect")
        operation = (
            str(effect.get("op") or "")
            if isinstance(effect, Mapping)
            else ""
        )
        if operation not in default_semantic_choice_registry().operations:
            raise GameRuleError(
                f"Unregistered semantic choice continuation {operation!r}"
            )
        self._complete_registered_semantic_choice(decision)

