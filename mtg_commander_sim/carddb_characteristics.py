from __future__ import annotations

from typing import Any, Mapping

from .carddb import CardRecord
from .model import CardInstance


def _custom_object_characteristics(card: CardInstance) -> Mapping[str, Any]:
    return dict(
        card.annotations.get("object_characteristics")
        or card.annotations.get("token_characteristics")
        or {}
    )


def base_card_characteristics(
    card: CardInstance,
    record: CardRecord | None,
) -> dict[str, Any]:
    """Adapt printed or custom object data to the shared evaluator schema."""

    if record is None:
        values = _custom_object_characteristics(card)
        return {
            "name": "" if card.object_kind == "emblem" else card.printed_name,
            "mana_cost": "",
            "mana_value": values.get("mana_value", 0),
            "type_line": str(values.get("type_line", "Token")),
            "oracle_text": str(values.get("oracle_text", "")),
            "power": values.get("power"),
            "toughness": values.get("toughness"),
            "loyalty": values.get("loyalty"),
            "defense": values.get("defense"),
            "keywords": list(values.get("keywords", [])),
            "colors": list(values.get("colors", [])),
            "produced_mana": list(values.get("produced_mana", [])),
        }

    face = None
    if card.active_face:
        face = next(
            (
                value
                for value in record.faces
                if str(value.get("name") or "") == card.active_face
            ),
            None,
        )
    return {
        "name": str(face.get("name")) if face else record.name,
        "mana_cost": str(face.get("mana_cost") or "") if face else record.mana_cost,
        "mana_value": record.mana_value,
        "type_line": str(face.get("type_line") or "") if face else record.type_line,
        "oracle_text": str(face.get("oracle_text") or "") if face else record.oracle_text,
        "power": face.get("power") if face else record.power,
        "toughness": face.get("toughness") if face else record.toughness,
        "loyalty": face.get("loyalty") if face else record.loyalty,
        "defense": face.get("defense") if face else record.defense,
        "keywords": list(record.keywords),
        "colors": list(record.colors),
        "produced_mana": list(record.produced_mana),
    }


__all__ = ["base_card_characteristics"]
