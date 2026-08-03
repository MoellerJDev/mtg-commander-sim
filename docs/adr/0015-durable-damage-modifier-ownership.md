---
title: "ADR 0015: durable damage-modifier ownership"
status: "ADR"
authoritative_source: "this decision record and platform/architecture-policy.json"
verified: "2026-08-02"
audience: "rules, semantics, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0015"
decision_status: "accepted"
date: "2026-08-02"
---

# ADR 0015: durable damage-modifier ownership

## Context

ADR 0012 established an immutable damage transaction but represented only
ephemeral static prevention. Finite shields, next-instance shields, shield
consumption, and persistent redirection need state that survives priority
windows while remaining choice-complete and replay-pinned. Keeping that state
inside CommanderEngine would enlarge its combat method and create another
string-based mutation path.

## Decision

`damage_modifier_state.py` owns the validated, serialization-safe domain
values without importing the rules layer. `damage_prevention.py` is a
rules-layer owner beneath `damage.py`; it owns replacement lowering, the
immutable commit plan, stale-plan fingerprint, consumption, and cleanup
expiration. It may mutate only its dedicated GameState collections through
that commit boundary.

`damage.py` owns proposal creation and invokes the modifier owner before CR
120.3 result commit. Combat proposal materialization also moves into this
subsystem, leaving CommanderEngine with choice suspension and orchestration.
Runtime JSON descriptors lower to the typed modifier vocabulary before play;
neither owner knows printed card names.

The generic semantic operations `create_damage_prevention_shield` and
`create_damage_redirection` are reviewed universal operations. They create
typed state through the effect-runtime owner and do not grant callbacks, raw
GameState access, or arbitrary mutation authority.

Game Record v3 remains structurally compatible. Modifier state is serialized
additively in checkpoints, modifier choices use canonical replacement journals,
and prepared commits reject changed state before mutation.

## Alternatives

- Recreate shields from Oracle text at each damage event. Rejected because
  partial consumption and exact replay require durable identity.
- Store modifier dictionaries in CommanderEngine. Rejected because validation,
  mutation ownership, and versioning would remain implicit.
- Treat redirection as arbitrary replacement callbacks. Rejected because the
  runtime vocabulary must remain closed and deterministic.

## Consequences

- Finite and next-instance prevention can be consumed exactly once across
  damage events, while unpreventable damage preserves the shield.
- Static full-recipient redirection is replayable and validated before result
  mutation.
- Empty damage batches still carry a pinned modifier plan, preventing a default
  plan from being mistaken for stale state.
- CommanderEngine loses combat-proposal construction and the architecture
  ratchet records the two reviewed universal operations.

## Removal condition

The compatibility facade may disappear after all internal consumers import the
decomposed replacement and damage owners directly. ADR 0017 adds represented
chosen-source selection, divided shields, prevention aftermath, and mana-
payment continuations; the capability remains partial until complete CR 609.7a
source continuity, general replacement-capable aftermath life gain, remaining
aftermath forms, and broader prevention/redirection grammar are certified.
