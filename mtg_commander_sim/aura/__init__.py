"""Typed targeting, entry, and legality rules for bounded Aura grammar."""

from .grammar import (
    is_aura_type_line,
    parse_simple_enchant_line,
    simple_enchant_spec_from_oracle,
)
from .compiler import keyword_target_schema
from .model import (
    AuraControllerRelation,
    AuraEntryChoiceRequired,
    AuraEntryOutcome,
    AuraEntryPlan,
    AuraRuleError,
    AuraZoneMovePreflight,
    EnchantSpec,
    LinkedGraveyardCreatureEnchantSpec,
    SimpleEnchantSpec,
    enchant_spec_from_dict,
    enchant_spec_to_dict,
)
from .runtime import (
    commit_aura_entry_attachment,
    commit_aura_zone_move,
    aura_resolution_move_kwargs,
    legal_aura_target_refs,
    prepare_aura_entry,
    preflight_aura_zone_move,
    simple_aura_attachment_is_legal,
)
from .decisions import (
    AuraEntryContinuation,
    complete_aura_entry_choice,
    issue_aura_entry_choice,
)

__all__ = [
    "AuraControllerRelation",
    "AuraEntryChoiceRequired",
    "AuraEntryOutcome",
    "AuraEntryPlan",
    "AuraEntryContinuation",
    "AuraRuleError",
    "AuraZoneMovePreflight",
    "EnchantSpec",
    "LinkedGraveyardCreatureEnchantSpec",
    "SimpleEnchantSpec",
    "commit_aura_entry_attachment",
    "commit_aura_zone_move",
    "complete_aura_entry_choice",
    "enchant_spec_from_dict",
    "enchant_spec_to_dict",
    "aura_resolution_move_kwargs",
    "is_aura_type_line",
    "legal_aura_target_refs",
    "keyword_target_schema",
    "parse_simple_enchant_line",
    "prepare_aura_entry",
    "preflight_aura_zone_move",
    "issue_aura_entry_choice",
    "simple_aura_attachment_is_legal",
    "simple_enchant_spec_from_oracle",
]
