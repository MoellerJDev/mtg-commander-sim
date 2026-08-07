---
title: "ADR 0029: typed permanent-exile transaction"
status: "ADR"
authoritative_source: "this decision record and typed permanent-exile implementation"
verified: "2026-08-07"
audience: "rules, compiler, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0029"
decision_status: "accepted"
date: "2026-08-07"
---

# ADR 0029: typed permanent-exile transaction

## Context

Directly exiling a battlefield permanent had no reusable typed transaction or
closed compiler family. Existing zone-change machinery could perform the move,
but it did not give this effect family one immutable precommit identity,
resolution-time validation boundary, typed result, and capability declaration.
Compiler recognition therefore could not safely promote ordinary direct-target
instructions shared by spells, triggers, and activated abilities.

The broader exile rules include temporary exile and return, linked exiled-card
references, mass and multi-target instructions, cards from nonbattlefield
zones, costs, optional or modal effects, face-down exile, imprinted cards, and
permission to cast or play exiled cards. Those families are outside this
decision.

## Decision

One typed transaction owns represented direct-target battlefield exile. It
prepares an immutable request pinned to the permanent's physical and logical
identity, owner, controller, public zone, and phasing state. Commit rejects a
stale plan before mutation, then delegates the requested move to the canonical
replacement-aware zone-change owner. The typed result records the actual
destination after replacement and preserves the origin identity required for
deterministic event journals.

The compiler lowers exactly one mandatory whole-clause instruction exiling one
target artifact, creature, enchantment, land, nonland permanent, permanent,
artifact or enchantment, or creature or planeswalker. Every execution context
uses the same source-spanned CardProgram node, target schema, capability set,
and resolution-time revalidation. Runtime code never reparses Oracle text or
branches on printed card identity.

## Alternatives

- Add another branch to the general effect executor. Rejected because
  validation, rollback, replacement, and replay would have competing owners.
- Treat exile as destruction. Rejected because destruction prevention,
  regeneration, indestructible, and shield counters do not govern exile.
- Promote any sentence containing the exile verb. Rejected because zones,
  quantities, choices, linked objects, durations, and permissions are
  materially different rule families.

## Consequences

- Advertised direct-target exile actions and accepted commands share one strict
  target schema and resolution-time revalidation path.
- Indestructible and regeneration do not prevent the represented move.
- Control or logical-identity changes after preparation make the plan stale;
  the transaction fails before mutation.
- Destination replacements remain owned and journaled by the zone-change
  transaction, and the result reports the committed destination.
- Exile is public under this slice, so replay and multiplayer projection expose
  only already-public object and event facts.
- Temporary, linked, face-down, mass, multi-target, optional, modal,
  conditional, qualified, cost, nonbattlefield, play-permission, and compound
  forms remain explicit residuals.

## Removal condition

The grammar may widen only through another typed clause family that preserves
exact source spans, closed target and zone semantics, precommit identity
validation, canonical replacement-aware mutation, replay identity, and
principal-scoped projection. The aggregate exile mechanic remains untrusted
until every applicable variant is capability-closed.
