---
title: "Damage transaction"
status: "current"
authoritative_source: "mtg_commander_sim/damage.py, mtg_commander_sim/damage_values.py, mtg_commander_sim/damage_results.py, mtg_commander_sim/fixed_damage_set*, and mtg_commander_sim/combat_damage_*"
verified: "2026-08-07"
audience: "rules, semantics, replay, and architecture contributors"
maintenance: "hand-maintained"
---

# Damage transaction

All represented combat and noncombat damage uses one prepare-and-commit
transaction. Producers submit immutable source, recipient, amount, and event
identity values. `damage.py` coordinates preparation; `damage_results.py` owns
normalized CR 120.3 result materialization, commit planning, and authoritative
result mutation.

```mermaid
flowchart LR
    Producer["Combat or typed effect"] --> Proposal["Immutable proposal batch"]
    Proposal --> Replace["Quantity and redirection replacements"]
    Replace --> Prevent["Prevention"]
    Prevent --> Results["Normalized result events"]
    Results --> Plan["Validated atomic commit plan"]
    Plan --> State["Authoritative mutation owners"]
```

## Proposal and preparation

Combat snapshots freeze the relevant public relationships and effective
characteristics before a pilot decision is issued. Assignment validation owns
legal recipients, totals, canonical source and recipient order, lethal
thresholds, and trample spill. Client JSON order is never authoritative.
Noncombat producers use the same immutable damage values and stable physical
or logical source identities.

Fixed simultaneous affected-set instructions compile to an immutable ordered
group descriptor. `fixed_damage_set_model.py` owns its closed player and
permanent vocabulary; `fixed_damage_set.py` materializes current public
effective-characteristic rows through a narrow query port. The snapshot uses
APNAP controller order plus stable logical object identity, excludes phased-out
objects, and deduplicates overlapping groups before creating proposals. Every
recipient then enters one `resolve_damage_batch` call, so replacement,
prevention, result, trigger, rollback, and replay behavior cannot diverge from
single-target or combat damage.

Preparation discovers applicable runtime components against the current
event, validates the affected player or permanent controller, records any
replacement choices, and rediscoveries after each transformation. Redirection
substitutes a complete recipient value before the loop continues. Prevention
then consumes the resulting event through the separate
[prevention transaction](prevention.md).

## Results and commit

Only positive final damage produces result events. The result planner derives
the typed consequences for life, marked damage, defense, loyalty, commander
damage, lifelink, deathtouch, infect, wither, toxic, and other represented
families. It validates all recipients and source snapshots before any state
changes. The commit is atomic; a malformed event or stale continuation leaves
the state unchanged.

State-based actions consume temporal damage markers according to their own
owner. Damage code does not perform unrelated state-based checks or bypass
focused life, counter, or permanent-state mutation boundaries.

## Replay, privacy, and extension

Event IDs derive from stable damage-step, source-incarnation, recipient, and
amount values rather than submission order. Continuations persist the option
set, chooser, selections, and projected modifier state. A seat sees only
authorized option labels and public facts; immutable event payloads remain in
the authoritative continuation. Replay rebuilds the transaction and must reach
the same state hash.

Add a damage family by defining a typed descriptor and immutable operation,
registering exact capability dependencies, integrating it at one transaction
stage, and adding multiplayer ordering, rollback, privacy, replay, and mutation
witnesses. Card-name or Oracle-ID branches are not permitted in the generic
transaction.

The fixed-set grammar currently covers positive fixed damage to closed player,
creature, planeswalker, opponent-controlled, flying, color-qualified,
nonartifact, nontoken, and shadow sets. Divided or variable damage, negative
keyword or subtype predicates, multiple independent damage instructions,
unpreventable wording, and linked life/draw/scry/conditional riders remain
compiler residuals. Do not widen the runtime query to approximate them.

See [ADR 0012](../adr/0012-damage-transaction-and-static-prevention.md),
[ADR 0013](../adr/0013-damage-result-event-ownership.md),
[ADR 0015](../adr/0015-durable-damage-modifier-ownership.md), and
[ADR 0017](../adr/0017-prevention-continuations-and-aftermath.md).
