# ADR 0001: one serialized writer per game

- Status: accepted
- Date: 2026-07-31

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

## Consequences

The single-node ordering proof is simple and exact replay remains unchanged.
Horizontal deployment will need an external ownership lease or one routed
worker per game; two processes must never independently host the same game
actor.
