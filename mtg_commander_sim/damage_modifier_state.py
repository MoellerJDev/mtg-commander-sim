from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class DamageModifierError(ValueError):
    """A durable prevention or redirection value is malformed or stale."""


class PreventionMode(str, Enum):
    AMOUNT = "amount"
    NEXT_INSTANCE = "next_instance"
    ALL = "all"


class DamageModifierDuration(str, Enum):
    UNTIL_END_OF_TURN = "until_end_of_turn"
    UNTIL_USED = "until_used"


def _exact_fields(
    value: Mapping[str, Any], expected: set[str], *, label: str
) -> None:
    actual = set(value)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    details: list[str] = []
    if missing:
        details.append("missing " + ", ".join(missing))
    if unknown:
        details.append("unknown " + ", ".join(unknown))
    raise DamageModifierError(f"{label} fields: {'; '.join(details)}")


def _strings(value: Any, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise DamageModifierError(f"{label} must be an array")
    result = tuple(sorted({str(item) for item in value if str(item)}))
    if len(result) != len(value):
        raise DamageModifierError(
            f"{label} must contain unique nonempty strings"
        )
    return result


@dataclass(frozen=True, slots=True)
class DamageSubject:
    ref: str
    kind: str
    controller: str
    object_id: str | None = None
    logical_object_id: str | None = None
    owner: str | None = None

    def __post_init__(self) -> None:
        ref = str(self.ref or "")
        kind = str(self.kind or "")
        controller = str(self.controller or "")
        object_id = str(self.object_id or "") or None
        logical_id = str(self.logical_object_id or "") or None
        owner = str(self.owner or "") or None
        if not ref or not controller or kind not in {
            "any",
            "player",
            "permanent",
        }:
            raise DamageModifierError(
                "A damage subject requires a player or permanent identity"
            )
        if kind in {"any", "player"}:
            if any(value is not None for value in (object_id, logical_id, owner)):
                raise DamageModifierError(
                    "A nonpermanent damage subject cannot carry object identity"
                )
        elif not all((object_id, logical_id, owner)):
            raise DamageModifierError(
                "A permanent damage subject requires complete object identity"
            )
        object.__setattr__(self, "ref", ref)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "controller", controller)
        object.__setattr__(self, "object_id", object_id)
        object.__setattr__(self, "logical_object_id", logical_id)
        object.__setattr__(self, "owner", owner)

    def event_conditions(self) -> dict[str, Any]:
        result: dict[str, Any] = {"amount": {"gt": 0}}
        if self.kind == "any":
            return result
        result["target"] = {"eq": self.ref}
        result["target_kind"] = {"eq": self.kind}
        if self.kind == "permanent":
            result["target_object_id"] = {"eq": self.object_id}
            result["target_logical_object_id"] = {
                "eq": self.logical_object_id
            }
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "kind": self.kind,
            "controller": self.controller,
            "object_id": self.object_id,
            "logical_object_id": self.logical_object_id,
            "owner": self.owner,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DamageSubject":
        _exact_fields(
            value,
            {
                "ref",
                "kind",
                "controller",
                "object_id",
                "logical_object_id",
                "owner",
            },
            label="Damage subject",
        )
        return cls(
            ref=str(value["ref"] or ""),
            kind=str(value["kind"] or ""),
            controller=str(value["controller"] or ""),
            object_id=(
                str(value["object_id"])
                if value["object_id"] is not None
                else None
            ),
            logical_object_id=(
                str(value["logical_object_id"])
                if value["logical_object_id"] is not None
                else None
            ),
            owner=(str(value["owner"]) if value["owner"] is not None else None),
        )


