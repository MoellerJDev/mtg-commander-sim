from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .damage_source import REPRESENTED_DAMAGE_SOURCE_ZONES


class ObjectQueryError(ValueError):
    """A generic object predicate is malformed or noncanonical."""


_QUERY_FIELDS = frozenset({
    "zones",
    "owner",
    "controller",
    "types_all",
    "types_any",
    "excluded_types",
    "subtypes_all",
    "supertypes_all",
    "colors_all",
    "colors_any",
    "keywords_all",
    "token",
    "tapped",
    "include_phased_out",
    "known_to_actor",
    "exclude_ref",
})
_LEGACY_QUERY_FIELDS = _QUERY_FIELDS - {"types_any"}


def _normalized_terms(
    values: Iterable[str], *, field_name: str, upper: bool = False
) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise ObjectQueryError(f"Object query {field_name} must be an array")
    normalize = str.upper if upper else str.casefold
    normalized: list[str] = []
    for value in values:
        if type(value) is not str or not value:
            raise ObjectQueryError(
                f"Object query {field_name} requires nonempty strings"
            )
        normalized.append(normalize(value))
    result = tuple(sorted(normalized))
    if len(set(result)) != len(result):
        raise ObjectQueryError(
            f"Object query {field_name} requires unique normalized strings"
        )
    return result


@dataclass(frozen=True, slots=True)
class ObjectQuerySpec:
    zones: tuple[str, ...] = ()
    owner: str | None = None
    controller: str | None = None
    types_all: tuple[str, ...] = ()
    types_any: tuple[str, ...] = ()
    excluded_types: tuple[str, ...] = ()
    subtypes_all: tuple[str, ...] = ()
    supertypes_all: tuple[str, ...] = ()
    colors_all: tuple[str, ...] = ()
    colors_any: tuple[str, ...] = ()
    keywords_all: tuple[str, ...] = ()
    token: bool | None = None
    tapped: bool | None = None
    include_phased_out: bool = False
    known_to_actor: bool | None = None
    exclude_ref: str | None = None
    _serialization_version: int = field(
        default=2,
        repr=False,
        compare=False,
        hash=False,
    )

    def __post_init__(self) -> None:
        for field_name in (
            "zones",
            "types_all",
            "types_any",
            "excluded_types",
            "subtypes_all",
            "supertypes_all",
            "keywords_all",
        ):
            object.__setattr__(
                self,
                field_name,
                _normalized_terms(
                    getattr(self, field_name), field_name=field_name
                ),
            )
        for field_name in ("colors_all", "colors_any"):
            object.__setattr__(
                self,
                field_name,
                _normalized_terms(
                    getattr(self, field_name),
                    field_name=field_name,
                    upper=True,
                ),
            )
        for field_name in ("owner", "controller", "exclude_ref"):
            value = getattr(self, field_name)
            if value is not None:
                if type(value) is not str or not value:
                    raise ObjectQueryError(
                        f"Object query {field_name} must be a nonempty string or null"
                    )
        for field_name in ("token", "tapped", "known_to_actor"):
            value = getattr(self, field_name)
            if value is not None and type(value) is not bool:
                raise ObjectQueryError(
                    f"Object query {field_name} must be boolean or null"
                )
        if type(self.include_phased_out) is not bool:
            raise ObjectQueryError(
                "Object query include_phased_out must be boolean"
            )
        if self._serialization_version not in {1, 2}:
            raise ObjectQueryError(
                "Object query serialization version is unsupported"
            )

    def canonical_dict(self) -> dict[str, Any]:
        """Return the complete current semantic descriptor."""

        return {
            "zones": list(self.zones),
            "owner": self.owner,
            "controller": self.controller,
            "types_all": list(self.types_all),
            "types_any": list(self.types_any),
            "excluded_types": list(self.excluded_types),
            "subtypes_all": list(self.subtypes_all),
            "supertypes_all": list(self.supertypes_all),
            "colors_all": list(self.colors_all),
            "colors_any": list(self.colors_any),
            "keywords_all": list(self.keywords_all),
            "token": self.token,
            "tapped": self.tapped,
            "include_phased_out": self.include_phased_out,
            "known_to_actor": self.known_to_actor,
            "exclude_ref": self.exclude_ref,
        }

    def to_dict(self) -> dict[str, Any]:
        value = self.canonical_dict()
        if self._serialization_version == 1:
            # Historical Game Record v3 payloads predate the additive
            # types-any predicate.  Preserve their exact serialized shape.
            value.pop("types_any")
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ObjectQuerySpec":
        if not isinstance(value, Mapping):
            raise ObjectQueryError("Object query must be an object")
        actual = frozenset(value)
        if actual not in {_QUERY_FIELDS, _LEGACY_QUERY_FIELDS}:
            missing = sorted(_QUERY_FIELDS - actual)
            unknown = sorted(actual - _QUERY_FIELDS)
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if unknown:
                details.append("unknown " + ", ".join(unknown))
            raise ObjectQueryError(
                "Object query fields: " + "; ".join(details)
            )
        return cls(
            zones=value["zones"],
            owner=value["owner"],
            controller=value["controller"],
            types_all=value["types_all"],
            types_any=value.get("types_any", ()),
            excluded_types=value["excluded_types"],
            subtypes_all=value["subtypes_all"],
            supertypes_all=value["supertypes_all"],
            colors_all=value["colors_all"],
            colors_any=value["colors_any"],
            keywords_all=value["keywords_all"],
            token=value["token"],
            tapped=value["tapped"],
            include_phased_out=value["include_phased_out"],
            known_to_actor=value["known_to_actor"],
            exclude_ref=value["exclude_ref"],
            _serialization_version=(
                2 if "types_any" in value else 1
            ),
        )


def validate_chosen_damage_source_predicate(
    spec: ObjectQuerySpec,
) -> ObjectQuerySpec:
    """Validate the closed public CR 609.7 chosen-source predicate family."""

    if not isinstance(spec, ObjectQuerySpec):
        raise ObjectQueryError(
            "Chosen damage sources require a typed object predicate"
        )
    if not spec.zones or not set(spec.zones).issubset(
        REPRESENTED_DAMAGE_SOURCE_ZONES
    ):
        raise ObjectQueryError(
            "Chosen damage sources require nonempty represented public zones"
        )
    if spec.known_to_actor is not True:
        raise ObjectQueryError(
            "Chosen damage sources must be legally known to the chooser"
        )
    if spec.include_phased_out:
        raise ObjectQueryError(
            "Chosen damage sources cannot include phased-out objects"
        )
    if spec.excluded_types:
        raise ObjectQueryError(
            "Chosen damage sources do not support excluded card types"
        )
    if spec.token is not None or spec.tapped is not None:
        raise ObjectQueryError(
            "Chosen damage sources do not support token or tapped predicates"
        )
    if spec.exclude_ref is not None:
        raise ObjectQueryError(
            "Chosen damage sources do not support unrelated exclusions"
        )
    return spec
