---
title: "ADR 0001: one serialized writer per game"
status: "ADR"
authoritative_source: "this decision record"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "server, persistence, and engine contributors"
maintenance: "hand-maintained"
adr_id: "0001"
decision_status: "accepted"
date: "2026-07-31"
---

# ADR 0001: one serialized writer per game

## Context

HTTP retries, simultaneous WebSockets, and reconnects can deliver commands
concurrently. `CommanderSession` is deterministic but was originally an
in-process sequential harness, not a concurrent database.

## Decision

`GameManager` owns one `GameActor` per active game. All state observation and
mutation crosses its bounded asyncio mailbox. A command is applied, the Game
Record is durably replaced, idempotency is committed, and only then is the
receipt acknowledged. Any exception during the ambiguous post-mutation commit
window makes the actor unavailable until it is reloaded from durable state.

## Alternatives

A shared mutable session guarded only by request-level locks was rejected
because retries, WebSockets, and persistence acknowledgement would still have
multiple ordering authorities. One process per game was deferred because it
adds deployment complexity without changing the required single-writer proof.

## Consequences

The single-node ordering proof is simple and exact replay remains unchanged.
Horizontal deployment will need an external ownership lease or one routed
worker per game; two processes must never independently host the same game
actor.
