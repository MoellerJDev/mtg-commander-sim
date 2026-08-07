"""Quorune's deterministic, server-authoritative multiplayer rules package."""

from .python_runtime import require_supported_python

require_supported_python()

from .version import __version__
from .carddb import CardDatabase, CardRecord, Ruling
from .card_programs import (
    CARD_PROGRAM_SCHEMA_VERSION,
    CardProgram,
    CardProgramError,
    CardProgramFace,
    compile_card_program,
)
from .bulk import (
    ScryfallBulkDataError,
    ScryfallBulkItem,
    fetch_bulk_manifest,
    parse_bulk_manifest,
    refresh_scryfall_database,
)
from .client import ProjectedClientView
from .continuous_effects import (
    CharacteristicState,
    ContinuousEffect,
    ContinuousEffectDuration,
    ContinuousEffectOrigin,
    ContinuousEvaluation,
    ContinuousObjectIdentity,
    ContinuousOperation,
    Layer,
    evaluate_continuous_effects,
    order_continuous_effects,
)
from .deck import DeckDefinition, DeckLoader, parse_deck_text
from .engine import ActionResult, CommanderEngine, GameRuleError
from .model import GameConfig, GameState, GoadDesignation
from .oracle_ir import (
    ORACLE_COMPILER_VERSION,
    OracleCardIR,
    compile_oracle_card,
    oracle_corpus_coverage,
)
from .pilot import (
    ManualJsonPilot,
    PilotMemory,
    PilotResponse,
    RunMetrics,
    ScriptedPilot,
    SequentialPilotRunner,
    SubprocessJsonPilot,
)
from .preflight import semantic_preflight
from .profiles import (
    DeckPilotProfile,
    DeckProfileCache,
    FINGERPRINT_ALGORITHM_VERSION,
    PROFILE_SCHEMA_VERSION,
    deck_list_fingerprint,
    deck_profile_fingerprint,
    deck_source_fingerprint,
    profile_source_fingerprint,
)
from .projection import ProjectionCursor, StateProjector
from .protocol import PROTOCOL_VERSION, ProtocolError, apply_json_patch, json_patch, view_hash
from .semantics import SemanticProgram, SemanticRegistry
from .service import (
    CommandEnvelope,
    CommandReceipt,
    GameService,
    IdempotencyRecord,
    IdempotencyRepository,
    InMemoryIdempotencyRepository,
)
from .session import CommanderSession
from .runtime import (
    GameActor,
    GameActorClosed,
    GameActorUnavailable,
    GameManager,
    GamePersistence,
)
from .persistence import (
    DirectoryGamePersistence,
    SqliteIdempotencyRepository,
    initialize_sqlite,
)
from .record import (
    finalize_record,
    provider_telemetry,
    refresh_record,
    verify_record_integrity,
)
from .replacement_effects import (
    ReplaceableEvent,
    ReplacementChoice,
    ReplacementClass,
    ReplacementEffect,
    apply_replacement,
    replacement_choice,
    resolve_replacements,
)
from .arena import (
    CodexThreadRegistry,
    CoordinatorTools,
    PilotInvocationIdentity,
    SeatScopedPilotTools,
)

__all__ = [
    "ActionResult",
    "CardDatabase",
    "CardRecord",
    "CardProgram",
    "CardProgramError",
    "CardProgramFace",
    "CARD_PROGRAM_SCHEMA_VERSION",
    "CharacteristicState",
    "CommandEnvelope",
    "CommandReceipt",
    "CommanderEngine",
    "CommanderSession",
    "ContinuousEffect",
    "ContinuousEffectDuration",
    "ContinuousEffectOrigin",
    "ContinuousEvaluation",
    "ContinuousObjectIdentity",
    "ContinuousOperation",
    "DeckDefinition",
    "DeckLoader",
    "GameConfig",
    "GameRuleError",
    "GameService",
    "GameActor",
    "GameActorClosed",
    "GameManager",
    "GamePersistence",
    "DirectoryGamePersistence",
    "SqliteIdempotencyRepository",
    "initialize_sqlite",
    "IdempotencyRecord",
    "IdempotencyRepository",
    "InMemoryIdempotencyRepository",
    "GameState",
    "GoadDesignation",
    "Layer",
    "ORACLE_COMPILER_VERSION",
    "OracleCardIR",
    "ProjectionCursor",
    "PROTOCOL_VERSION",
    "ProjectedClientView",
    "ProtocolError",
    "Ruling",
    "ReplaceableEvent",
    "ReplacementChoice",
    "ReplacementClass",
    "ReplacementEffect",
    "ScryfallBulkDataError",
    "ScryfallBulkItem",
    "SequentialPilotRunner",
    "ScriptedPilot",
    "ManualJsonPilot",
    "SubprocessJsonPilot",
    "PilotMemory",
    "PilotResponse",
    "RunMetrics",
    "SemanticProgram",
    "SemanticRegistry",
    "StateProjector",
    "apply_json_patch",
    "apply_replacement",
    "compile_oracle_card",
    "compile_card_program",
    "evaluate_continuous_effects",
    "fetch_bulk_manifest",
    "json_patch",
    "parse_bulk_manifest",
    "parse_deck_text",
    "oracle_corpus_coverage",
    "order_continuous_effects",
    "refresh_scryfall_database",
    "replacement_choice",
    "resolve_replacements",
    "view_hash",
    "semantic_preflight",
    "DeckPilotProfile",
    "DeckProfileCache",
    "FINGERPRINT_ALGORITHM_VERSION",
    "PROFILE_SCHEMA_VERSION",
    "deck_list_fingerprint",
    "deck_profile_fingerprint",
    "deck_source_fingerprint",
    "profile_source_fingerprint",
    "CodexThreadRegistry",
    "CoordinatorTools",
    "PilotInvocationIdentity",
    "SeatScopedPilotTools",
    "provider_telemetry",
    "refresh_record",
    "finalize_record",
    "verify_record_integrity",
]
