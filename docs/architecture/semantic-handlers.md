---
title: "Typed semantic handlers"
status: "current"
authoritative_source: "mtg_commander_sim/semantic_runtime and platform/architecture-policy.json"
verified: "2026-08-01"
audience: "rules, compiler, and replay contributors"
maintenance: "hand-maintained"
---

# Typed semantic handlers

The typed semantic runtime is an incremental boundary between CardProgram
effect nodes and authoritative mutation. It currently owns `draw`,
`draw_each_player`, and `become_monarch`; every other operation remains on the
explicit legacy fallback and is not implied to be migrated.

```mermaid
flowchart LR
    Program["CardProgram effect node"] --> Registry["frozen handler registry"]
    Query["immutable rules query"] --> Handler["typed family handler"]
    Registry --> Handler
    Handler --> Intents["typed intents"]
    Intents --> Executor["canonical intent executor"]
    Executor --> Engine["existing engine mutation methods"]
    Registry -->|"unregistered only"| Legacy["measured legacy dispatcher"]
```

Handlers receive only the acting seat, a default reason, the seats still
represented by the game, active seats, and APNAP order. They do not receive
hands, libraries, card objects, mutable state, projections, or record data.
The architecture validator rejects imports that would cross this boundary.

Each handler declares a stable ID, schema version, one operation, and bounded
capability dependencies. Registration rejects duplicate ownership and unknown
capability IDs. Malformed input for a registered operation is a rules error;
it never falls back to permissive string dispatch.

The executor is intentionally small. Direct effect application sends
`DrawCardsIntent` and `BecomeMonarchIntent` through
`CommanderEngine.draw` and `CommanderEngine.become_monarch`. Ordinary
CardProgram stack resolution also lowers registered nodes through this same
handler registry. Draw intents then enter the engine's replacement-aware draw
sequence so represented draw replacements and private draw continuations keep
their existing behavior. Handlers themselves never mutate state.

The architecture audit scans every semantic-operation branch in the engine,
not only `apply_effect`. A registered operation intercepted before the handler
boundary is therefore reported as migration drift.

## Migration checklist

1. Characterize the current operation and exact return/event behavior.
2. Define a typed node and intent with the smallest read-only query surface.
3. Register one stable handler and bounded capability dependencies.
4. Add direct lowering, malformed-input rollback, ordinary stack-resolution,
   and exact replay tests.
5. Remove every corresponding engine dispatch branch, including any
   pre-resolution special case outside `apply_effect`.
6. Update CardProgram explain/audit mapping and generated architecture status.

Do not use this boundary to widen Oracle coverage or conceal unresolved cost,
target, replacement, prevention, visibility, or interaction semantics. See
[ADR 0006](../adr/0006-typed-semantic-handler-boundary.md).
