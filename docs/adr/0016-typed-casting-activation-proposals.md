---
title: "ADR 0016: typed casting and activation proposals"
status: "ADR"
authoritative_source: "this decision record and platform/architecture-policy.json"
verified: "2026-08-02"
audience: "rules, protocol, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0016"
decision_status: "accepted"
date: "2026-08-02"
---

# ADR 0016: typed casting and activation proposals

## Context

Casting, activation, legal-action advertisement, and execution previously
recomputed overlapping rules in large `CommanderEngine` methods. A client
could receive an action that no longer described the same cost, target, or
source facts used by execution. Extending either path also enlarged the
monolith and encouraged card-specific exceptions at the action boundary.

## Decision

Casting and activation use immutable, canonically fingerprinted proposal
values. Read-only proposal builders own source, timing, cost, target, and
payability validation. Action offers are derived from those same queries and
carry the proposal fingerprint plus the authoritative state revision at which
the offer expires. Commit modules revalidate physical object identity and then
own the represented transaction beneath a narrow `CommanderEngine` facade.

The action catalog composes cast, land, and activation offers without
reimplementing their legality. Ordinary derived mana plans are committed by
the existing mana-activation owner. Generic Crew and Craft abilities are
lowered from Oracle keyword text, while dynamically granted activated
abilities arrive as CardProgram descriptors. Historical named Game Record v3
markers remain supported only through the explicit compatibility adapter.

The rules boundary may depend on immutable proposal models and semantic
descriptors, but it receives no application, transport, pilot, or UI
authority. Proposal fingerprints contain only authoritative rules facts and
are safe to project to the entitled seat.

## Alternatives

- Keep separate advertisement and execution checks. Rejected because their
  inevitable drift can advertise an action the server cannot execute.
- Store mutable proposal dictionaries on GameState. Rejected because stale
  offers must be reproducible without adding hidden lifecycle state.
- Move the old engine methods unchanged. Rejected because extraction requires
  coherent query/commit ownership and removal of card-specific dispatch.

## Consequences

- Stale revision, cost, source, and target facts fail before mutation.
- The same pure queries serve UI action offers and authoritative execution.
- Casting and activation commits are explicit mutation owners, while proposal,
  availability, query, and catalog modules are read-only consumers.
- `CommanderEngine` loses more than two thousand logical lines and the direct
  state-write and oversized-function ratchets both improve.
- Printed-name allowance identities are refreshed under this ADR only because
  generic literals moved into the new owners; the total allowance count
  decreases and no new card-specific behavior is approved.

## Removal condition

The remaining engine facades may disappear after all callers depend on a
stable rules-service port. Historical marker adapters remain until the Game
Record v3 compatibility window is explicitly retired.
