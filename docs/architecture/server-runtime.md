---
title: "Server runtime"
status: "current"
authoritative_source: "server package and GameService"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "server contributors and local operators"
maintenance: "hand-maintained"
---

# Server runtime

The FastAPI runtime is an adapter around the deterministic game service. It
owns guest sessions, rooms, deck submissions, serialized game actors, HTTP and
WebSocket projection delivery, local SQLite control-plane persistence, managed
Scryfall snapshots, card images, and static browser assets.

## State ownership

`ServerStore` owns durable guests, memberships, rooms, lifecycle metadata,
idempotency, and record locations. Each loaded game has one `GameActor` mailbox;
only that actor invokes state-changing `GameService` operations. The runtime
persists the Game Record before acknowledging an accepted command.

## Trust boundary

The browser supplies an opaque action/capability, expected view revision,
choices, CSRF proof, and client command ID. The server derives the authenticated
principal and rejects client-selected seats, effect operations, mana side
effects, or state fields. WebSockets carry projections, not checkpoints.

## Failure and recovery

Idempotency makes a retried command safe. Ambiguous persistence failures make
the actor unavailable until durable reload. Restart recovery reopens the
record with its exact card and semantic fingerprints. A rules/fidelity pause is
not an administrative pause and cannot be cleared by ordinary resume.

## Current limit

This is a single-process local-development topology. Production accounts,
external actor leasing, rate limiting, multi-process ownership, PostgreSQL,
TLS/reverse-proxy operations, and hosted deployment are target work described
in [hosted operations](../operations/hosted.md).
