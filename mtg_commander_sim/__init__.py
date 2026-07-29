"""Four-player, LLM-piloted Commander simulation kernel."""

from .carddb import CardDatabase, CardRecord, Ruling
from .bulk import (
    ScryfallBulkDataError,
    ScryfallBulkItem,
    fetch_bulk_manifest,
    parse_bulk_manifest,
    refresh_scryfall_database,
)
from .client import ProjectedClientView
from .deck import DeckDefinition, DeckLoader, parse_deck_text
from .engine import ActionResult, CommanderEngine, GameRuleError
from .model import GameConfig, GameState
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
from .service import CommandEnvelope, GameService
from .session import CommanderSession
from .record import (
    finalize_record,
    provider_telemetry,
    refresh_record,
    verify_record_integrity,
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
    "CommandEnvelope",
    "CommanderEngine",
    "CommanderSession",
    "DeckDefinition",
    "DeckLoader",
    "GameConfig",
    "GameRuleError",
    "GameService",
    "GameState",
    "ProjectionCursor",
    "PROTOCOL_VERSION",
    "ProjectedClientView",
    "ProtocolError",
    "Ruling",
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
    "fetch_bulk_manifest",
    "json_patch",
    "parse_bulk_manifest",
    "parse_deck_text",
    "refresh_scryfall_database",
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

__version__ = "0.6.0"
