from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Protocol, Sequence

from .damage import DamageError, recipient_snapshot, source_snapshot
from .damage_modifier_state import (
    ChosenDamageSource,
    DamageModifierDuration,
    DamageModifierError,
    DamagePreventionShield,
    DamageSubject,
    GainLifePreventionAftermath,
    PlaceCountersPreventionAftermath,
    PreventionMode,
)
from .util import stable_json


class DamagePreventionCreationError(ValueError):
    """A prevention resource could not be planned or committed exactly."""


class DamagePreventionCreationHost(Protocol):
    state: Any

    def _effective_card_data(self, card: Any) -> Mapping[str, Any]: ...

    def _type_parts(
        self, type_line: str
    ) -> tuple[set[str], set[str], set[str]]: ...


@dataclass(frozen=True, slots=True)
class PreventionSubjectAllocation:
    subject_ref: str
    amount: int | None

    def __post_init__(self) -> None:
        if not str(self.subject_ref or ""):
            raise DamagePreventionCreationError(
                "Prevention allocations require a subject"
            )
        if self.amount is not None and (
            type(self.amount) is not int or self.amount < 1
        ):
            raise DamagePreventionCreationError(
                "Prevention allocations require a positive integer amount"
            )


@dataclass(frozen=True, slots=True)
class GainLifeAftermathRequest:
    player: str
    per_prevented: int = 0
    fixed_amount: int = 0

    def __post_init__(self) -> None:
        # Reuse the persistent model's closed arithmetic validation.
        GainLifePreventionAftermath(
            player=self.player,
            per_prevented=self.per_prevented,
            fixed_amount=self.fixed_amount,
        )


@dataclass(frozen=True, slots=True)
class PlaceCountersAftermathRequest:
    counter_name: str
    placing_player: str
    per_prevented: int = 0
    fixed_amount: int = 0
    subject_ref: str | None = None

    def __post_init__(self) -> None:
        if not " ".join(str(self.counter_name).casefold().split()):
            raise DamagePreventionCreationError(
                "Counter aftermath requires a counter name"
            )
        if not str(self.placing_player or ""):
            raise DamagePreventionCreationError(
                "Counter aftermath requires a placing player"
            )
        if self.subject_ref is not None and not str(self.subject_ref):
            raise DamagePreventionCreationError(
                "Counter aftermath subject references cannot be empty"
            )
        if (
            type(self.per_prevented) is not int
            or self.per_prevented < 0
            or type(self.fixed_amount) is not int
            or self.fixed_amount < 0
            or not (self.per_prevented or self.fixed_amount)
        ):
            raise DamagePreventionCreationError(
                "Counter aftermath requires a positive fixed or scaled amount"
            )


PreventionAftermathRequest = (
    GainLifeAftermathRequest | PlaceCountersAftermathRequest
)


