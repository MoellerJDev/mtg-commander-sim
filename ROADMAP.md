---
title: "Roadmap"
status: "target"
authoritative_source: "current standalone platform objective"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "maintainers and contributors"
maintenance: "hand-maintained"
---

# Roadmap

The product target is a deterministic, server-authoritative, browser-based
four-player Commander platform. The current 0.8.x line is a rules-kernel,
semantic, protocol, replay, and privacy foundation. It is not a complete
Comprehensive Rules or Oracle implementation. The first single-node network,
SQLite, and browser vertical slice is implemented; production database and
operations work plus complete generic browser choice forms remain open.

The generated current ledger is
`docs/PLATFORM_IMPLEMENTATION_STATUS.md`.

## Phase 0 — integrate the deterministic foundation

- [x] merge `agent/review-mvp` into `main` through an ordinary merge commit
- [x] merge updated `main` into `agent/rules-completeness` without rewriting history
- [x] retarget and merge the rules branch into `main`
- [x] retain exact replay, privacy, repository, schema, and packaging gates
- [x] remove AI-run games and provider identity from product completion criteria
- [x] integrate the reviewed CR 400–408 and CR 500–512 slices into `main` while
  preserving ancestry-proven intermediate work; pull-request chronology is
  retained in the changelog rather than this target plan
- [x] verify the combined source tree under the complete local gate and public
  Python 3.11/3.12 Ubuntu/Windows GitHub matrix

The immediate product milestone combines the former phases 1–3 into one
authoritative server/browser vertical slice. It must prove strict commands,
idempotency, expected revisions, one serialized game writer, guest room/seat
flow, principal-scoped WebSocket projection, reconnect, and a four-context
browser test before broad CR-number traversal resumes.

## Phase 1 — strict command and domain boundaries

- [x] versioned browser command envelopes and strict choice schemas
- [x] server-derived authenticated principals
- [x] idempotent commands and stale revision rejection
- [x] canonical public versus authoritative object identities
- [x] transaction rollback and architecture dependency tests

## Phase 2 — single-writer server and persistence

- [x] `GameManager` with one serialized `GameActor` per active game
- [x] ASGI HTTP/WebSocket gateway
- [x] guest identities, rooms, seats, deck selection, readiness, and lifecycle
- [ ] persistence ports with SQLite development implemented; PostgreSQL remains
- [x] migrations, durable command acknowledgement, checkpoints, reconnect, and
  process-restart recovery

## Phase 3 — browser Commander MVP

- [x] TypeScript browser client generated from versioned schemas
- [x] four-player table, local hand, public zones, stack, and ordinary decisions
- [ ] generic modes, targets, costs, searches, ordering, replacement, trigger, and
  combat choices
- [ ] safe yields, reconnect/resync, and the text-forward visual design are
  implemented; spectators and complete accessibility remain
- [x] four isolated browser-context end-to-end test

## Phase 4 — rules and Oracle expansion

- dependency-ordered Comprehensive Rules conformance families
- typed events, universal replacement/prevention, layers, triggers, state-based
  actions, casting/costs, combat, card forms, and Commander multiplayer
- typed Oracle compilation, reviewed overrides, rulings linkage, and source-hash
  invalidation
- trusted-only declared pools first, then Commander-legal corpus expansion

## Phase 5 — deterministic assurance and operations

- property, seeded fuzz, mutation, protocol, browser, load, and soak suites
- security threat model, legal/content boundary, dependency audit, and
  observability without private-state leakage
- containerized reproducible development and single-node deployment
- performance baselines and regression budgets that never suppress legal
  actions

Existing scripted, manual, subprocess, and optional AI adapters may continue to
use the ordinary public protocol. No AI system is required for gameplay,
legality, testing, persistence, replay, merge gates, or releases.

No roadmap phase modifies either pinned regression deck based on test results or
promotes a duplicate-list fixture to matchup evidence.
