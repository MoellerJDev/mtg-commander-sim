---
title: "Damage prevention"
status: "current"
authoritative_source: "mtg_commander_sim/damage_prevention.py, mtg_commander_sim/damage_prevention_creation.py, mtg_commander_sim/damage_prevention_aftermath.py, and mtg_commander_sim/semantic_runtime/damage_replacements.py"
verified: "2026-08-06"
audience: "rules, semantics, replay, and architecture contributors"
maintenance: "hand-maintained"
---

# Damage prevention

Prevention is a stage of the canonical [damage transaction](damage.md), with a
separate owner for durable modifier state. Static effects participate through
immutable runtime components. Finite and next-instance shields, chosen-source
effects, redirections, and represented aftermath use typed creation,
application, and result transactions.

## Modifier lifecycle

`damage_prevention_creation.py` validates a typed request, performs any
source choice, and creates a source-stamped modifier through the focused
mutation owner. Public source candidates may be projected to the chooser;
private state and opaque object references remain authoritative only.
Physical and logical identity rules determine whether a later object is still
the chosen source.

During damage preparation, `damage_prevention.py` discovers applicable
modifiers, applies affected-player ordering, allocates bounded amounts, and
produces a mutation-only commit plan. Unpreventable damage does not consume a
shield. Finite modifiers retain their exact remainder across events; expired
or exhausted modifiers are removed by their declared lifecycle owner.

Preparation and commit are separated. A continuation fingerprints the damage
event, available amount, source snapshot, modifier set, chooser, and prior
journal. If any input drifts before resume, validation fails without partial
mutation.

## Aftermath and ordering

Only wording explicitly dependent on damage "prevented this way" enters the
aftermath transaction. Independent later instructions remain ordinary ordered
siblings. Typed aftermath can route represented life, counter, or nested
damage results through those subsystems' canonical replacement-aware
transactions. Triggered prevention aftermath requiring a stack object remains
a trigger concern, not an implicit immediate effect.

Competing prevention effects follow the affected-player ordering rules and are
rediscovered after each application. Simultaneous events preserve APNAP and
same-chooser order in replay. Mana-payment and semantic-choice continuations
resume the exact original action after the prevention decision.

## Boundary

Runtime components and handlers never mutate shield state directly. Generic
code does not recognize card names or Oracle IDs. New prevention grammar must
compile to typed descriptors with exact predicates, provenance, duration, and
capability dependencies; unsupported predicates and aftermath forms stay
material residuals.

See [ADR 0012](../adr/0012-damage-transaction-and-static-prevention.md),
[ADR 0015](../adr/0015-durable-damage-modifier-ownership.md), and
[ADR 0017](../adr/0017-prevention-continuations-and-aftermath.md).
