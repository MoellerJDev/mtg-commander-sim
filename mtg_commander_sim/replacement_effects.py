"""Compatibility facade for the decomposed CR 614-616 subsystem.

New implementation belongs under :mod:`mtg_commander_sim.replacement`. This
module remains import-stable for Game Record v3 code and external clients.
"""

from .replacement import (
    AddAmount,
    AffectedObject,
    AppendValues,
    CapResultLifeLoss,
    CreateNestedEvent,
    EntryReplacementScope,
    FrozenMap,
    PreventionAllocationChoice,
    MultiplyAmount,
    PreventAmount,
    PreventUsingShield,
    ReplaceableEvent,
    ReplacementBatchChoice,
    ReplacementBatchProgress,
    ReplacementChoice,
    ReplacementChoiceRequired,
    ReplacementClass,
    ReplacementContinuation,
    ReplacementEffect,
    ReplacementEffectError,
    ReplacementEventBatch,
    ReplacementOperation,
    ReplacementSelection,
    ReplacementTreeChoice,
    RedirectDamage,
    ReserveZoneChange,
    SetField,
    UnionValues,
    advance_replacement_batch,
    apply_batch_replacement,
    apply_replacement,
    apply_tree_replacement,
    canonical_replacement_selection,
    immutable_fingerprint,
    next_batch_replacement_choice,
    operation_from_dict,
    operation_to_dict,
    replacement_choice,
    replacement_choice_payload,
    replacement_tree_choice,
    resolve_replacement_batch,
    resolve_replacements,
)

__all__ = [name for name in globals() if not name.startswith("_")]
