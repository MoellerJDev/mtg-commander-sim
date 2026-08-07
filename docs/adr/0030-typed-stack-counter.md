---
title: "ADR 0030: typed direct stack-counter ownership"
status: "ADR"
authoritative_source: "this decision record and typed stack-counter implementation"
verified: "2026-08-07"
audience: "rules, compiler, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0030"
decision_status: "accepted"
date: "2026-08-07"
---

# ADR 0030: typed direct stack-counter ownership

## Context

The engine could remove stack objects, but generated CardPrograms had no
closed, reusable direct-counter instruction. A reviewed pack represented one
specific counter spell, the general effect runtime retained an untyped
operation, and counterability inspected Oracle text during a transition.
Those paths could not safely promote the common mandatory “Counter target …”
family or prove that advertised stack targets and accepted commands shared one
legality boundary.

Counter rules also include conditional payments and actions, optional and
modal instructions, qualified targets, multiple or mass targets, replacement
destinations, rule-generated stack removal, and dynamic prohibitions. Those
families are outside this decision.

## Decision

One focused stack-counter owner performs represented counterability checks,
canonical stack removal, ordinary countered-spell movement, telemetry, and
public journaling behind a narrow host protocol. `CommanderEngine` retains a
compatibility facade but no longer owns that sequence.

The compiler lowers only complete mandatory direct clauses over a closed list
of spell, activated-ability, and triggered-ability target domains. Every
schema excludes the resolving source's own stack object and uses the existing
resolution-time target revalidation boundary. A strict semantic handler emits
one typed `CounterStackIntent`; it cannot choose an alternate destination or
access mutable state.

The exact complete sentence “This spell can't be countered” is a separate
stack-active capability declaration. Cast commit consumes only a current
trusted CardProgram declaration and pins the result to the created stack
object. Runtime Oracle-text parsing is not an authority.

The generated runtime registry materializes that closed static declaration;
it is not merely an Oracle-coverage fact. A separate immutable stack-resolution
query recognizes an exact spell with no executable resolution node and plans
its empty resolution. This keeps capability-only spells out of arbiter fallback
without adding another decision path to `CommanderEngine`.

## Alternatives

- Extend the string-based general effect switch. Rejected because target
  exactness, counterability, stack mutation, and replay would retain competing
  owners.
- Treat every sentence containing “counter target” as equivalent. Rejected
  because conditions, qualifications, destinations, and linked results change
  legality and resolution.
- Continue reading Oracle text from a spell on the stack. Rejected because the
  compiler and runtime could disagree, and historical replay would depend on
  live interpretation rather than the pinned CardProgram.

## Consequences

- Generated spells, triggers, and activated abilities share one source-spanned
  instruction and one target/capability shape.
- Countered abilities leave the stack without moving a physical card;
  countered physical spells use the existing canonical zone-transition owner.
- Exact intrinsic prohibitions participate in capability closure and replay
  fingerprints. An exact capability-only spell resolves as a verified no-op
  to its ordinary destination. Conditional and granted prohibitions remain
  fail-closed.
- The broad Counter keyword action remains untrusted. Conditional-payment,
  optional, modal, aggregate, linked-result, alternate-destination, and other
  unsupported variants remain material residuals.
- Game Record v3 remains additive: existing stack context and event shapes are
  preserved, while generated-program fingerprints change with compiler v42.

## Removal condition

The grammar may widen only through another typed family that preserves closed
target predicates, exact source spans, source exclusion, resolution-time
revalidation, canonical stack and zone mutation, and deterministic replay.
The compatibility engine facade may be removed when all legacy callers use the
focused owner directly.
