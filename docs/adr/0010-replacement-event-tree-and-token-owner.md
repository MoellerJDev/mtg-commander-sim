---
title: "ADR 0010: replayable replacement-event trees and token mutation ownership"
status: "ADR"
authoritative_source: "this decision record and platform/architecture-policy.json"
verified: "2026-08-02"
audience: "rules, semantics, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0010"
decision_status: "accepted"
date: "2026-08-02"
---

# ADR 0010: replayable replacement-event trees and token mutation ownership

## Context

The original replacement helper could transform one flat event from a supplied
choice sequence. It could not represent an affected object, APNAP choices over
simultaneous events, a replacement-created contained event, or a suspended
choice that survived exact replay. Token replacement components also committed
extra tokens after the original event and the central engine owned the entire
token mutation path.

CR 614.13, 614.16, 616.1, and 616.1g require a reusable event boundary that
preserves chooser identity, contained-event order, and rediscovery after each
replacement. Moving token creation through that boundary changes mutation
ownership and therefore requires an explicit architecture decision.

## Decision

`replacement_effects.py` owns immutable replaceable events, affected-subject
facts, nested event trees, entry reservations, simultaneous event batches,
APNAP traversal, exact selection journals, and seat-safe choice projections.
It remains independent of game state, card data, transport, and the browser.

Runtime components compile source-pinned token and zone-change descriptors into
generic `ReplacementEffect` values. The engine discovers currently active,
trusted components and suspends semantic resolution when the affected player
or object controller has a real choice. The authoritative batch and effects
remain in the continuation; pilots receive labels and stable option IDs but no
hidden event payload.

`token_creation.py` is the focused replay-participating mutation owner for token
objects. Its `TokenCreationHost` protocol exposes only the existing transaction
host operations needed to discover replacement components, allocate stable
identity and timestamps, commit token state, and dispatch generic enter events.
`CommanderEngine.create_token` is a compatibility facade over that owner.

Capabilities stay honestly `tested` or blocked where entry choices, prevention,
or replaceable event producers are not yet integrated. This decision does not
claim complete CR 614/615/616 coverage.

## Alternatives

- Keep token replacement ordering inside `CommanderEngine.create_token`.
  Rejected because it grows an oversized mutation method and leaves no reusable
  event model for other producers.
- Give semantic handlers mutable game state. Rejected because handlers must
  validate and lower immutable descriptors, not become alternate rules kernels.
- Serialize only the selected effect ID. Rejected because exact replay must also
  verify the event path and chooser against the reconstructed state.
- Treat replacement-created token and counter events as already replaced.
  Rejected because CR 614.16 requires applicable effects to consider them.

## Consequences

- Token creation leaves the central engine as a narrow compatibility method.
- Multiple applicable token or destination replacements can suspend, resume,
  and replay through the ordinary capability protocol.
- A copied token with no explicit rename preserves the copied name.
- The Dauthi Voidwalker destination rule is source-pinned semantic data rather
  than an Oracle-ID conditional in the universal engine.
- Further replaceable event producers can adopt the same batch and continuation
  model without inventing card-specific ordering code.

## Removal condition

Replace the transitional `TokenCreationHost` port when a universal typed event
transaction owns object creation and zone entry. That migration must preserve
stable event IDs, selection journals, exact replay, trigger batching, and the
principal-scoped choice boundary.
