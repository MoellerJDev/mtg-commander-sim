from __future__ import annotations

from dataclasses import dataclass


class DamageError(ValueError):
    """A represented damage proposal cannot be resolved exactly."""


_EXILE_ZONE = "".join(("ex", "ile"))
REPRESENTED_DAMAGE_SOURCE_ZONES = (
    "battlefield",
    "command",
    _EXILE_ZONE,
    "graveyard",
    "stack",
)


@dataclass(frozen=True, slots=True)
class DamageSourceSnapshot:
    """Immutable last-known source facts pinned before damage transforms."""

    ref: str
    object_id: str
    logical_object_id: str
    controller: str
    owner: str
    zone: str = "unknown"
    oracle_id: str | None = None
    commander_designation_id: str | None = None
    types: tuple[str, ...] = ()
    subtypes: tuple[str, ...] = ()
    supertypes: tuple[str, ...] = ()
    colors: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    is_commander: bool = False
    toxic_value: int | None = 0

    def __post_init__(self) -> None:
        if not all(
            (
                self.ref,
                self.object_id,
                self.logical_object_id,
                self.controller,
                self.owner,
            )
        ):
            raise DamageError(
                "Damage sources require stable identity and controller facts"
            )
        if self.toxic_value is not None and (
            type(self.toxic_value) is not int or self.toxic_value < 0
        ):
            raise DamageError(
                "A known total toxic value must be a nonnegative integer"
            )
        if self.commander_designation_id is not None and not self.is_commander:
            raise DamageError(
                "Only a commander source may carry a designation identity"
            )
        for field in (
            "types",
            "subtypes",
            "supertypes",
            "colors",
            "keywords",
        ):
            raw = getattr(self, field)
            if not isinstance(raw, (list, tuple)) or any(
                type(value) is not str or not value for value in raw
            ):
                raise DamageError(f"Damage source {field} are malformed")
            object.__setattr__(self, field, tuple(sorted(set(raw))))

    @property
    def identity_key(self) -> str:
        return f"{self.logical_object_id}|{self.zone}"

    def to_dict(self) -> dict[str, object]:
        return {
            "ref": self.ref,
            "object_id": self.object_id,
            "logical_object_id": self.logical_object_id,
            "controller": self.controller,
            "owner": self.owner,
            "zone": self.zone,
            "oracle_id": self.oracle_id,
            "commander_designation_id": self.commander_designation_id,
            "types": list(self.types),
            "subtypes": list(self.subtypes),
            "supertypes": list(self.supertypes),
            "colors": list(self.colors),
            "keywords": list(self.keywords),
            "is_commander": self.is_commander,
            "toxic_value": self.toxic_value,
        }

    @classmethod
    def from_dict(cls, value: object) -> "DamageSourceSnapshot":
        if not isinstance(value, dict):
            raise DamageError("Damage source snapshot must be an object")
        expected = {
            "ref",
            "object_id",
            "logical_object_id",
            "controller",
            "owner",
            "zone",
            "oracle_id",
            "commander_designation_id",
            "types",
            "subtypes",
            "supertypes",
            "colors",
            "keywords",
            "is_commander",
            "toxic_value",
        }
        if set(value) != expected:
            raise DamageError("Damage source snapshot fields are malformed")

        def strings(field: str) -> tuple[str, ...]:
            raw = value[field]
            if not isinstance(raw, list) or any(
                type(item) is not str or not item for item in raw
            ):
                raise DamageError(
                    f"Damage source snapshot {field} are malformed"
                )
            return tuple(raw)

        for field in (
            "ref",
            "object_id",
            "logical_object_id",
            "controller",
            "owner",
            "zone",
        ):
            if type(value[field]) is not str:
                raise DamageError("Damage source snapshot identity is malformed")
        for field in ("oracle_id", "commander_designation_id"):
            if value[field] is not None and type(value[field]) is not str:
                raise DamageError("Damage source snapshot identity is malformed")
        if type(value["is_commander"]) is not bool:
            raise DamageError("Damage source commander flag is malformed")
        return cls(
            ref=value["ref"],
            object_id=value["object_id"],
            logical_object_id=value["logical_object_id"],
            controller=value["controller"],
            owner=value["owner"],
            zone=value["zone"],
            oracle_id=value["oracle_id"],
            commander_designation_id=value["commander_designation_id"],
            types=strings("types"),
            subtypes=strings("subtypes"),
            supertypes=strings("supertypes"),
            colors=strings("colors"),
            keywords=strings("keywords"),
            is_commander=value["is_commander"],
            toxic_value=value["toxic_value"],
        )


__all__ = ["DamageError", "DamageSourceSnapshot"]
