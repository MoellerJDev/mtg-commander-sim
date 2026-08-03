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
state. New chosen sources use the version-3 identity shape: the current logical
incarnation and zone are pinned, and a chosen permanent spell additionally pins
the same logical incarnation on the battlefield for CR 400.7a/609.7a
continuity. This includes a permanent-spell copy, which is offered by its public
stack identity while its underlying copy-object identity remains authoritative.
A later incarnation with the same physical card ID does not match.
The same snapshot stores one strict canonical `ObjectQuerySpec` instead of
parallel source-filter fields. Historical version-0 through version-2
checkpoint shapes retain their original meaning during Game Record v3 replay.

Chosen-source property filters use the shared object predicate: all/any colors
and required effective card types, subtypes, supertypes, or keywords. The
compiler, choice continuation, and damage-source snapshot recheck share its
strict serialization and evaluator. CR 609.7 identity, visibility, and LKI
provenance remain source-specific. Unknown predicates fail closed.

`damage_prevention_aftermath.py` prepares represented life, permanent-counter,
and source-controller damage results. Life results enter the immutable
`life.change` replacement tree before
mutation and then commit through `life_change.py` plus the mutation-only
`life_state.py` owner. The focused `semantic_runtime/life_replacements.py`
registry supplies ordinary `life.change` replacement effects; life handlers no
longer depend on the damage-result registry. Permanent counters continue
through the canonical counter-placement
owner. Source-controller damage pins a `DamageSourceSnapshot`, derives the
recipient from the prevented event, and prepares a nested `DamageProposal`
against projected modifier state before any outer mutation. This makes
represented CR 615.5 life and damage aftermath replacement-capable while
keeping all result plans validated before the damage batch mutates state.

Independent later sentences are not aftermath. Oracle IR v18 lowers a reviewed
fixed `Prevent ... . You gain N life.` form as two top-level instructions. The
source-choice continuation creates the shield, then resumes the sibling life
instruction in written order. That life change happens during the successful
spell resolution whether or not future damage occurs. Only an explicit
dependency such as `damage prevented this way` lowers into the CR 615.5
aftermath value.

The generic `choose_damage_source` semantic operation is a reviewed universal
choice. It exposes the CR 609.7a universe: public permanents, spells on the
stack, face-up command-zone objects, and public former-zone objects explicitly
referred to by a stack object, waiting typed prevention/replacement value, or
waiting delayed trigger. Typed `referred_object_ids` metadata carries that
provenance; arbitrary semantic context is never searched. The handler pins the
accepted physical object and characteristics and can continue only into the
typed prevention-creation owner. It grants no arbitrary callback, state
mutation, hidden-zone access, or cross-seat projection authority.

`mana_payment_continuations.py` owns the rollback, suspension, and resumption of
a cast or activation when damage from a mana ability requires a replacement
choice. The continuation stores an exact priority/stack frame and payment
identity. A resumed action discards only the expired offer revision and
fingerprint, then rebuilds the same canonical cast or activation proposal from
current authoritative facts.

The effect runtime separates `damage-modifiers.v1` and `life-effects.v2` from
the former broad damage/life/turn family. Each family has a closed operation
inventory and delegates final mutation to its declared typed owner. Version 2
routes general effect life changes through `life.change` before mutation and
records stable event IDs, source/controller/cause, requested/final amounts,
and the canonical replacement journal.

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
- Represented prevention aftermath validates every life/counter/damage result
  before mutation. Nested damage reuses the canonical replacement, prevention,
  result, final-event, and replay paths.
- A source-choice pause preserves every later sibling instruction; fixed
  independent life is neither delayed until shield use nor repeated by it.
- Mana payments with replacement choices roll back completely and resume the
  original action without adding a CommanderEngine method.
- Oracle IR v18 and template
  `damage-prevention-chosen-source-fixed-life-v2` lower the corrected ordered
  sequence without card-name dispatch. The compiler/CardProgram fingerprint
  changes, while a historical v17 artifact retains its pinned historical
  shape and distinct fingerprint.
- Oracle IR v19 and template
  `damage-prevention-source-controller-aftermath-v1` lower the closed
  source-controller-damage family without card-name dispatch. The trusted
  capability is `damage.prevention.aftermath.damage`.
- Oracle IR v20 replaces the parallel chosen-source qualifier fields with the
  strict shared object predicate while preserving historical snapshot replay.

## Remaining boundary

This decision does not claim complete CR 609.7, 615, or 616. Explicit typed
provenance is required for referred former-zone objects; arbitrary opaque
references and face-down source characteristics remain blocked. Source
predicates beyond the closed color/type/
subtype/supertype/keyword vocabulary, life-gain prevention such as `can't gain
life`, non-effect-runtime life producers, aftermath forms beyond represented
life, permanent counters, and source-controller damage, CR 615.13 triggered
prevention results,
partial/attached redirection, and non-damage transformations remain blocked.

## Removal condition

The architecture allowance may shrink when the remaining top-level coordination
facades move into stable rules packages. The reviewed source-choice operation
remains only while it is the narrow typed entry point for this universal rule.
