from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, TypeAlias


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
    # Version zero is the additive Game Record v3 compatibility shape used by
    # historical checkpoints.  New source choices pin the complete supported
    # CR 615.1 snapshot at effect creation with version one.
    snapshot_version: int = 0
    logical_object_id: str | None = None
    oracle_id: str | None = None
    printed_name: str | None = None
    controller: str | None = None
    owner: str | None = None
    zone: str | None = None
    types: tuple[str, ...] = ()
    subtypes: tuple[str, ...] = ()
    supertypes: tuple[str, ...] = ()
    colors: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()

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
        if self.snapshot_version not in {0, 1}:
            raise DamageModifierError(
                "A chosen damage source has an unsupported snapshot version"
            )
        optional_strings = (
            "logical_object_id",
            "oracle_id",
            "printed_name",
            "controller",
            "owner",
            "zone",
        )
        for field_name in optional_strings:
            raw = getattr(self, field_name)
            value = str(raw) if raw is not None else None
            if value == "":
                raise DamageModifierError(
                    "Chosen source snapshot strings cannot be empty"
                )
            object.__setattr__(self, field_name, value)
        for field_name in ("types", "subtypes", "supertypes", "keywords"):
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
        object.__setattr__(
            self,
            "colors",
            tuple(sorted({str(value).upper() for value in self.colors if str(value)})),
        )
        if self.snapshot_version == 0:
            if any(
                getattr(self, field_name) is not None
                for field_name in optional_strings
            ) or any(
                getattr(self, field_name)
                for field_name in (
                    "types",
                    "subtypes",
                    "supertypes",
                    "colors",
                    "keywords",
                )
            ):
                raise DamageModifierError(
                    "Legacy chosen sources cannot carry versioned snapshot facts"
                )
        elif not all(
            (
                self.logical_object_id,
                self.oracle_id,
                self.printed_name,
                self.controller,
                self.owner,
                self.zone,
            )
        ):
            raise DamageModifierError(
                "A versioned chosen source requires a complete identity snapshot"
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
        result = {
            "ref": self.ref,
            "object_id": self.object_id,
            "required_colors": list(self.required_colors),
            "required_types": list(self.required_types),
        }
        if self.snapshot_version:
            result.update(
                {
                    "snapshot_version": self.snapshot_version,
                    "logical_object_id": self.logical_object_id,
                    "oracle_id": self.oracle_id,
                    "printed_name": self.printed_name,
                    "controller": self.controller,
                    "owner": self.owner,
                    "zone": self.zone,
                    "types": list(self.types),
                    "subtypes": list(self.subtypes),
                    "supertypes": list(self.supertypes),
                    "colors": list(self.colors),
                    "keywords": list(self.keywords),
                }
            )
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ChosenDamageSource":
        legacy = {"ref", "object_id", "required_colors", "required_types"}
        versioned = legacy | {
            "snapshot_version",
            "logical_object_id",
            "oracle_id",
            "printed_name",
            "controller",
            "owner",
            "zone",
            "types",
            "subtypes",
            "supertypes",
            "colors",
            "keywords",
        }
        _exact_fields(
            value,
            versioned if "snapshot_version" in value else legacy,
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
            snapshot_version=int(value.get("snapshot_version", 0)),
            logical_object_id=value.get("logical_object_id"),
            oracle_id=value.get("oracle_id"),
            printed_name=value.get("printed_name"),
            controller=value.get("controller"),
            owner=value.get("owner"),
            zone=value.get("zone"),
            types=_strings(value.get("types", ()), label="Source snapshot types"),
            subtypes=_strings(
                value.get("subtypes", ()), label="Source snapshot subtypes"
            ),
            supertypes=_strings(
                value.get("supertypes", ()), label="Source snapshot supertypes"
            ),
            colors=_strings(value.get("colors", ()), label="Source snapshot colors"),
            keywords=_strings(
                value.get("keywords", ()), label="Source snapshot keywords"
            ),
        )


@dataclass(frozen=True, slots=True)
class GainLifePreventionAftermath:
    player: str
    per_prevented: int = 0
    fixed_amount: int = 0
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not str(self.player or ""):
            raise DamageModifierError("Prevention life gain requires a player")
        if self.schema_version != 1:
            raise DamageModifierError(
                "Unsupported prevention aftermath schema version"
            )
        if (
            type(self.per_prevented) is not int
            or self.per_prevented < 0
            or type(self.fixed_amount) is not int
            or self.fixed_amount < 0
            or not (self.per_prevented or self.fixed_amount)
        ):
            raise DamageModifierError(
                "Prevention life gain requires a positive fixed or scaled amount"
            )

    def amount(self, prevented: int) -> int:
        return self.fixed_amount + self.per_prevented * prevented

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "gain_life",
            "schema_version": self.schema_version,
            "player": self.player,
            "per_prevented": self.per_prevented,
            "fixed_amount": self.fixed_amount,
        }


