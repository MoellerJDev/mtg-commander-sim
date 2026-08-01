"""Canonical CardProgram V2 models and compatibility adapters."""

from .model import (
    CARD_PROGRAM_SCHEMA_VERSION,
    CardProgram,
    CardProgramError,
    CardProgramFace,
)
from .adapters import (
    card_program_from_semantic_programs,
    card_programs_from_semantic_programs,
    compile_card_program,
)
from .commands import CARD_PROGRAM_OPERATIONS, execute_card_operation
from .validation import canonical_program_fingerprint, program_source_is_current

__all__ = [
    "CARD_PROGRAM_SCHEMA_VERSION",
    "CardProgram",
    "CardProgramError",
    "CardProgramFace",
    "card_program_from_semantic_programs",
    "card_programs_from_semantic_programs",
    "compile_card_program",
    "CARD_PROGRAM_OPERATIONS",
    "execute_card_operation",
    "canonical_program_fingerprint",
    "program_source_is_current",
]
