from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


class ObjectQueryError(ValueError):
    """A generic object predicate is malformed or noncanonical."""


_QUERY_FIELDS = {
    "zones",
    "owner",
    "controller",
    "types_all",
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
}


def _normalized_terms(
    values: Iterable[str], *, field_name: str, upper: bool = False
) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise ObjectQueryError(f"Object query {field_name} must be an array")
    normalize = str.upper if upper else str.casefold
    result = tuple(sorted({normalize(str(value)) for value in values if str(value)}))
    if len(result) != len(values):
        raise ObjectQueryError(
            f"Object query {field_name} requires unique nonempty strings"
        )
    return result


@dataclass(frozen=True, slots=True)
class ObjectQuerySpec:
    zones: tuple[str, ...] = ()
    owner: str | None = None
    controller: str | None = None
    types_all: tuple[str, ...] = ()
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

    def __post_init__(self) -> None:
        for field_name in (
            "zones",
            "types_all",
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
                value = str(value)
                if not value:
                    raise ObjectQueryError(
                        f"Object query {field_name} cannot be empty"
                    )
                object.__setattr__(self, field_name, value)
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "zones": list(self.zones),
            "owner": self.owner,
            "controller": self.controller,
            "types_all": list(self.types_all),
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

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ObjectQuerySpec":
        if not isinstance(value, Mapping):
            raise ObjectQueryError("Object query must be an object")
        actual = set(value)
        if actual != _QUERY_FIELDS:
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
        )
