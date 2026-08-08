---
title: "ADR 0035: typed fixed player-counter placement"
status: "ADR"
authoritative_source: "this decision record and typed fixed player-counter implementation"
verified: "2026-08-07"
audience: "rules, compiler, replay, privacy, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0035"
decision_status: "accepted"
date: "2026-08-07"
---

# ADR 0035: typed fixed player-counter placement

## Context

The canonical counter-placement transaction already owns player counters,
replacement ordering, authoritative mutation, suspension, rollback, and replay.
However, ordinary fixed instructions such as “you get two energy counters” or
“each opponent gets a poison counter” had no shared compiler and runtime
boundary. Spell, triggered, and activated contexts could therefore recognize
different wording or bypass the canonical transaction.

The wider Oracle family includes variable, optional, distributed, conditional,
cost, removal, movement, replacement, and multiple-counter-kind instructions.
Those are not equivalent to one mandatory positive fixed quantity of one
counter kind for a closed player set.

## Decision

Add one closed `place_player_counters` semantic operation. The compiler lowers
only a mandatory positive exact integer of one named counter for the source
controller, one direct player target, each active player, or each active
opponent. Energy and ticket symbols lower to the same canonical representation
as their named forms. The same immutable, source-spanned descriptor is shared
by spell, triggered, and activated CardProgram V2 contexts.

The registered runtime handler strictly validates the descriptor and lowers it
to `PlacePlayerCountersIntent`. It determines multiplayer subjects in canonical
APNAP order and revalidates direct player targets. It is read-only: the
canonical counter-placement transaction remains the sole owner of replacement
ordering, suspension, rollback, authoritative mutation, projection, poison
state-based actions, and replay. Runtime code does not parse Oracle text and
contains no printed-name, collector-number, set-code, or Oracle-ID dispatch.

## Alternatives

- Mutate player counter dictionaries in the generic semantic executor.
  Rejected because that would create a second replacement and mutation owner.
- Introduce an arbitrary player-query language. Rejected because the current
  Oracle family needs a small closed seat-relative vocabulary and broader
  predicates would overstate capability closure.
- Treat player-counter quantity replacements as part of this capability.
  Rejected because producing an event and replacing its quantity are separate
  trust boundaries.

## Consequences

- Fixed player-counter effects in three represented execution contexts share
  one capability, operation shape, runtime handler, and transaction.
- Direct targets remain seat-scoped, affected sets are APNAP-canonical, and a
  source may leave before its already resolving independent result.
- Poison counters use the existing player-counter and state-based-action paths;
  other counter kinds remain ordinary typed player counters.
- Variable, optional, distributed, conditional, cost, removal, movement,
  multiple-counter-kind, and unsupported replacement variants remain precise
  fail-closed residuals.
- Game Record v3 and public protocol schemas remain structurally unchanged;
  current compiler, program, registry, and semantic-handler fingerprints
  advance with the represented operation.

## Removal condition

Retire `place_player_counters` only if a successor typed effect model preserves
its closed grammar, immutable source-spanned descriptor, seat-relative subject
scope, canonical APNAP ordering, target revalidation, counter-transaction
ownership, privacy, exact replay, and fail-closed residuals.
