# Roadmap

The product target is a deterministic, server-authoritative, browser-based
four-player Commander platform. The current 0.8.x line is a rules-kernel,
semantic, protocol, replay, and privacy foundation. It is not a complete
Comprehensive Rules or Oracle implementation and does not yet include a network
server, durable production database, or browser client.

The generated current ledger is
`docs/PLATFORM_IMPLEMENTATION_STATUS.md`.

## Phase 0 — integrate the deterministic foundation

- merge `agent/review-mvp` into `main` through its draft pull request
- merge updated `main` into `agent/rules-completeness` without rewriting history
- retarget and merge the rules branch into `main`
- retain exact replay, privacy, repository, schema, and packaging gates
- remove AI-run games and provider identity from product completion criteria

## Phase 1 — strict command and domain boundaries

- versioned browser command envelopes and strict choice schemas
- server-derived authenticated principals
- idempotent commands and stale revision rejection
- canonical public versus authoritative object identities
- transaction rollback and architecture dependency tests

## Phase 2 — single-writer server and persistence

- `GameManager` with one serialized `GameActor` per active game
- ASGI HTTP/WebSocket gateway
- guest identities, rooms, seats, deck selection, readiness, and lifecycle
- persistence ports with in-memory, SQLite development, and PostgreSQL adapters
- migrations, durable command acknowledgement, checkpoints, reconnect, and
  process-restart recovery

## Phase 3 — browser Commander MVP

- TypeScript browser client generated from versioned schemas
- four-player table, local hand, public zones, stack, combat, decisions, and log
- generic modes, targets, costs, searches, ordering, replacement, trigger, and
  combat choices
- safe yields, reconnect/resync, spectators, accessibility, and independent
  text-forward visual design
- four isolated browser-context end-to-end tests

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
