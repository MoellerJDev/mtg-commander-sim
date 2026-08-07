---
title: "ADR 0031: typed fixed affected-set damage"
status: "ADR"
authoritative_source: "this decision record and typed fixed damage-set implementation"
verified: "2026-08-07"
audience: "rules, compiler, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0031"
decision_status: "accepted"
date: "2026-08-07"
---

# ADR 0031: typed fixed affected-set damage

## Context

The canonical damage transaction already handled single recipients and every
opponent, but common instructions such as “deals 2 damage to each creature”
had no typed affected-set owner. Extending the legacy effect switch or emitting
one unrelated operation per recipient would let compiler wording, effective
characteristics, replacement ordering, and replay identity diverge.

The wider Oracle family also contains divided and variable damage, negative
keyword and subtype predicates, multiple damage clauses, dynamic conditions,
unpreventable wording, and linked life, draw, or scry results. Those are not
equivalent to a fixed simultaneous affected set.

## Decision

Add one closed `damage_fixed_set` semantic operation. Its strict handler lowers
JSON-compatible ordered groups into one immutable `FixedDamageSetSpec` and one
typed intent. Player groups use an all-or-opponents relation. Permanent groups
use the complete canonical `ObjectQuerySpec` plus an explicit any, opponents,
or target-player controller relation.

At resolution a narrow read-only query port materializes public effective
battlefield facts. The affected-set owner orders them by APNAP controller and
stable logical identity, excludes phased-out objects, deduplicates overlapping
groups, and freezes the result. Every recipient becomes a proposal in one call
to the existing canonical damage transaction. The damage owner remains the
only mutation boundary.

The compiler lowers only complete positive fixed clauses covered by this
descriptor. Runtime code never parses Oracle text and contains no card-name or
Oracle-ID behavior.

## Alternatives

- Extend `damage_each_opponent` with optional permanent filters. Rejected
  because unrelated nullable fields would form an open operation DSL.
- Resolve one recipient at a time. Rejected because simultaneous replacement,
  prevention, result, trigger, rollback, and replay behavior would be wrong.
- Treat arbitrary adjectives before “creature” as subtypes or qualities.
  Rejected because unsupported grammar must remain a precise residual.

## Consequences

- Fixed mass damage shares source snapshots, replacement and prevention
  ordering, result events, state-based consequences, privacy, and replay with
  every other represented damage producer.
- Equivalent object enumeration order produces the same snapshot fingerprint
  and per-recipient event identities.
- The closed compiler grammar can promote common player, creature,
  planeswalker, opponent-controlled, flying, color-qualified, nonartifact,
  nontoken, and shadow affected sets.
- Divided or variable amounts, negative predicates, independent multiple
  clauses, unpreventable wording, and linked riders remain fail-closed
  residuals.
- Game Record v3 remains structurally unchanged; generated program and compiler
  fingerprints advance because the new operation is part of current semantics.

## Removal condition

Retire the operation only if a more general typed effect model preserves the
same closed query vocabulary, immutable affected-set snapshot, one-batch
commit, capability closure, replay identities, and fail-closed residuals.