@dataclass(frozen=True, slots=True)
class PreventionShieldCreationRequest:
    source_id: str
    controller: str
    mode: PreventionMode
    duration: DamageModifierDuration
    subjects: tuple[PreventionSubjectAllocation, ...]
    chosen_source_ref: str | None = None
    required_source_colors: tuple[str, ...] = ()
    allowed_source_colors: tuple[str, ...] = ()
    required_source_types: tuple[str, ...] = ()
    required_source_subtypes: tuple[str, ...] = ()
    required_source_supertypes: tuple[str, ...] = ()
    required_source_keywords: tuple[str, ...] = ()
    label: str = ""
    aftermath: tuple[PreventionAftermathRequest, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.source_id or "") or not str(self.controller or ""):
            raise DamagePreventionCreationError(
                "Prevention creation requires source and controller identity"
            )
        if not isinstance(self.mode, PreventionMode) or not isinstance(
            self.duration, DamageModifierDuration
        ):
            raise DamagePreventionCreationError(
                "Prevention creation requires typed mode and duration"
            )
        subjects = tuple(self.subjects)
        if not subjects or any(
            not isinstance(value, PreventionSubjectAllocation)
            for value in subjects
        ):
            raise DamagePreventionCreationError(
                "Prevention creation requires typed subject allocations"
            )
        refs = tuple(value.subject_ref for value in subjects)
        if len(refs) != len(set(refs)):
            raise DamagePreventionCreationError(
                "A prevention creation cannot repeat a subject"
            )
        if self.mode == PreventionMode.AMOUNT:
            if any(value.amount is None for value in subjects):
                raise DamagePreventionCreationError(
                    "Amount shields require an amount for every subject"
                )
        elif any(value.amount is not None for value in subjects):
            raise DamagePreventionCreationError(
                "Only amount shields accept subject allocations"
            )
        object.__setattr__(self, "subjects", subjects)
        object.__setattr__(
            self,
            "required_source_colors",
            tuple(
                sorted(
                    {
                        str(value).upper()
                        for value in self.required_source_colors
                        if str(value)
                    }
                )
            ),
        )
        object.__setattr__(
            self,
            "allowed_source_colors",
            tuple(
                sorted(
                    {
                        str(value).upper()
                        for value in self.allowed_source_colors
                        if str(value)
                    }
                )
            ),
        )
        if self.required_source_colors and self.allowed_source_colors:
            raise DamagePreventionCreationError(
                "Source colors cannot require both all and any modes"
            )
        aftermath = tuple(self.aftermath)
        if any(
            not isinstance(
                value,
                (GainLifeAftermathRequest, PlaceCountersAftermathRequest),
            )
            for value in aftermath
        ):
            raise DamagePreventionCreationError(
                "Prevention aftermath requests must be typed"
            )
        object.__setattr__(self, "aftermath", aftermath)
        object.__setattr__(
            self,
            "required_source_types",
            tuple(
                sorted(
                    {
                        str(value).casefold()
                        for value in self.required_source_types
                        if str(value)
                    }
                )
            ),
        )
        for field_name in (
            "required_source_subtypes",
            "required_source_supertypes",
            "required_source_keywords",
        ):
            object.__setattr__(
                self,
                field_name,
                tuple(
                    sorted(
                        {
                            str(value).casefold()
                            for value in getattr(self, field_name)
                            if str(value)
                        }
                    )
                ),
            )


@dataclass(frozen=True, slots=True)
class DamagePreventionCreationPlan:
    state_fingerprint: str
    shields: tuple[DamagePreventionShield, ...]


def _damage_subject(host: DamagePreventionCreationHost, ref: str, actor: str) -> DamageSubject:
    if ref == "*":
        return DamageSubject(ref="*", kind="any", controller=actor)
    snapshot = recipient_snapshot(host, ref, actor=actor)
    return DamageSubject(
        ref=snapshot.ref,
        kind=snapshot.kind,
        controller=snapshot.controller,
        object_id=snapshot.object_id,
        logical_object_id=snapshot.logical_object_id,
        owner=snapshot.owner,
    )


