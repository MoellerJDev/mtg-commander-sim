from __future__ import annotations

from typing import Any, Mapping


def normalize_game_record_v3_effect(effect: Mapping[str, Any]) -> dict[str, Any]:
    """Decode historical card-named Game Record v3 effects.

    Current CardPrograms never emit these operation names.  The mappings live
    behind the record compatibility boundary so an old record retains its
    pinned behavior without reintroducing card-specific kernel dispatch.
    """

    value = dict(effect)
    operation = str(value.get("op") or "")
    if operation in {"create_warform", "choose_warform"}:
        value.update(
            {
                "op": (
                    "create_modified_token_copy"
                    if operation == "create_warform"
                    else "choose_modified_token_copy"
                ),
                "name": "Mishra's Warform",
                "characteristics": {
                    "name": "Mishra's Warform",
                    "type_line": "Artifact Creature — Construct",
                    "power": "4",
                    "toughness": "4",
                    "mana_value": 0,
                },
                "temporary_keywords": ["Haste"],
                "sacrifice_on_controller_end_step": True,
            }
        )
    elif operation == "field_of_dead_token":
        value.update(
            {
                "op": "create_token_if_distinct_controlled_names",
                "required_type": "land",
                "minimum_distinct_names": 7,
                "token": {
                    "name": "Zombie",
                    "characteristics": {
                        "type_line": "Token Creature — Zombie",
                        "power": "2",
                        "toughness": "2",
                        "colors": ["B"],
                    },
                },
            }
        )
    elif operation == "scute_swarm_token":
        value.update(
            {
                "op": "create_token_copy_if_controlled_count",
                "copy_of": value.pop("source", None),
                "copy_name": "Scute Swarm",
                "required_type": "land",
                "fallback_token": {
                    "name": "Insect",
                    "characteristics": {
                        "type_line": "Token Creature — Insect",
                        "colors": ["G"],
                        "power": "1",
                        "toughness": "1",
                    },
                },
            }
        )
    elif operation == "create_daretti_emblem":
        value.update(
            {
                "op": "create_emblem",
                "abilities": [
                    "Whenever an artifact is put into your graveyard from "
                    "the battlefield, return that card to the battlefield "
                    "at the beginning of the next end step."
                ],
                "display_label": "Daretti, Scrap Savant emblem",
                "semantic_key": "builtin:daretti-emblem",
                "stats_counter": "daretti_emblems",
            }
        )
    elif operation == "grant_urzas_saga_chapter":
        chapter = int(value.pop("chapter", 0))
        value.update(
            {
                "op": "grant_ability_marker",
                "marker": f"urzas_saga_chapter_{chapter}",
            }
        )
    elif operation == "demonic_junker_resolve":
        value.update(
            {
                "op": "destroy_selected_and_reward_source",
                "counter": "+1/+1",
                "counter_amount": 2,
            }
        )
    elif operation == "welder_exchange":
        value["op"] = "exchange_artifact_zones"
    elif operation == "toxic_deluge":
        value.update(
            {
                "op": "modify_all_matching_permanents_until_end_of_turn",
                "required_type": "creature",
                "scale": -1,
                "event_code": "effect.toxic_deluge",
            }
        )
    elif operation == "animate_dead_prepare":
        value["op"] = "prepare_graveyard_creature_aura"
    elif operation == "animate_dead_reanimate":
        value.update(
            {
                "op": "reanimate_attached_creature_aura",
                "link_annotation": "animate_dead_creature",
                "event_code": "animate_dead.reanimate",
            }
        )
    return value
