---
title: "ADR 0028: typed return-to-owner-hand transaction"
status: "ADR"
authoritative_source: "this decision record and typed return-to-owner-hand implementation"
verified: "2026-08-07"
audience: "rules, compiler, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0028"
decision_status: "accepted"
date: "2026-08-07"
---

# ADR 0028: typed return-to-owner-hand transaction

## Context

Returning a permanent to a hand was represented by the generic effect
dispatcher. The operation lacked an immutable physical/logical identity
snapshot, a single owner/control rule boundary, strict compiler closure, and a
typed result that retained destination-replacement outcomes. That made runtime
acceptance broader than the compiler's evidence and left replay and privacy
properties implicit.

The broader return family includes self-return, graveyard recursion,
reanimation, mass or multi-target instructions, costs, optional and modal
effects, qualified targets, linked results, and controller-hand wording. Those
families are not closed by this decision.

## Decision

One typed transaction owns represented direct-target battlefield returns. It
prepares an immutable request pinned to the permanent's physical and logical
identity, owner, controller, public zone, and phasing state. Commit rejects a
stale plan before mutation, then delegates the requested move to the canonical
replacement-aware zone-change owner. The typed result records the actual
destination after replacement while preserving the owner and origin
controller snapshot.

The compiler lowers exactly one mandatory whole-clause instruction returning
one target artifact, creature, enchantment, land, nonland permanent,
permanent, artifact or enchantment, or creature or planeswalker to its owner's
hand. Spell, trigger, and activated contexts use the same source-spanned
CardProgram node and capability. Runtime code never reparses Oracle text or
branches on card identity.

## Alternatives

- Keep the operation in generic effect dispatch. Rejected because resolution,
  replacement, rollback, and replay would continue to have competing owners.
- Treat the current controller as the destination player. Rejected because a
  card can only enter its owner's hand under the represented rule boundary.
- Promote every Oracle sentence containing “return.” Rejected because zone,
  object, choice, quantity, and ownership variants are materially distinct.

## Consequences

- Advertised direct-target return actions and accepted commands share one
  strict target schema and resolution-time revalidation path.
- Control changes do not change the destination owner; control or identity
  changes after preparation make the plan stale.
- Destination replacements remain owned and journaled by the zone-change
  transaction, and the result reports the committed destination.
- A public permanent entering a hidden hand receives the repository's existing
  seat-scoped known-object projection without exposing other hand contents.
- Graveyard, reanimation, mass, multi-target, optional, modal, conditional,
  qualified, cost, self-return, controller-hand, and compound forms remain
  explicit residuals.

## Removal condition

The grammar may widen only through another typed clause family that preserves
exact source spans, closed target and zone semantics, precommit identity
validation, canonical replacement-aware mutation, replay identity, and
seat-scoped hidden-zone projection. The aggregate mechanic remains untrusted
until each applicable variant is capability-closed.