def pin_chosen_damage_source(
    host: DamagePreventionCreationHost,
    *,
    source_ref: str | None,
    controller: str,
    required_colors: Sequence[str] = (),
    allowed_colors: Sequence[str] = (),
    required_types: Sequence[str] = (),
    required_subtypes: Sequence[str] = (),
    required_supertypes: Sequence[str] = (),
    required_keywords: Sequence[str] = (),
) -> ChosenDamageSource | None:
    """Pin one legal source choice to physical identity and current LKI."""

    ref = source_ref
    if ref is None:
        return None
    normalized_colors = tuple(
        sorted({str(value).upper() for value in required_colors if str(value)})
    )
    normalized_allowed_colors = tuple(
        sorted({str(value).upper() for value in allowed_colors if str(value)})
    )
    normalized_types = tuple(
        sorted(
            {str(value).casefold() for value in required_types if str(value)}
        )
    )
    normalized_subtypes = tuple(
        sorted({str(value).casefold() for value in required_subtypes if str(value)})
    )
    normalized_supertypes = tuple(
        sorted(
            {str(value).casefold() for value in required_supertypes if str(value)}
        )
    )
    normalized_keywords = tuple(
        sorted({str(value).casefold() for value in required_keywords if str(value)})
    )
    snapshot = source_snapshot(host, ref, controller=controller)
    if snapshot.object_id.startswith("unrepresented:"):
        raise DamagePreventionCreationError(
            "A chosen damage source requires authoritative physical identity"
        )
    card = host.state.cards.get(snapshot.object_id)
    if card is None:
        raise DamagePreventionCreationError(
            "The chosen damage source is no longer represented"
        )
    data = host._effective_card_data(card)
    types, subtypes, supertypes = host._type_parts(
        str(data.get("type_line") or "")
    )
    colors = tuple(str(value).upper() for value in data.get("colors", ()))
    keywords = tuple(str(value).casefold() for value in data.get("keywords", ()))
    if (
        not set(normalized_colors).issubset(colors)
        or (
            normalized_allowed_colors
            and not set(normalized_allowed_colors).intersection(colors)
        )
        or not set(normalized_types).issubset(types)
        or not set(normalized_subtypes).issubset(subtypes)
        or not set(normalized_supertypes).issubset(supertypes)
        or not set(normalized_keywords).issubset(keywords)
    ):
        raise DamagePreventionCreationError(
            "The chosen damage source no longer has the required characteristics"
        )
    identity_keys = [snapshot.identity_key]
    permanent_types = {
        "artifact",
        "battle",
        "creature",
        "enchantment",
        "planeswalker",
    }
    if snapshot.zone == "stack" and permanent_types.intersection(types):
        identity_keys.append(
            f"{snapshot.logical_object_id}|battlefield"
        )
    return ChosenDamageSource(
        ref=snapshot.ref,
        object_id=snapshot.object_id,
        required_colors=normalized_colors,
        allowed_colors=normalized_allowed_colors,
        required_types=normalized_types,
        required_subtypes=normalized_subtypes,
        required_supertypes=normalized_supertypes,
        required_keywords=normalized_keywords,
        snapshot_version=2,
        logical_object_id=snapshot.logical_object_id,
        oracle_id=snapshot.oracle_id,
        printed_name=str(card.printed_name),
        controller=snapshot.controller,
        owner=snapshot.owner,
        zone=str(card.zone),
        types=tuple(types),
        subtypes=tuple(subtypes),
        supertypes=tuple(supertypes),
        colors=colors,
        keywords=keywords,
        identity_keys=tuple(identity_keys),
    )


def _state_fingerprint(
    host: DamagePreventionCreationHost,
    subjects: Sequence[DamageSubject],
) -> str:
    return stable_json(
        {
            "existing": [
                shield.to_dict()
                for shield in host.state.damage_prevention_shields
            ],
            "subjects": [subject.to_dict() for subject in subjects],
        }
    )


