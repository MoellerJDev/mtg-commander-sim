from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


DamageRecipientKind = Literal["player", "permanent"]


@dataclass(frozen=True, slots=True)
class DamageEvent:
    """One final source-recipient result from an authoritative damage batch.

    The event records damage after prevention and replacement processing.  A
    zero ``dealt_amount`` is still useful to the audit journal, but it must not
    be dispatched as a ``damage.dealt`` trigger event.
    """

    source: str
    source_object_id: str
    source_logical_object_id: str
    source_controller: str
    source_owner: str
    source_types: tuple[str, ...]
    source_subtypes: tuple[str, ...]
    source_colors: tuple[str, ...]
    source_keywords: tuple[str, ...]
    source_is_commander: bool
    target: str
    target_kind: DamageRecipientKind
    target_object_id: str | None
    target_controller: str | None
    target_types: tuple[str, ...]
    target_subtypes: tuple[str, ...]
    assigned_amount: int
    dealt_amount: int
    prevented_amount: int
    combat: bool
    damage_step: int | None = None
    first_strike_step: bool = False

    def __post_init__(self) -> None:
        if self.assigned_amount <= 0:
            raise ValueError("A damage event requires a positive assignment")
        if self.dealt_amount < 0 or self.prevented_amount < 0:
            raise ValueError("Damage event results cannot be negative")
        if self.dealt_amount + self.prevented_amount != self.assigned_amount:
            raise ValueError(
                "Dealt and prevented damage must equal the assignment"
            )
        if self.target_kind == "player" and self.target_object_id is not None:
            raise ValueError("Player damage cannot have a target object id")
        if self.target_kind == "permanent" and not self.target_object_id:
            raise ValueError("Permanent damage requires a target object id")

    @property
    def was_dealt(self) -> bool:
        return self.dealt_amount > 0

    def semantic_context(self) -> dict[str, Any]:
        """Return the stable normalized context consumed by trigger programs."""

        return {
            # ``card`` is the established self-event identity field used by
            # ``damage.dealt.self`` programs.
            "card": self.source,
            "source": self.source,
            "source_object_id": self.source_object_id,
            "source_logical_object_id": self.source_logical_object_id,
            "source_controller": self.source_controller,
            "source_owner": self.source_owner,
            "source_types": list(self.source_types),
            "source_subtypes": list(self.source_subtypes),
            "source_colors": list(self.source_colors),
            "source_keywords": list(self.source_keywords),
            "source_is_commander": self.source_is_commander,
            "target": self.target,
            "target_kind": self.target_kind,
            "target_object_id": self.target_object_id,
            "target_controller": self.target_controller,
            "target_types": list(self.target_types),
            "target_subtypes": list(self.target_subtypes),
            "player": self.target if self.target_kind == "player" else None,
            "amount": self.dealt_amount,
            "assigned_amount": self.assigned_amount,
            "prevented_amount": self.prevented_amount,
            "combat": self.combat,
            "damage_step": self.damage_step,
            "first_strike_step": self.first_strike_step,
        }
