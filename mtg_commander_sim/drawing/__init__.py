"""Typed CR 121 draw instructions, events, replacements, and commits.

The coordinator facade is loaded lazily because runtime semantic components
depend on the pure draw model while the coordinator consumes those components.
Keeping that dependency edge lazy prevents the package facade from turning the
two independently testable layers into an import cycle.
"""

from importlib import import_module

from .continuation import DrawDecisionContinuation, DrawResume
from .model import (
    DrawError,
    DrawEventRequest,
    DrawEventResolution,
    DrawInstructionRequest,
    PreparedDrawEvent,
    PreparedDrawInstruction,
    QueuedDraw,
    prepare_draw_event,
    prepare_draw_instruction,
    prepare_ordinary_draw,
    validate_prepared_draw,
)
from .transaction import DrawCommitHost, commit_prepared_draw
from .restrictions import (
    DrawPermission,
    DrawRestriction,
    drawn_this_turn,
    evaluate_draw_permission,
    require_payable_draw_cost,
)


_COORDINATOR_EXPORTS = {
    "begin_draw_batch",
    "begin_draw_sequence",
    "commit_unreplaced_draws",
    "complete_draw_replacement",
    "DrawCoordinatorHost",
    "draw_event_id",
    "resume_after_draw",
}


def __getattr__(name: str):
    if name not in _COORDINATOR_EXPORTS:
        raise AttributeError(name)
    value = getattr(import_module(".coordinator", __name__), name)
    globals()[name] = value
    return value

__all__ = [
    "DrawError",
    "DrawDecisionContinuation",
    "DrawResume",
    "DrawEventRequest",
    "DrawEventResolution",
    "DrawInstructionRequest",
    "DrawPermission",
    "DrawRestriction",
    "PreparedDrawEvent",
    "PreparedDrawInstruction",
    "QueuedDraw",
    "prepare_draw_event",
    "prepare_draw_instruction",
    "prepare_ordinary_draw",
    "validate_prepared_draw",
    "DrawCommitHost",
    "commit_prepared_draw",
    "begin_draw_batch",
    "begin_draw_sequence",
    "commit_unreplaced_draws",
    "complete_draw_replacement",
    "DrawCoordinatorHost",
    "draw_event_id",
    "drawn_this_turn",
    "evaluate_draw_permission",
    "require_payable_draw_cost",
    "resume_after_draw",
]
