---
title: "Architecture portal"
status: "current"
authoritative_source: "implemented runtime boundaries and modular architecture documentation"
verified: "2026-08-06"
audience: "engine, server, client, and rules contributors"
maintenance: "hand-maintained"
concern: "architecture-portal"
---

# Architecture portal

This page routes contributors to the current architecture owners. Code,
schemas, machine-readable policy, and executable tests define behavior;
[ADRs](docs/adr/index.md) preserve accepted decisions and alternatives;
generated [architecture status](docs/ARCHITECTURE_DEBT_STATUS.md) owns changing
measurements.

## System invariants

- `CommanderEngine` and its typed rules subsystems are the sole authoritative
  game runtime. Clients and CardPrograms never write `GameState`.
- Each game has one serialized command writer. HTTP and WebSocket concurrency
  ends at the game actor.
- Identity is transport-derived; actions are capability-scoped, validated
  before mutation, durably journaled, and replayable.
- Advertised actions and accepted commands share typed legality, cost, target,
  and choice authority.
- Principal projection precedes serialization. Checkpoints, raw capabilities,
  opposing private zones, and analyst artifacts are not client payloads.
- Material unknown Oracle semantics and unsupported rules dependencies fail
  closed before mutation.
- Card behavior comes from pinned source-spanned CardPrograms and reusable
  rules owners, never printed-name runtime branches or live Oracle parsing.
- Game Record v3 is the durable compatibility contract. Additive state and
  continuation fields preserve historical replay semantics.

## Runtime map

```text
browser / CLI / scripted or optional automated clients
                         |
         server identity, rooms, HTTP and WebSocket
                         |
            GameService and one game actor
                         |
            session, projection and engine
              /          |          \
       typed queries  coordinators  mutation owners
              \          |          /
             deterministic GameState
                         |
          record, replay and audit journals
```

The engine is being decomposed incrementally. A valid extraction transfers one
coherent rules family to an immutable query/proposal/transaction boundary,
removes the former path, and narrows dependencies. Moving lines to an unbounded
helper or adding a parallel registry is not an ownership improvement.

## Navigate by concern

- Context and containers: [system context](docs/architecture/context.md) and
  [runtime containers](docs/architecture/containers.md)
- Rules ownership: [rules kernel](docs/architecture/rules-kernel.md),
  [dependency and mutation rules](docs/architecture/dependency-rules.md), and
  [reusable rules pieces](docs/architecture/reusable-rules-pieces.md)
- Card execution: [CardProgram](docs/architecture/card-programs.md),
  [compiler](docs/architecture/compiler.md), [typed semantic handlers](docs/architecture/semantic-handlers.md),
  [runtime components](docs/architecture/runtime-components.md), and
  [trust closure](docs/architecture/trust-closure.md)
- Rules subsystems: [damage](docs/architecture/damage.md),
  [prevention](docs/architecture/prevention.md),
  [counter placement](docs/architecture/counter-placement.md), and
  [drawing](docs/architecture/drawing.md)
- Application boundary: [server runtime](docs/architecture/server-runtime.md),
  [visibility](docs/architecture/visibility.md), and
  [protocol](docs/reference/protocol.md)
- Durability: [replay architecture](docs/architecture/replay.md) and
  [Game Record reference](docs/reference/game-record.md)
- Decisions: [ADR index](docs/adr/index.md)

Use the [documentation map](docs/index.md) for product, operations, extension,
testing, optional-client, historical, and generated references.
