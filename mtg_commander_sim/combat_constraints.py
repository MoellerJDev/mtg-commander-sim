from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Sequence


RequirementKind = Literal[
    "choose",
    "choose_option",
    "option_used",
]
RestrictionKind = Literal[
    "minimum_option_uses",
    "maximum_option_uses",
]


class DeclarationConstraintError(ValueError):
    """A submitted combat declaration is outside its issued problem."""


class DeclarationSearchLimitError(RuntimeError):
    """Exact requirement maximization exceeded its deterministic limit."""


@dataclass(frozen=True, slots=True)
class DeclarationRequirement:
    requirement_id: str
    kind: RequirementKind
    variable: str | None = None
    option: str | None = None
    label: str = ""

    def satisfied_by(self, declaration: Mapping[str, str]) -> bool:
        if self.kind == "choose":
            return self.variable in declaration
        if self.kind == "choose_option":
            return declaration.get(str(self.variable)) == self.option
        if self.kind == "option_used":
            return self.option in declaration.values()
        raise DeclarationConstraintError(
            f"Unknown declaration requirement {self.kind!r}"
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "id": self.requirement_id,
            "kind": self.kind,
            "variable": self.variable,
            "option": self.option,
            "label": self.label,
        }


@dataclass(frozen=True, slots=True)
class DeclarationRestriction:
    restriction_id: str
    kind: RestrictionKind
    option: str
    count: int
    when_used: bool = False
    label: str = ""

    def error(self, declaration: Mapping[str, str]) -> str | None:
        uses = sum(
            1 for selected in declaration.values() if selected == self.option
        )
        if self.when_used and uses == 0:
            return None
        if self.kind == "minimum_option_uses" and uses < self.count:
            return self.label or (
                f"{self.option} requires at least {self.count} selections"
            )
        if self.kind == "maximum_option_uses" and uses > self.count:
            return self.label or (
                f"{self.option} allows at most {self.count} selections"
            )
        return None

    def to_dict(self) -> dict[str, str | int | bool]:
        return {
            "id": self.restriction_id,
            "kind": self.kind,
            "option": self.option,
            "count": self.count,
            "when_used": self.when_used,
            "label": self.label,
        }


@dataclass(frozen=True, slots=True)
class DeclarationEvaluation:
    satisfied: tuple[str, ...]
    unmet: tuple[str, ...]
    maximum: int
    restriction_errors: tuple[str, ...]

    @property
    def legal(self) -> bool:
        return not self.restriction_errors and len(self.satisfied) == self.maximum


@dataclass(frozen=True, slots=True)
class DeclarationProblem:
    """A finite combat declaration problem under CR 508.1d or 509.1c.

    Each variable may be omitted or select exactly one option from its domain.
    Restrictions are inviolable. Among declarations that obey them, a legal
    declaration must satisfy the greatest possible number of requirements.
    """

    domains: Mapping[str, Sequence[str]]
    requirements: tuple[DeclarationRequirement, ...] = ()
    restrictions: tuple[DeclarationRestriction, ...] = ()
    max_search_states: int = 200_000

    def __post_init__(self) -> None:
        if self.max_search_states < 1:
            raise ValueError("max_search_states must be positive")
        if len({item.requirement_id for item in self.requirements}) != len(
            self.requirements
        ):
            raise ValueError("Declaration requirement ids must be unique")
        if len({item.restriction_id for item in self.restrictions}) != len(
            self.restrictions
        ):
            raise ValueError("Declaration restriction ids must be unique")

    def canonical_declaration(
        self,
        declaration: Mapping[str, str],
    ) -> dict[str, str]:
        if not isinstance(declaration, Mapping):
            raise DeclarationConstraintError(
                "Combat declaration must be a mapping"
            )
        canonical: dict[str, str] = {}
        for raw_variable, raw_option in declaration.items():
            variable = str(raw_variable)
            option = str(raw_option)
            if variable not in self.domains:
                raise DeclarationConstraintError(
                    f"{variable} is not an eligible declaration object"
                )
            if option not in self.domains[variable]:
                raise DeclarationConstraintError(
                    f"{option} is not legal for {variable}"
                )
            canonical[variable] = option
        return canonical

    def restriction_errors(
        self,
        declaration: Mapping[str, str],
    ) -> tuple[str, ...]:
        return tuple(
            error
            for restriction in self.restrictions
            if (error := restriction.error(declaration)) is not None
        )

    def satisfied_requirement_ids(
        self,
        declaration: Mapping[str, str],
    ) -> tuple[str, ...]:
        return tuple(
            requirement.requirement_id
            for requirement in self.requirements
            if requirement.satisfied_by(declaration)
        )

    def maximum_satisfied_requirements(self) -> int:
        if not self.requirements:
            return 0
        variables = sorted(self.domains)
        domains = {
            variable: tuple(dict.fromkeys(self.domains[variable]))
            for variable in variables
        }
        best = 0
        states = 0
        declaration: dict[str, str] = {}

        def search(index: int) -> bool:
            nonlocal best, states
            states += 1
            if states > self.max_search_states:
                raise DeclarationSearchLimitError(
                    "Exact combat requirement maximization exceeded "
                    f"{self.max_search_states} states"
                )
            if index == len(variables):
                if self.restriction_errors(declaration):
                    return False
                best = max(
                    best,
                    len(self.satisfied_requirement_ids(declaration)),
                )
                return best == len(self.requirements)

            variable = variables[index]
            # Requirement-satisfying branches occur before omission. This is
            # deterministic and usually proves the theoretical maximum early.
            for option in domains[variable]:
                declaration[variable] = option
                if search(index + 1):
                    return True
            declaration.pop(variable, None)
            return search(index + 1)

        search(0)
        return best

    def evaluate(
        self,
        declaration: Mapping[str, str],
    ) -> DeclarationEvaluation:
        canonical = self.canonical_declaration(declaration)
        satisfied = self.satisfied_requirement_ids(canonical)
        satisfied_set = set(satisfied)
        return DeclarationEvaluation(
            satisfied=satisfied,
            unmet=tuple(
                item.requirement_id
                for item in self.requirements
                if item.requirement_id not in satisfied_set
            ),
            maximum=self.maximum_satisfied_requirements(),
            restriction_errors=self.restriction_errors(canonical),
        )

    def projection(self) -> dict[str, object]:
        return {
            "requirements": [item.to_dict() for item in self.requirements],
            "restrictions": [item.to_dict() for item in self.restrictions],
            "maximum_requirements": self.maximum_satisfied_requirements(),
        }
