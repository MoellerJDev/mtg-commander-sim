---
title: "ADR 0017: prevention continuations and aftermath ownership"
status: "ADR"
authoritative_source: "this decision record and platform/architecture-policy.json"
verified: "2026-08-03"
audience: "rules, semantics, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0017"
decision_status: "accepted"
date: "2026-08-03"
---

# ADR 0017: prevention continuations and aftermath ownership

## Context

ADR 0015 established durable prevention and redirection state, but effect
creation still depended on fixed values and the damage transaction could not
resume a replacement choice discovered while a mana ability was paying for a
cast or activation. CR 609.7a source selection and CR 615.5 immediately-after
results also require seat-scoped choices, stable object identity, exact replay,
and a single precommit boundary.

## Decision

`damage_prevention_creation.py` owns typed shield creation. It validates resolved
dynamic amounts, exact divided allocations, independent per-object shields,
and optional chosen-source physical identity plus LKI before committing durable
state. `damage_prevention_aftermath.py` prepares represented life and permanent-
counter results and delegates mutation to the canonical life and counter owners.

The generic `choose_damage_source` semantic operation is a reviewed universal
choice. It exposes only legally known public battlefield, stack, and face-up
command-zone candidates to the affected seat, pins the accepted physical object
and characteristics, and can continue only into the typed prevention-creation
owner. It grants no arbitrary callback, state mutation, hidden-zone access, or
cross-seat projection authority.

`mana_payment_continuations.py` owns the rollback, suspension, and resumption of
a cast or activation when damage from a mana ability requires a replacement
choice. The continuation stores an exact priority/stack frame and payment
identity. A resumed action discards only the expired offer revision and
fingerprint, then rebuilds the same canonical cast or activation proposal from
current authoritative facts.

The effect runtime separates `damage-modifiers.v1` and `life-effects.v1` from
the former broad damage/life/turn family. Each family has a closed operation
inventory and delegates final mutation to its declared typed owner.

## Alternatives

- Extend the broad public-object chooser with arbitrary continuation effects.
  Rejected because that would grant a generic choice handler more mutation and
  callback authority than source selection requires.
- Keep payment resumption as a new `CommanderEngine` method. Rejected because
  the payment frame and exact action rebuild belong to the mana continuation
  boundary and would enlarge the engine method inventory.
- Store aftermath as untyped effect dictionaries executed after damage.
  Rejected because life/counter replacement, rollback, and replay require typed
  precommit plans validated with the damage batch.

## Consequences

- Dynamic, divided, and per-object prevention resources are replayable and
  independently consumable.
- Same-chooser simultaneous replacement ordering is explicit rather than an
  incidental event-list order.
- Represented prevention aftermath validates every life/counter result before
  mutation and can participate in permanent-counter replacement.
- Mana payments with replacement choices roll back completely and resume the
  original action without adding a CommanderEngine method.
- Oracle IR v16 can lower the represented generic wording while unimplemented
  source categories and aftermath forms remain material residuals.

## Remaining boundary

This decision does not claim complete CR 609.7a, 615, or 616. Referred former-
zone objects, permanent-spell continuity, broader source-property predicates,
general replacement-capable life gain, other aftermath forms, partial/attached
redirection, and non-damage transformations remain blocked.

## Removal condition

The architecture allowance may shrink when the remaining top-level coordination
facades move into stable rules packages. The reviewed source-choice operation
remains only while it is the narrow typed entry point for this universal rule.
