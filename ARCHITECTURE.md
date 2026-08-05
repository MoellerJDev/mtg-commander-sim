---
title: "Architecture overview"
status: "current"
authoritative_source: "implemented runtime boundaries and modular architecture documentation"
verified: "2026-08-05"
audience: "engine, server, client, and rules contributors"
maintenance: "hand-maintained"
---

# Architecture overview

This file is the short entry point for the architecture. Detailed ownership,
dependency and extension rules live in the modular documents under
[`docs/architecture/`](docs/architecture/) and the accepted
[ADRs](docs/adr/index.md). Generated measurements live in
[architecture debt status](docs/ARCHITECTURE_DEBT_STATUS.md); do not duplicate
those changing counts here.

## Invariants

- `CommanderEngine` and its typed subsystems are the sole authoritative game
  runtime. External clients never write `GameState`.
- Each game has one serialized command writer. HTTP and WebSocket concurrency
  ends at the per-game actor boundary.
- Every command is authenticated, capability-scoped, validated before mutation,
  journaled and replayable.
- Legal-action advertisement and command acceptance consume the same typed
  proposal or query authority.
- Hidden information leaves the runtime only through a principal-scoped
  projection. Public observers receive no seat-private substitute fields.
- Material unsupported semantics fail closed before mutation.
- Card behavior comes from pinned CardPrograms, typed runtime descriptors and
  reusable rules owners—not printed-name branches or live Oracle parsing.
- Game Record v3 remains the durable command/replay contract. New subsystems add
  typed payloads without silently reinterpreting historical records.

## Runtime layers

```text
React browser / CLI / scripted, manual, subprocess or optional AI clients
                                 |
                 FastAPI room and identity adapter
                                 |
               transport-neutral GameService actor
                                 |
                    Session and StateProjector
                                 |
                       CommanderEngine facade
                 /               |               \
       typed rules queries   event coordinators   mutation owners
                 \               |               /
                    deterministic GameState
                                 |
                 command, event and audit journals
```

The browser renders projections and submits opaque action IDs. It does not
reimplement timing, targets, mana, combat or card legality. `server/` manages
rooms, guest identity, WebSockets, SQLite control data, process recovery,
Scryfall refresh and image caching without moving transport dependencies into
`mtg_commander_sim/`.

The engine is still being decomposed. A valid extraction creates a coherent
typed owner with independent tests, narrows dependencies and removes the former
implementation. Moving lines to an unbounded helper or adding a second registry
does not count as an extraction.

## Rules and card path

Pinned Oracle data is compiled into source-spanned CardProgram V2 nodes. A
program declares fine-grained capabilities and runtime components. Trusted-only
play requires the whole materially reachable program to close over trusted
capabilities and supported dependencies.

At runtime:

1. read-only rules queries derive effective characteristics and candidate facts;
2. a typed proposal enumerates legal choices and validates the selected command;
3. replacement/choice coordinators suspend and resume through replay-pinned
   continuations where necessary;
4. a narrow mutation owner commits the validated result atomically;
5. state-based actions and triggers stabilize before priority returns;
6. projections, opportunity telemetry and journals are derived from the committed
   state.

Unsupported grammar remains a precise compiler residual. Repeated card-specific
descriptors must be generalized into a shared compiler production and runtime
family.

## Persistence, replay and privacy

Game Record v3 separates the initial state, accepted command journal, event and
decision journals, checkpoints, manifests and derived review. Capabilities are
not persisted. Replay verifies before/after hashes and pinned semantic identity;
failed commands roll back without mutation.

The authoritative checkpoint may contain every hidden zone, so it is never a
client API. `StateProjector` produces seat, spectator and coordinator views. A
seat sees its own private data plus public information; opponents receive only
public counts or objects. Rules lookup is limited to visible or legally known
references.

## Detailed references

- [System context](docs/architecture/context.md)
- [Runtime containers](docs/architecture/containers.md)
- [Rules kernel](docs/architecture/rules-kernel.md)
- [CardProgram V2](docs/architecture/card-programs.md)
- [Oracle compiler](docs/architecture/compiler.md)
- [Typed semantic handlers](docs/architecture/semantic-handlers.md)
- [Runtime components](docs/architecture/runtime-components.md)
- [Reusable rules pieces](docs/architecture/reusable-rules-pieces.md)
- [Trust closure](docs/architecture/trust-closure.md)
- [Dependency and mutation rules](docs/architecture/dependency-rules.md)
- [Replay](docs/architecture/replay.md)
- [Visibility](docs/architecture/visibility.md)
- [Server runtime](docs/architecture/server-runtime.md)
- [Architecture decisions](docs/adr/index.md)

Specialized subsystem documents cover damage, counter placement and drawing.
The [documentation map](docs/index.md) is authoritative when a new maintained
document is added or an old one is retired.