@dataclass(frozen=True, slots=True)
class ChosenDamageSource:
    ref: str
    object_id: str
    required_colors: tuple[str, ...] = ()
    required_types: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ref = str(self.ref or "")
        object_id = str(self.object_id or "")
        if not ref or not object_id:
            raise DamageModifierError(
                "A chosen damage source requires stable physical identity"
            )
        object.__setattr__(self, "ref", ref)
        object.__setattr__(self, "object_id", object_id)
        object.__setattr__(
            self,
            "required_colors",
            tuple(sorted({str(value).upper() for value in self.required_colors})),
        )
        object.__setattr__(
            self,
            "required_types",
            tuple(sorted({str(value).casefold() for value in self.required_types})),
        )

    def event_conditions(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "source_object_id": {"eq": self.object_id}
        }
        if self.required_colors:
            result["source_colors"] = {
                "contains_all": list(self.required_colors)
            }
        if self.required_types:
            result["source_types"] = {
                "contains_all": list(self.required_types)
            }
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "object_id": self.object_id,
            "required_colors": list(self.required_colors),
            "required_types": list(self.required_types),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ChosenDamageSource":
        _exact_fields(
            value,
            {"ref", "object_id", "required_colors", "required_types"},
            label="Chosen damage source",
        )
        return cls(
            ref=str(value["ref"] or ""),
            object_id=str(value["object_id"] or ""),
            required_colors=_strings(
                value["required_colors"], label="Required source colors"
            ),
            required_types=_strings(
                value["required_types"], label="Required source types"
            ),
        )


@dataclass(frozen=True, slots=True)
class DamagePreventionShield:
    shield_id: str
    source_id: str
    controller: str
    subject: DamageSubject
    mode: PreventionMode
    remaining: int | None
    duration: DamageModifierDuration
    created_turn_sequence: int
    chosen_source: ChosenDamageSource | None = None
    label: str = ""

    def __post_init__(self) -> None:
        if not all((self.shield_id, self.source_id, self.controller)):
            raise DamageModifierError(
                "A prevention shield requires stable identity and controller"
            )
        if not isinstance(self.subject, DamageSubject):
            raise DamageModifierError("A prevention shield requires a subject")
        if not isinstance(self.mode, PreventionMode) or not isinstance(
            self.duration, DamageModifierDuration
        ):
            raise DamageModifierError(
                "A prevention shield requires typed mode and duration"
            )
        if self.mode == PreventionMode.AMOUNT:
            if type(self.remaining) is not int or self.remaining < 1:
                raise DamageModifierError(
                    "An amount shield requires a positive remaining amount"
                )
        elif self.remaining is not None:
            raise DamageModifierError(
                "Only an amount shield may carry a remaining amount"
            )
        if (
            type(self.created_turn_sequence) is not int
            or self.created_turn_sequence < 0
        ):
            raise DamageModifierError(
                "A prevention shield requires a nonnegative creation turn"
            )
        if self.chosen_source is not None and not isinstance(
            self.chosen_source, ChosenDamageSource
        ):
            raise DamageModifierError(
                "A prevention shield chosen source must be typed"
            )

    @property
    def effect_id(self) -> str:
        return f"prevention.shield:{self.shield_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "shield_id": self.shield_id,
            "source_id": self.source_id,
            "controller": self.controller,
            "subject": self.subject.to_dict(),
            "mode": self.mode.value,
            "remaining": self.remaining,
            "duration": self.duration.value,
            "created_turn_sequence": self.created_turn_sequence,
            "chosen_source": (
                self.chosen_source.to_dict()
                if self.chosen_source is not None
                else None
            ),
            "label": self.label,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "DamagePreventionShield":
        _exact_fields(
            value,
            {
                "shield_id",
                "source_id",
                "controller",
                "subject",
                "mode",
                "remaining",
                "duration",
                "created_turn_sequence",
                "chosen_source",
                "label",
            },
            label="Prevention shield",
        )
        subject = value["subject"]
        chosen = value["chosen_source"]
        if not isinstance(subject, Mapping) or (
            chosen is not None and not isinstance(chosen, Mapping)
        ):
            raise DamageModifierError(
                "Prevention shield nested values are malformed"
            )
        try:
            mode = PreventionMode(str(value["mode"]))
            duration = DamageModifierDuration(str(value["duration"]))
        except ValueError as exc:
            raise DamageModifierError(
                "Prevention shield mode or duration is unsupported"
            ) from exc
        return cls(
            shield_id=str(value["shield_id"] or ""),
            source_id=str(value["source_id"] or ""),
            controller=str(value["controller"] or ""),
            subject=DamageSubject.from_dict(subject),
            mode=mode,
            remaining=value["remaining"],
            duration=duration,
            created_turn_sequence=value["created_turn_sequence"],
            chosen_source=(
                ChosenDamageSource.from_dict(chosen)
                if isinstance(chosen, Mapping)
                else None
            ),
            label=str(value["label"] or ""),
        )


