---
title: "ADR 0036: typed fixed affected-set counter placement"
status: "ADR"
authoritative_source: "this decision record and typed fixed affected-set counter implementation"
verified: "2026-08-08"
audience: "rules, compiler, replay, privacy, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0036"
decision_status: "accepted"
date: "2026-08-08"
---

# ADR 0036: typed fixed affected-set counter placement

## Context

The canonical counter-placement transaction already owns replacement ordering,
authoritative permanent-counter mutation, suspension, rollback, and replay.
The fixed single-permanent and player-counter compilers do not represent
ordinary instructions such as “put a +1/+1 counter on each creature you
control.” Treating each matching permanent as a separate semantic instruction
would lose the shared resolution-time set snapshot and canonical batch.

The wider Oracle family contains variable, optional, distributed, linked,
conditional, compound, history-dependent, combat-dependent, and counter-defined
sets. Those instructions are not equivalent to one mandatory fixed quantity on
one closed public battlefield set.

## Decision

Add one closed `place_counters_on_set` semantic operation. Compile only one
positive exact integer of one counter kind applied to an immutable
`AffectedPermanentSetSpec`. The represented grammar permits a bounded public
type, one pinned subtype, or one reviewed quality predicate, combined with the
controller, opponents, one direct player target, or an unrestricted controller
relation. Spell, triggered, and activated CardProgram V2 contexts share the
same source-spanned descriptor.

At resolution, a narrow read-only query snapshots matching public permanents in
APNAP and stable logical-identity order. The strict handler emits
`PlaceCountersOnSetIntent`; the existing canonical `place_counters` transaction
then owns replacement choices and the atomic authoritative commit. The new
family does not parse Oracle text at runtime, inspect hidden zones, mutate
`GameState` directly, or dispatch on card identity.

## Alternatives

- Emit one independent direct-target counter effect per matching permanent.
  Rejected because it would not preserve one canonical affected set or batch.
- Add an unrestricted runtime object-query DSL. Rejected because it would
  advertise unreviewed predicates and create a second rules authority.
- Add printed-name overrides for representative cards. Rejected because the
  wording family is reusable across spells, triggers, and activated abilities.

## Consequences

- Fixed affected-set placement shares the existing counter replacement,
  mutation, rollback, replay, and journal owners.
- Target-player selection remains seat-scoped and is revalidated before any
  mutation; empty matching sets resolve without manufacturing a decision.
- Compiler and capability closure share one exact predicate-shape validator.
- The generic grammar contains keyword names that happen also to be printed
  card names; their reviewed specificity entries describe predicates, never
  card-identity dispatch.
- Variable, optional, distributed, linked, conditional, compound,
  counter-defined, combat-dependent, entry-history, face-down, colorless, and
  negative or disjunctive sets remain material fail-closed residuals.
- Game Record v3 and public protocol schemas remain structurally unchanged;
  compiler, registry, and runtime-handler fingerprints advance.

## Removal condition

Retire `place_counters_on_set` only if a successor typed effect model preserves
the closed compiler grammar, immutable public set snapshot, canonical APNAP and
logical-identity ordering, target revalidation, replacement suspension,
counter-transaction ownership, privacy, exact replay, and precise residuals.
