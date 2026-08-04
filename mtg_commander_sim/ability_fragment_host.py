from __future__ import annotations

from typing import Any

from .ability_fragments import StaticAbilityFragment
from .carddb_characteristics import base_card_characteristics
from .compiled_ability_fragments import (
    compiled_ability_fragment_dicts,
    compiled_enchant_spec,
    compiled_static_ability_fragments,
)
from .enchant_spec import EnchantSpec


class AbilityFragmentHostMixin:
    """Narrow runtime facade for trusted compiled ability fragments."""

    def _compiled_ability_fragments(
        self,
        card: Any,
        *,
        face_name: str | None = None,
    ) -> tuple[StaticAbilityFragment, ...]:
        return compiled_static_ability_fragments(
            self,
            card,
            face_name=face_name,
        )

    def _compiled_enchant_spec(
        self,
        card: Any,
        *,
        face_name: str | None = None,
    ) -> EnchantSpec | None:
        return compiled_enchant_spec(
            self,
            card,
            face_name=face_name,
        )

    def _compiled_ability_fragment_dicts(
        self,
        card: Any,
        *,
        face_name: str | None = None,
        error_type: type[Exception] | None = None,
    ) -> list[dict[str, Any]]:
        return compiled_ability_fragment_dicts(
            self,
            card,
            face_name=face_name,
            error_type=error_type,
        )

    def _compiled_base_characteristics(
        self,
        card: Any,
        record: Any,
        *,
        error_type: type[Exception] | None = None,
    ) -> dict[str, Any]:
        base = base_card_characteristics(card, record)
        base["ability_fragments"] = self._compiled_ability_fragment_dicts(
            card,
            error_type=error_type,
        )
        return base


__all__ = ["AbilityFragmentHostMixin"]