@dataclass(frozen=True, slots=True)
class DamageRedirectionEffect:
    redirection_id: str
    source_id: str
    controller: str
    subject: DamageSubject
    destination: DamageSubject
    duration: DamageModifierDuration
    created_turn_sequence: int
    chosen_source: ChosenDamageSource | None = None
    consume_on_application: bool = True
    label: str = ""

    def __post_init__(self) -> None:
        if not all((self.redirection_id, self.source_id, self.controller)):
            raise DamageModifierError(
                "A redirection effect requires stable identity and controller"
            )
        if not isinstance(self.subject, DamageSubject) or not isinstance(
            self.destination, DamageSubject
        ):
            raise DamageModifierError(
                "A redirection effect requires typed subjects"
            )
        if self.destination.kind == "any":
            raise DamageModifierError(
                "A damage redirection requires a concrete destination"
            )
        if not isinstance(self.duration, DamageModifierDuration):
            raise DamageModifierError(
                "A redirection effect requires a typed duration"
            )
        if type(self.consume_on_application) is not bool:
            raise DamageModifierError(
                "Redirection consumption policy must be a boolean"
            )
        if (
            type(self.created_turn_sequence) is not int
            or self.created_turn_sequence < 0
        ):
            raise DamageModifierError(
                "A redirection effect requires a nonnegative creation turn"
            )

    @property
    def effect_id(self) -> str:
        return f"damage.redirection:{self.redirection_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "redirection_id": self.redirection_id,
            "source_id": self.source_id,
            "controller": self.controller,
            "subject": self.subject.to_dict(),
            "destination": self.destination.to_dict(),
            "duration": self.duration.value,
            "created_turn_sequence": self.created_turn_sequence,
            "chosen_source": (
                self.chosen_source.to_dict()
                if self.chosen_source is not None
                else None
            ),
            "consume_on_application": self.consume_on_application,
            "label": self.label,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "DamageRedirectionEffect":
        _exact_fields(
            value,
            {
                "redirection_id",
                "source_id",
                "controller",
                "subject",
                "destination",
                "duration",
                "created_turn_sequence",
                "chosen_source",
                "consume_on_application",
                "label",
            },
            label="Damage redirection",
        )
        subject = value["subject"]
        destination = value["destination"]
        chosen = value["chosen_source"]
        if (
            not isinstance(subject, Mapping)
            or not isinstance(destination, Mapping)
            or (chosen is not None and not isinstance(chosen, Mapping))
        ):
            raise DamageModifierError(
                "Damage redirection nested values are malformed"
            )
        try:
            duration = DamageModifierDuration(str(value["duration"]))
        except ValueError as exc:
            raise DamageModifierError(
                "Damage redirection duration is unsupported"
            ) from exc
        return cls(
            redirection_id=str(value["redirection_id"] or ""),
            source_id=str(value["source_id"] or ""),
            controller=str(value["controller"] or ""),
            subject=DamageSubject.from_dict(subject),
            destination=DamageSubject.from_dict(destination),
            duration=duration,
            created_turn_sequence=value["created_turn_sequence"],
            chosen_source=(
                ChosenDamageSource.from_dict(chosen)
                if isinstance(chosen, Mapping)
                else None
            ),
            consume_on_application=value["consume_on_application"],
            label=str(value["label"] or ""),
        )
