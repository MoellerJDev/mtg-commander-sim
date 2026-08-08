---
title: "ADR 0037: typed fixed target-set counter placement"
status: "ADR"
authoritative_source: "this decision record and typed fixed target-set counter implementation"
verified: "2026-08-08"
audience: "rules, compiler, replay, privacy, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0037"
decision_status: "accepted"
date: "2026-08-08"
---

# ADR 0037: typed fixed target-set counter placement

## Context

The canonical counter transaction and the fixed affected-set coordinator own
simultaneous replacement ordering and mutation for public battlefield sets.
They do not represent instructions such as “put a +1/+1 counter on each of up
to two target creatures.” A target set is chosen when the spell or ability is
put on the stack, may be empty because of “up to,” and must be revalidated as
individual targets when the instruction resolves.

The surrounding Oracle family includes Support, variable or distributed
amounts, subtypes, combat or counter qualifications, modal and conditional
clauses, and additional linked results. Those forms are not equivalent to one
bounded direct target set.

## Decision

Add one closed `place_counters_on_targets` semantic operation. Compile only one
positive exact quantity of one named counter applied to each member of an
“each of up to N target” set. The represented target grammar permits one
permanent type, an optional controller relation, and the reviewed
noncreature-artifact predicate. Spell, triggered, and activated CardProgram V2
contexts share the same source-spanned descriptor.

At resolution, ordinary target revalidation first removes illegal targets or
counters the instruction when its originally selected nonempty target set has
become wholly illegal. A narrow read-only query then freezes the remaining
public identities in APNAP-controller and logical-object order. The strict
handler emits `PlaceCountersOnTargetsIntent`; the existing `place_counters`
transaction owns quantity replacement choices and atomic mutation.

The coordinator permits an empty submitted set, rejects duplicate or excessive
refs and malformed identities before mutation, and never parses Oracle text or
dispatches on card identity at runtime.

## Alternatives

- Reuse the affected-set operation. Rejected because an affected set is
  determined at resolution, while a target set is chosen earlier and carries
  target legality rules.
- Emit one unrelated single-target effect per selected permanent. Rejected
  because it would lose one canonical simultaneous replacement batch and
  stable continuation identity.
- Implement Support in the same parser. Rejected because a permanent source
  excludes itself while an instant or sorcery source does not; that requires a
  source-context-aware keyword lowering boundary.

## Consequences

- Advertised target schemas and accepted commands share the same closed
  maximum, type, controller, and negative-type predicates.
- Zero selections, partial target illegality, and all-targets-illegal behavior
  remain explicit and independently tested.
- Replacement suspension serializes the selected refs and maximum exactly;
  replay restores the same typed intent without exposing continuation internals
  to another seat.
- Game Record v3 and public protocol schemas remain structurally unchanged;
  compiler, registry, evidence, and runtime-handler fingerprints advance.
- Support, variable, distributed, subtype-qualified, combat-qualified,
  counter-qualified, modal, conditional, compound, and multi-counter target
  sets remain material fail-closed residuals.

## Removal condition

Retire `place_counters_on_targets` only if a successor typed effect model
preserves the closed target grammar, distinct bounded refs, zero-target
semantics, resolution-time legality, immutable APNAP/logical-identity snapshot,
single replacement-aware counter batch, privacy, exact replay, and precise
residuals.
