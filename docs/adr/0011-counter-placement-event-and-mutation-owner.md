---
title: "ADR 0011: counter-placement event and mutation ownership"
status: "ADR"
authoritative_source: "this decision record and platform/architecture-policy.json"
verified: "2026-08-02"
audience: "rules, semantics, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0011"
decision_status: "accepted"
date: "2026-08-02"
---

# ADR 0011: counter-placement event and mutation ownership

## Context

Positive counter instructions mutated permanent counter maps directly inside
the central engine. That made quantity replacement, affected-controller choice,
APNAP traversal, replacement-created counter events, rollback, and exact replay
impossible to enforce at one boundary. ADR 0010 established the immutable
replacement-event tree but intentionally left universal counter placement as
the next producer migration.

## Decision

`counter_placement.py` owns the prepare/commit transaction for represented
effect-generated permanent counters. Preparation resolves object identity,
builds simultaneous typed events, discovers active trusted descriptors, and
completes every replacement choice before mutation. Commit revalidates object
and zone identity, changes only the counter map, and emits canonical audit
records.

`semantic_runtime/counter_replacements.py` owns strict descriptor validation
and immutable fixed integral quantity transformations. It remains pure and has
no authority over `GameState`. The engine implements a narrow host protocol and
keeps compatibility facades while producers migrate incrementally.

A zone replacement that creates counters represents them as nested event-tree
children. The parent is exhausted before the child under CR 616.1g, while all
choices still complete before the original zone mutation. Capabilities remain
tested or blocked outside the represented producer and descriptor families.

## Alternatives

- Apply doubling after a direct counter mutation. Rejected because competing
  replacement order can change the result and must be chosen before the event.
- Put counter mutation inside the runtime component. Rejected because pure
  semantic descriptors cannot become a second authoritative rules engine.
- Migrate every legacy producer immediately. Rejected because producers inside
  partially executed semantic instructions need resumable continuation frames
  before they can safely suspend without duplicating earlier side effects.
- Add printed-card conditionals for known doublers. Rejected because source-
  pinned descriptors and a generic event predicate cover reviewed cards without
  universal-engine name dispatch.

## Consequences

- Represented positive placements have one rollback-safe choice boundary and
  one authoritative commit owner.
- Affected-object choice, APNAP ordering, seat projection, and command replay
  reuse the shared replacement batch.
- Engine physical line count decreases for the migrated paths.
- Remaining counter producers are an explicit architecture inventory rather
  than implied coverage.

## Removal condition

Replace the transitional host port only when a universal typed event
transaction owns all counter producers, including entry events, costs, rule
actions, player counters, and resumable semantic continuations. The successor
must preserve pre-mutation choice, object identity, APNAP, projection privacy,
rollback, and exact replay.
