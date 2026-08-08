---
title: "ADR 0033: typed fixed counter placement effects"
status: "ADR"
authoritative_source: "this decision record and typed fixed counter-placement implementation"
verified: "2026-08-07"
audience: "rules, compiler, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0033"
decision_status: "accepted"
date: "2026-08-07"
---

# ADR 0033: typed fixed counter placement effects

## Context

The canonical counter-placement transaction already owns replacement ordering,
authoritative mutation, suspension, rollback, and replay, but ordinary fixed
instructions such as “put a +1/+1 counter on target creature” had no shared
compiler or semantic boundary. Spell, triggered, and activated contexts could
therefore recognize different wording or bypass the canonical transaction.

The wider Oracle family also contains optional, variable, distributed,
set-based, player-counter, multiple-counter-kind, conditional-target, entry,
cost, removal, movement, and rule-generated instructions. Those are not
equivalent to one mandatory positive fixed quantity on one permanent.

## Decision

Add one closed `place_counters` semantic operation. The compiler lowers only a
mandatory positive fixed quantity of one named counter on the source, an exact
named source, or one direct battlefield permanent target. Permanent subjects
use a closed card-type or pinned creature-subtype predicate, an explicit
controller relation, and source exclusion where required. The same immutable,
source-spanned descriptor is shared by spell, triggered, and activated
CardProgram V2 contexts.

The registered runtime handler strictly validates the descriptor and lowers it
to `PlaceCountersIntent`. It is read-only: the canonical counter-placement
transaction remains the sole owner of live target revalidation, quantity
replacement and APNAP choice, suspension, rollback, authoritative mutation,
projection, and replay. Runtime code does not parse Oracle text and contains no
printed-name, collector-number, set-code, or Oracle-ID dispatch.

## Alternatives

- Keep separate `add_counter_selected` compiler paths. Rejected because they
  make effect context, legality, source spans, and dependency closure diverge.
- Let the generic effect executor mutate counter dictionaries. Rejected because
  it would create a second mutation and replacement owner.
- Accept arbitrary target adjectives or counter formulas. Rejected because the
  represented grammar must remain closed and unsupported wording must remain a
  precise residual.

## Consequences

- Fixed permanent-counter effects in all three represented execution contexts
  share one capability, operation shape, runtime handler, and transaction.
- Stale targets fail before mutation, source departure does not invalidate an
  already resolving independent effect, and replacement suspension resumes the
  same identity-pinned intent.
- The handler adds no direct `GameState` write and `CommanderEngine` remains
  flat.
- Optional, variable, distributed, set-based, fixed player-counter,
  multiple-counter-kind, conditional-target, noncreature-subtype, entry, cost,
  removal, movement, and rule-generated variants remain fail-closed residuals.
- Game Record v3 remains structurally unchanged; current compiler, program,
  registry, and runtime fingerprints advance with the represented operation.

## Removal condition

Retire `place_counters` only if a successor typed effect model preserves its
closed grammar, immutable source-spanned descriptor, identity-pinned target,
canonical counter-transaction ownership, capability closure, replay identity,
and fail-closed residuals.
