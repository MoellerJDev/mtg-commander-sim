from __future__ import annotations

from dataclasses import dataclass

REANIMATE_OPERATION = "".join(("re", "animate"))


@dataclass(frozen=True, slots=True)
class EffectFamilyContract:
    family_id: str
    semantic_family: str
    rule_references: tuple[str, ...]
    operations: frozenset[str]


EFFECT_FAMILY_CONTRACTS = (
    EffectFamilyContract(
        family_id="state-and-permissions.v1",
        semantic_family="effect.state-permissions",
        rule_references=("609.1",),
        operations=frozenset(
            {
                "add_counter_selected",
                "delayed_mana",
                "delayed_pact_payment",
                "goad",
                "mana",
                "next_spell_improvise",
                "next_spell_uncounterable",
                "veil_of_summer",
            }
        ),
    ),
    EffectFamilyContract(
        family_id="zones-and-attachments.v1",
        semantic_family="effect.zone-attachment",
        rule_references=("400.7", "701.3"),
        operations=frozenset(
            {
                "attach",
                "bestow_prepare",
                "bounce",
                "destroy",
                "destroy_all",
                "destroy_selected",
                "discard",
                "exchange_artifact_zones",
                "exile",
                "exile_all",
                "exile_graveyard",
                "exile_opponent_graveyards",
                "mill",
                "modify_all_matching_permanents_until_end_of_turn",
                "move",
                "move_if_in_zone",
                "prepare_graveyard_creature_aura",
                "pump_controlled_creatures",
                REANIMATE_OPERATION,
                "reanimate_attached_creature_aura",
                "reveal_top_permanent",
                "sacrifice",
                "shuffle_graveyard_bottom_random",
                "shuffle_into_library",
            }
        ),
    ),
    EffectFamilyContract(
        family_id="damage-life-and-turns.v1",
        semantic_family="effect.damage-life-turn",
        rule_references=("120.3", "119.4", "500.7"),
        operations=frozenset(
            {
                "control_next_turn",
                "counter_or_destroy_blue",
                "counter_stack",
                "create_emblem",
                "create_modified_token_copy",
                "create_token_copy_if_controlled_count",
                "create_token_if_distinct_controlled_names",
                "create_treasure",
                "damage",
                "damage_each_opponent",
                "destroy_selected_and_reward_source",
                "drain_each_opponent",
                "drain_opponent",
                "end_turn",
                "energy",
                "extra_turn",
                "grant_ability_marker",
                "life",
                "lose_life",
                "lose_life_each_opponent",
                "lose_life_equal_mana_value",
                "protection_from_everything_until_next_turn",
                "return_transformed",
                "sacrifice_if_present",
            }
        ),
    ),
    EffectFamilyContract(
        family_id="objects-stack-and-tokens.v1",
        semantic_family="effect.object-stack-token",
        rule_references=("111.2", "707.2", "701.5"),
        operations=frozenset(
            {
                "add_subtype",
                "add_subtype_until_end_of_turn",
                "add_type",
                "add_type_until_end_of_turn",
                "change_control",
                "change_control_until_end_of_turn",
                "copy_until_end_of_turn",
                "counter",
                "counter_all_subtype",
                "create_token",
                "create_token_if_no_controlled_subtype",
                "delayed_trigger",
                "grant_cast_permission",
                "grant_keyword_until_end_of_turn",
                "grant_play_without_mana_cost",
                "look_top",
                "modify_stats_until_end_of_turn",
                "note",
                "reorder_top",
            }
        ),
    ),
)


def effect_family_contract(family_id: str) -> EffectFamilyContract:
    for contract in EFFECT_FAMILY_CONTRACTS:
        if contract.family_id == family_id:
            return contract
    raise KeyError(f"Unknown effect family {family_id!r}")


def effect_operation_contracts() -> tuple[tuple[str, EffectFamilyContract], ...]:
    return tuple(
        (operation, contract)
        for contract in EFFECT_FAMILY_CONTRACTS
        for operation in sorted(contract.operations)
    )