@dataclass(frozen=True, slots=True)
class PlaceCountersPreventionAftermath:
    subject: DamageSubject
    counter_name: str
    placing_player: str
    per_prevented: int = 0
    fixed_amount: int = 0
    schema_version: int = 1

    def __post_init__(self) -> None:
        if (
            not isinstance(self.subject, DamageSubject)
            or self.subject.kind != "permanent"
        ):
            raise DamageModifierError(
                "Prevention counter aftermath requires a permanent"
            )
        counter = " ".join(str(self.counter_name).casefold().split())
        if not counter or not str(self.placing_player or ""):
            raise DamageModifierError(
                "Prevention counter aftermath requires counter and player"
            )
        object.__setattr__(self, "counter_name", counter)
        if self.schema_version != 1:
            raise DamageModifierError(
                "Unsupported prevention aftermath schema version"
            )
        if (
            type(self.per_prevented) is not int
            or self.per_prevented < 0
            or type(self.fixed_amount) is not int
            or self.fixed_amount < 0
            or not (self.per_prevented or self.fixed_amount)
        ):
            raise DamageModifierError(
                "Prevention counter aftermath requires a positive fixed or scaled amount"
            )

    def amount(self, prevented: int) -> int:
        return self.fixed_amount + self.per_prevented * prevented

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "place_counters",
            "schema_version": self.schema_version,
            "subject": self.subject.to_dict(),
            "counter_name": self.counter_name,
            "placing_player": self.placing_player,
            "per_prevented": self.per_prevented,
            "fixed_amount": self.fixed_amount,
        }


PreventionAftermath: TypeAlias = (
    GainLifePreventionAftermath | PlaceCountersPreventionAftermath
)


def prevention_aftermath_from_dict(
    value: Mapping[str, Any],
) -> PreventionAftermath:
    if not isinstance(value, Mapping):
        raise DamageModifierError("Prevention aftermath must be an object")
    kind = value.get("kind")
    if kind == "gain_life":
        _exact_fields(
            value,
            {
                "kind",
                "schema_version",
                "player",
                "per_prevented",
                "fixed_amount",
            },
            label="Prevention life aftermath",
        )
        return GainLifePreventionAftermath(
            player=str(value["player"] or ""),
            per_prevented=value["per_prevented"],
            fixed_amount=value["fixed_amount"],
            schema_version=value["schema_version"],
        )
    if kind == "place_counters":
        _exact_fields(
            value,
            {
                "kind",
                "schema_version",
                "subject",
                "counter_name",
                "placing_player",
                "per_prevented",
                "fixed_amount",
            },
            label="Prevention counter aftermath",
        )
        subject = value["subject"]
        if not isinstance(subject, Mapping):
            raise DamageModifierError(
                "Prevention counter aftermath subject must be an object"
            )
        return PlaceCountersPreventionAftermath(
            subject=DamageSubject.from_dict(subject),
            counter_name=str(value["counter_name"] or ""),
            placing_player=str(value["placing_player"] or ""),
            per_prevented=value["per_prevented"],
            fixed_amount=value["fixed_amount"],
            schema_version=value["schema_version"],
        )
    raise DamageModifierError("Unknown prevention aftermath kind")


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
    aftermath: tuple[PreventionAftermath, ...] = ()

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
        aftermath = tuple(self.aftermath)
        if any(
            not isinstance(
                value,
                (GainLifePreventionAftermath, PlaceCountersPreventionAftermath),
            )
            for value in aftermath
        ):
            raise DamageModifierError(
                "A prevention shield aftermath must use typed values"
            )
        object.__setattr__(self, "aftermath", aftermath)

    @property
    def effect_id(self) -> str:
        return f"prevention.shield:{self.shield_id}"

    def to_dict(self) -> dict[str, Any]:
        result = {
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
        if self.aftermath:
            result["aftermath"] = [value.to_dict() for value in self.aftermath]
        return result

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "DamagePreventionShield":
        expected = {
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
        }
        _exact_fields(
            value,
            expected | ({"aftermath"} if "aftermath" in value else set()),
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
            aftermath=tuple(
                prevention_aftermath_from_dict(item)
                for item in value.get("aftermath", ())
            ),
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
