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
from .pilot import RunMetrics, SequentialPilotRunner
from .projection import ProjectionCursor, StateProjector
from .protocol import PROTOCOL_VERSION, ProtocolError, apply_json_patch, json_patch, view_hash
from .semantics import SemanticProgram, SemanticRegistry
from .service import CommandEnvelope, GameService
from .session import CommanderSession

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
]

__version__ = "0.3.0"
