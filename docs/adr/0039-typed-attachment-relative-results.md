---
title: "ADR 0039: typed attachment-relative result references"
status: "ADR"
authoritative_source: "this decision record and quorune/attachment_references.py"
verified: "2026-08-08"
audience: "rules, compiler, replay, privacy, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0039"
decision_status: "accepted"
date: "2026-08-08"
---

# ADR 0039: typed attachment-relative result references

## Context

Some otherwise ordinary spell, triggered-ability, and activated-ability
results refer to the permanent a source enchants, equips, or fortifies. The
fixed counter transaction from ADR 0033 can already place the result, but a
plain `$source` or direct target cannot represent CR 113.7a and 608.2h. The
source can remain and become attached to another object before resolution, or
it can leave after the ability is created and require last-known information.
Re-reading Oracle text at resolution would create a second rules authority and
would not pin either physical incarnation.

## Decision

The compiler emits an immutable `AttachmentReferenceSpec` only when the exact
parsed source subtype and wording agree: Aura with “enchanted,” Equipment with
“equipped,” or Fortification with “fortified.” The descriptor also pins one
closed required permanent card type. Ambiguous source subtypes, mismatched
relations, dynamic qualities, players, and nonbattlefield cards remain
residuals.

When an activated ability is committed, the coordinator captures the source
and attached-object physical, logical, and public identities before costs are
paid. Trigger discovery captures the same facts before enqueueing, using its
existing departure snapshot when the source is represented by last-known
information. The stack context serializes that typed snapshot.

At resolution, the read-only resolver uses the current reciprocal relation if
the same source incarnation remains on the battlefield. If that incarnation
left, it uses the pinned relation, but only while the attached object is still
the same phased-in battlefield incarnation and has the required effective card
type. It returns a public reference to the existing typed effect handler; it
does not mutate state. The fixed counter handler and counter transaction remain
the only owners of placement and replacement ordering.

## Consequences

- Reattachment before resolution follows the live source relation.
- Source departure uses one deterministic last-known relation.
- A target that leaves and returns is a new object and receives no stale
  result.
- Malformed descriptors or stack snapshots fail before result mutation.
- Copies of stack objects preserve the pinned context through ordinary stack
  serialization.
- Authoritative physical and logical identities remain outside seat
  projections; exact replay validates the serialized context.
- Attachment creation, legality, movement, dynamic predicates, and broader
  “object formerly attached” grammar remain separate capabilities.

## Alternatives

- Parse “enchanted creature” from Oracle text during resolution. Rejected
  because runtime text interpretation would compete with CardProgram.
- Snapshot only the target public reference. Rejected because zone changes can
  reuse a physical card reference for a new logical object.
- Always use the activation-time target. Rejected because a source that
  remains can legally move to another attachment before its ability resolves.
- Add an attachment-specific counter mutation. Rejected because the existing
  counter transaction already owns the result.

## Removal condition

Replace this boundary only with a more general typed object-reference system
that preserves compile-time source-role validation, current-versus-LKI
selection, physical and logical identity, required effective characteristics,
pre-cost and pre-enqueue capture, privacy, rollback, and exact replay.
