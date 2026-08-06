---
title: "ADR 0021: canonical draw transaction and replacement ownership"
status: "ADR"
authoritative_source: "this decision record and platform/architecture-policy.json"
verified: "2026-08-05"
audience: "rules, compiler, semantics, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0021"
decision_status: "accepted"
date: "2026-08-02"
---

# ADR 0021: canonical draw transaction and replacement ownership

## Context

Draw producers previously moved cards from library to hand through several
engine and semantic paths. Those paths could not apply replacement effects to
each individual draw, suspend for an affected-player choice, or distinguish a
draw from another library-to-hand move consistently. A beginning-phase helper,
stack resolution, semantic choices, and conditional spell effects therefore
had overlapping authority.

The Oracle compiler also needs a generic runtime representation for graveyard
draw-replacement keywords and ordinary draw effects. Adding those families to
the central Oracle module without extracting its immutable values would grow an
already oversized compiler compatibility facade.

## Decision

The `drawing` package owns immutable, versioned draw instructions, individual
draw events, continuation data, prepared results, and the canonical mutation
transaction. The transaction validates the prepared state fingerprint, moves
exactly one top library object through the ordinary zone owner, updates draw
history and empty-library state, and exposes no arbitrary state callback.

The draw coordinator is a read-only orchestration boundary. It creates one
replacement event per draw, applies APNAP replacement ordering, suspends through
the existing replacement continuation machinery when a choice is required, and
delegates the final mutation to the draw transaction. Individual events and
queued instructions are drained by an iterative trampoline, so legal large
counts are not bounded by Python recursion depth. A suspended choice serializes
the exact remaining count and re-enters that same loop after completion. Turn
draws, stack effects, semantic choices, conditional effects, and ordered
instructions all enter that same coordinator. Unrouted `DrawCardsIntent` values
fail closed.

Trusted graveyard draw replacements are discovered by a generic semantic
runtime component using a narrow structural state protocol. Runtime descriptor
data lowers to typed `DredgeDraw` replacement operations before it participates
in a game. The operation revalidates physical source identity and graveyard
continuity, mills through the canonical zone path, and returns the original card
to hand instead of committing the replaced draw.

Draw permission is a separate immutable query over turn history and live,
trusted battlefield restrictions. The coordinator recomputes that permission
before each individual event, so a mandatory multi-draw can occur partially
while an optional draw or draw cost is legal only when its complete count is
possible. An empty library is not itself a draw prohibition. Current
unconditional fixed draw doubling creates typed result-draw instructions under
CR 121.7. Those instructions run before the original instruction tail, create
independently replaceable draw events, and exclude the producing effect under
CR 614.5. Historical instruction-count multipliers remain readable only as
explicit Game Record v3 compatibility.

The transaction can pin a closed typed action sequence to the exact physical
card drawn. The first represented CR 121.6c family publicly reveals that card
and discards it unless its front face is a land. Prevented, prohibited, Dredge,
and replacement-result draws do not inherit the original event's actions.

`offer_draw` is the reviewed generic semantic operation for a seat-scoped
optional draw choice. Its handler records chooser and prospective drawer
separately, validates the prospective drawer before issuing and completing the
choice, and lowers an accepted choice back into the canonical mandatory draw
path. It has no direct mutation or hidden-zone authority.

`draw_if_opponent_cast_colors_this_turn` and
`grant_uncounterable_hexproof_from_colors_until_end` are reviewed generic
semantic operations for ordered conditional effects. The historical
`veil_of_summer` operation remains readable for prior Game Record v3 programs
but is no longer emitted by the current semantic pack. No operation dispatches
on a printed card name or Oracle ID.

Immutable Oracle IR values live in `compiler/ir_model.py`; `oracle_ir.py`
remains the compatibility import surface and compilation coordinator. This
keeps the oversized module ratchet moving downward while preserving callers.

## Alternatives

- Keep every draw producer responsible for replacement handling. Rejected
  because individual-draw ordering, continuation, replay, and empty-library
  behavior would diverge again.
- Implement the graveyard keyword inside `CommanderEngine`. Rejected because
  it would add keyword and source-card knowledge to the universal engine.
- Treat all library-to-hand moves as draws. Rejected because CR 121 explicitly
  distinguishes draw instructions from other zone changes.
- Remove the historical card-shaped operation immediately. Rejected because
  existing Game Record v3 semantic programs must remain replayable.

## Consequences

- Represented draws now share one replacement-aware, replay-pinned mutation
  path, including private choice, empty-library behavior, and iterative large-
  count coordination.
- Replacement-result draws and specifically-drawn-card actions have separate
  fine-grained capabilities rather than widening the base draw trust claim.
- The engine loses draw sequencing and producer-specific mutation branches;
  live draw-limit and optional-draw legality.
- The compiler gains generic fixed draw, draw-limit, result-doubling,
  optional-draw, graveyard-keyword, and public reveal/discard-unless-land
  templates with measurable corpus promotions.
- The architecture specificity scan records the generic `reason` metadata key
  used by the new typed result and action descriptors. `Reason` is also a card
  name, but these structural payload keys contain no card dispatch and are not
  conditional behavior.
- Shared-team turns, conditional and dynamic draw-limit grammar, broader
  specifically-drawn-card actions, optional reveal-as-drawn choices,
  face-down casting-process draws, and wider replacement-result grammar remain
  explicitly unsupported until their dependencies are implemented.