def _shield_ids(
    host: DamagePreventionCreationHost,
    request: PreventionShieldCreationRequest,
    subjects: Sequence[DamageSubject],
) -> tuple[str, ...]:
    seed = stable_json(
        {
            "revision": int(host.state.revision),
            "event_sequence": int(host.state.event_sequence),
            "source": request.source_id,
            "controller": request.controller,
            "mode": request.mode.value,
            "duration": request.duration.value,
            "subjects": [subject.to_dict() for subject in subjects],
            "amounts": [allocation.amount for allocation in request.subjects],
            "chosen_source": request.chosen_source_ref,
            "source_colors": list(request.required_source_colors),
            "source_colors_any": list(request.allowed_source_colors),
            "source_types": list(request.required_source_types),
            "source_subtypes": list(request.required_source_subtypes),
            "source_supertypes": list(request.required_source_supertypes),
            "source_keywords": list(request.required_source_keywords),
            "aftermath": [
                (
                    {
                        "kind": "gain_life",
                        "player": value.player,
                        "per_prevented": value.per_prevented,
                        "fixed_amount": value.fixed_amount,
                    }
                    if isinstance(value, GainLifeAftermathRequest)
                    else {
                        "kind": "place_counters",
                        "subject": value.subject_ref,
                        "counter_name": value.counter_name,
                        "placing_player": value.placing_player,
                        "per_prevented": value.per_prevented,
                        "fixed_amount": value.fixed_amount,
                    }
                )
                for value in request.aftermath
            ],
            "existing": [
                shield.shield_id
                for shield in host.state.damage_prevention_shields
            ],
        }
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return tuple(f"PS-{digest}-{index + 1}" for index in range(len(subjects)))


def _aftermath_for_subject(
    host: DamagePreventionCreationHost,
    request: PreventionShieldCreationRequest,
    subject: DamageSubject,
) -> tuple[GainLifePreventionAftermath | PlaceCountersPreventionAftermath, ...]:
    result: list[
        GainLifePreventionAftermath | PlaceCountersPreventionAftermath
    ] = []
    for value in request.aftermath:
        if isinstance(value, GainLifeAftermathRequest):
            result.append(
                GainLifePreventionAftermath(
                    player=value.player,
                    per_prevented=value.per_prevented,
                    fixed_amount=value.fixed_amount,
                )
            )
            continue
        target = (
            subject
            if value.subject_ref is None
            else _damage_subject(host, value.subject_ref, request.controller)
        )
        result.append(
            PlaceCountersPreventionAftermath(
                subject=target,
                counter_name=value.counter_name,
                placing_player=value.placing_player,
                per_prevented=value.per_prevented,
                fixed_amount=value.fixed_amount,
            )
        )
    return tuple(result)


def plan_prevention_shield_creation(
    host: DamagePreventionCreationHost,
    request: PreventionShieldCreationRequest,
) -> DamagePreventionCreationPlan:
    """Resolve subjects and source LKI without mutating authoritative state."""

    if request.controller not in host.state.active_seats():
        raise DamagePreventionCreationError(
            "The prevention effect controller is not active"
        )
    try:
        subjects = tuple(
            _damage_subject(host, allocation.subject_ref, request.controller)
            for allocation in request.subjects
        )
        chosen = pin_chosen_damage_source(
            host,
            source_ref=request.chosen_source_ref,
            controller=request.controller,
            required_colors=request.required_source_colors,
            allowed_colors=request.allowed_source_colors,
            required_types=request.required_source_types,
            required_subtypes=request.required_source_subtypes,
            required_supertypes=request.required_source_supertypes,
            required_keywords=request.required_source_keywords,
        )
        ids = _shield_ids(host, request, subjects)
        shields = tuple(
            DamagePreventionShield(
                shield_id=shield_id,
                source_id=request.source_id,
                controller=request.controller,
                subject=subject,
                mode=request.mode,
                remaining=allocation.amount,
                duration=request.duration,
                created_turn_sequence=int(host.state.turn_sequence),
                chosen_source=chosen,
                label=request.label,
                aftermath=_aftermath_for_subject(host, request, subject),
            )
            for shield_id, subject, allocation in zip(
                ids, subjects, request.subjects, strict=True
            )
        )
    except (DamageError, DamageModifierError) as exc:
        raise DamagePreventionCreationError(str(exc)) from exc
    return DamagePreventionCreationPlan(
        state_fingerprint=_state_fingerprint(host, subjects),
        shields=shields,
    )


def validate_prevention_shield_creation(
    host: DamagePreventionCreationHost,
    plan: DamagePreventionCreationPlan,
) -> None:
    if not isinstance(plan, DamagePreventionCreationPlan) or not plan.shields:
        raise DamagePreventionCreationError(
            "Prevention commits require a nonempty typed plan"
        )
    subjects = tuple(shield.subject for shield in plan.shields)
    if plan.state_fingerprint != _state_fingerprint(host, subjects):
        raise DamagePreventionCreationError(
            "Prevention creation subject identity or state is stale"
        )
    current_ids = {
        shield.shield_id for shield in host.state.damage_prevention_shields
    }
    planned_ids = tuple(shield.shield_id for shield in plan.shields)
    if len(planned_ids) != len(set(planned_ids)) or current_ids.intersection(
        planned_ids
    ):
        raise DamagePreventionCreationError(
            "Prevention shield identity collision"
        )
    for subject in subjects:
        if subject.kind != "permanent":
            continue
        card = host.state.cards.get(str(subject.object_id or ""))
        if (
            card is None
            or card.zone != "battlefield"
            or card.logical_object_id != subject.logical_object_id
        ):
            raise DamagePreventionCreationError(
                "Prevention creation subject changed object identity"
            )


def commit_prevention_shield_creation(
    host: DamagePreventionCreationHost,
    plan: DamagePreventionCreationPlan,
) -> tuple[DamagePreventionShield, ...]:
    validate_prevention_shield_creation(host, plan)
    host.state.damage_prevention_shields.extend(plan.shields)
    return plan.shields


__all__ = [
    "DamagePreventionCreationError",
    "DamagePreventionCreationPlan",
    "GainLifeAftermathRequest",
    "PlaceCountersAftermathRequest",
    "PreventionShieldCreationRequest",
    "PreventionSubjectAllocation",
    "commit_prevention_shield_creation",
    "plan_prevention_shield_creation",
    "pin_chosen_damage_source",
    "validate_prevention_shield_creation",
]
