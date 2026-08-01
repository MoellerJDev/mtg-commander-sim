---
title: "ADR 0006: typed semantic handler boundary"
status: "ADR"
authoritative_source: "this decision record"
verified: "2026-08-01"
audience: "rules, compiler, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0006"
decision_status: "accepted"
date: "2026-08-01"
---

# ADR 0006: typed semantic handler boundary

## Context

CardProgram V2 provides a canonical card artifact, but its effect nodes still
entered `CommanderEngine` string dispatch, principally through
`apply_effect` and sometimes through pre-resolution special cases. Moving
those switches wholesale would make behavior and replay regressions difficult
to localize. Giving handlers the engine or `GameState` would merely distribute
mutation authority across more files.

## Decision

Migrate operation families incrementally into a deterministic registry under
`mtg_commander_sim/semantic_runtime/`. Each stable operation has one handler
ID and schema version, typed node input, explicit capability dependencies, an
immutable `ReadOnlyHandlerContext`, and typed output intents. Handlers cannot
import the engine, state model, records, or projections.

A small executor applies intents only through existing canonical engine
methods. It does not interpret card text or mutate fields directly. Registered
operations fail closed when their node is malformed. Unregistered operations
continue through the measured legacy dispatcher until separately migrated.
Removing the old branch is part of each migration.

The first slice migrates single-player draw, APNAP table-wide draw, and monarch
designation. Both direct effect application and ordinary CardProgram stack
resolution use the registered handlers. During stack resolution, typed draw
intents continue through the existing replacement-aware draw sequence rather
than bypassing represented replacements. This does not claim complete draw
replacement behavior or complete monarch rules; the declared capabilities are
deliberately narrower.

Game Record remains schema version 3. Commands and CardProgram nodes do not
change, so current and historical records use the same replay path. Card
explain/audit output adds the registered handler mapping as derived data.

## Consequences

- Handler registration is deterministic, frozen at runtime, and rejects
  duplicate operation or handler ownership.
- Capability references are validated against the versioned registry, while
  trust remains bounded by the capability's own status and blockers.
- The architecture audit reports registered operations and remaining legacy
  branches across the engine. A registered operation still intercepted by any
  engine string-dispatch branch is measurable drift.
- New handler families require direct lowering, rollback/illegal-input,
  canonical engine, and replay evidence before their legacy branches are
  removed.
- The engine remains the mutation owner during this phase. Later kernel
  extraction may replace the intent sink without changing handler contracts.

## Alternatives

- Keep extending the central switch. Rejected because it deepens the measured
  monolith and prevents independent family testing.
- Pass `CommanderEngine` or `GameState` to every handler. Rejected because it
  creates unbounded mutation and hidden-information authority.
- Replace all operations in one change. Rejected because exact compatibility
  and review would be too difficult to establish.
- Change Game Record or CardProgram schema for the runtime registry. Rejected
  because handler selection is derived from already-versioned operation nodes.
