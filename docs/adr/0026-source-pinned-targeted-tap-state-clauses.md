---
title: "ADR 0026: source-pinned targeted tap-state clauses"
status: "ADR"
authoritative_source: "this decision record and typed targeted tap-state compiler implementation"
verified: "2026-08-06"
audience: "rules, compiler, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0026"
decision_status: "accepted"
date: "2026-08-06"
---

# ADR 0026: source-pinned targeted tap-state clauses

## Context

Direct instructions such as “Tap target creature” occur in spells, triggered
abilities, and activated abilities. The runtime already owns typed tap and
untap transitions, including the represented stun-counter replacement, but the
compiler previously grouped those instructions under broad target and keyword-
action mechanics. That prevented the existing runtime ownership from producing
fine-grained CardProgram trust.

The wider tap/untap family includes modal, optional, quantified, relational,
qualified, aggregate, cost, untap-step, prohibition, and replacement wording.
Those forms do not share this clause's closed target or execution grammar.

## Decision

The compiler lowers exactly one mandatory whole-clause instruction to tap or
untap exactly one target artifact, creature, land, or permanent. It emits a
versioned typed template with one public battlefield target schema, one
`$target.0` operation, precise source provenance, and the fine-grained tap or
untap capability plus resolution-time target revalidation.

Spells, triggers, and activated abilities consume the same template. Action
advertisement, proposal validation, resolution, replacement handling, and
replay use the resulting CardProgram data; runtime code does not parse Oracle
text. The canonical tap-state mutation owner remains the only state writer.

## Alternatives

- Trust the aggregate Tap and Untap mechanic. Rejected because unsupported
  variants and ambient interactions would inherit false coverage.
- Maintain separate parsers for spell, trigger, and activated contexts.
  Rejected because equivalent clauses could drift across execution paths.
- Add reviewed behavior per card. Rejected because the clause is a reusable
  semantic family and source-pinned overrides would not scale.

## Consequences

- Closed direct-target clauses can become capability-closed wherever their
  enclosing cost and trigger dependencies are also closed.
- Target legality is identical when advertised and when revalidated at
  resolution.
- Untap instructions reuse the represented stun-counter replacement; tap
  instructions and no-op transitions preserve canonical public event behavior.
- Optional, modal, aggregate, quantified, relational, qualified, compound,
  cost, untap-step, prohibition, and broader replacement variants remain
  explicit residuals and fail trust closed.

## Removal condition

The narrow template may be generalized only when a larger typed effect-clause
grammar can preserve the same target, capability, replay, and mutation-owner
boundaries. The aggregate mechanic must remain untrusted until its documented
variants and ambient interactions are independently capability-closed.
