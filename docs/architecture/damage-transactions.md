---
title: "Damage transaction"
status: "current"
authoritative_source: "mtg_commander_sim/damage.py, damage_prevention.py, damage_prevention_creation.py, damage_prevention_aftermath.py, damage_results.py, life_change.py, life_state.py, object_predicate.py, object_query.py, mana_payment_continuations.py, replacement/, semantic_runtime/damage_replacements.py, semantic_runtime/damage_results.py, semantic_runtime/life_replacements.py, ADR 0012, ADR 0013, and ADR 0017"
verified: "2026-08-03"
audience: "rules, semantics, replay, and architecture contributors"
maintenance: "hand-maintained"
---

# Damage transaction

`damage.py` coordinates represented damage proposals, quantity replacement,
prevention, and normalized final events. `damage_results.py` is the sole owner
of represented CR 120.3 result materialization, validation, commit planning,
and authoritative result mutation. Combat, semantic single-target damage,
semantic each-opponent damage, and damage produced by represented mana
abilities use the same transaction.

The transaction has six explicit stages:

1. Snapshot the source and recipient identities and relevant characteristics.
2. Build immutable positive `damage` events and discover active trusted
   replacement/prevention components against the pre-mutation state.
3. Apply forced damage effects or suspend an affected-player/controller choice
   before mutation.
4. Group every simultaneous life, poison, -1/-1, marked-damage, loyalty,
   defense, lifelink, toxic, and nested replacement result beneath immutable
   affected-player or affected-permanent `damage.results` roots. Resolve the
   containing event before its contained result events.
5. Validate every result and object incarnation, build mutation-only result,
   modifier, life-aftermath, counter-aftermath, and nested damage-aftermath
   plans, and commit the complete batch atomically.
6. Publish one final `DamageEvent` for each positive proposal and one aggregate
   prevention-aftermath event per applied shield instruction. Fully prevented
   damage remains in the audit result but does not dispatch `damage.dealt`.

Zero assignments create no event. Infect and wither create poison or -1/-1
counter results instead of the ordinary result; lifelink creates one life-gain
result per source/controller; fixed total toxic creates additional poison only
after positive creature combat damage to a player. An unresolved toxic value,
stale recipient identity, unrepresented source fact, or malformed result leaf
rejects the batch before any result commits. State-based actions still occur
after damage; the transaction does not destroy creatures or remove defeated
players itself.

If prevention reduces an in-progress event to zero, that event no longer
offers later replacement or prevention effects (CR 120.8 and 614.7a).
Unpreventable damage remains positive, so each applicable prevention effect is
still applied exactly once as required by CR 615.12.

## Runtime components

`replacement.damage.quantity.v1` supports fixed integral multiplication and
addition with declarative source-controller, recipient-controller, recipient
kind, source/recipient characteristic, and combat predicates.

`prevention.damage.fixed.v1` supports a fixed positive reduction with the same
predicate vocabulary. Represented player/permanent protection contributes a
source-and-recipient-scoped prevention effect through the same ordering path,
so protection from one source cannot suppress another simultaneous source.
Furnace of Rath and Daunting Defender are source-pinned witnesses; their names
and Oracle IDs do not appear in engine dispatch.

`damage_prevention.py` owns durable finite, next-instance, and all-damage
shield values plus durable redirection values. A shield records its subject,
optional physically identified source predicate, duration, remaining amount,
and controller. Preparation never mutates it. The final commit consumes the
validated amount or next instance, while unpreventable damage applies the
effect once without consuming it. If simultaneous events compete for an
insufficient shield, the affected seat supplies one exact allocation through
the ordinary replacement continuation. The journal and commit plan are both
replay-pinned. Until-end-of-turn values expire at cleanup.

`damage_prevention_creation.py` resolves dynamic quantities before commit,
validates exact divided allocations, creates one independently consumable
shield per selected object, and pins an optional chosen source to physical
identity plus current characteristics/LKI. Version-3 source identity uses the
logical incarnation and zone, with the CR 400.7a exception that a chosen
permanent spell continues to the permanent that spell becomes. It neither
follows a countered spell into a graveyard nor a physical card through a later
incarnation. Its strict `ObjectQuerySpec` serialization replaces the former
parallel source-filter fields. Historical version-0 through version-2
checkpoint shapes retain their original replay semantics.

The seat-scoped source choice offers public permanents, spells on the stack,
face-up command-zone objects, and former-zone objects carried by explicit typed
provenance from a stack object, waiting prevention/replacement value, or waiting
delayed trigger. It never scans arbitrary semantic context or hidden objects.
The compiler, choice continuation, and damage-time recheck share the canonical
object predicate for all/any colors and required effective types, subtypes,
supertypes, or keywords. CR 609.7 source identity, public/LKI provenance,
exact incarnation, and permanent-spell continuity remain source-specific
checks rather than target-legality rules.

`damage_prevention_aftermath.py` aggregates the amount actually prevented by
each applied shield across a simultaneous batch. Represented life gain becomes
an immutable `life.change` replacement event, resolves current trusted life
replacement components in APNAP order, replay-validates its journal, and commits
through the canonical life owner. Represented permanent counters use the
canonical counter-placement pipeline, including applicable quantity
replacements. Every result plan is validated before the damage batch mutates.
Represented source-controller damage uses the shield's immutable source LKI,
derives the prevented source's controller from the event batch, and prepares a
nested `DamageProposal` against the projected post-consumption modifier state.
Ordinary replacement, prevention, result, trigger, and replay behavior therefore
applies to the nested damage. Mandatory recursive cycles, explicit-target
aftermath, mixed damage/non-damage aftermath, and other CR 615.5 forms remain
blocked before mutation. CR 615.13 triggered results are a separate stack
boundary and are not executed as immediate aftermath.

An independent sentence after a prevention instruction is different. The
reviewed fixed sequence creates its shield through the seat-scoped source
choice and then resumes a sibling `life` instruction immediately. It gains
life once during successful resolution even when the shield remains unused;
later shield consumption does not run that instruction again. An all-targets-
illegal spell stops before either instruction. `life-effects.v2` sends the
immediate result through the same replacement-capable `life.change` owner and
persists stable event/batch identity and the canonical replacement journal.

`replacement.damage.redirect-to-source.v1` is the current trusted static
redirection component. It replaces the complete recipient snapshot, not just
a display ref, and replacement applicability/affected-subject ordering is then
recomputed. A departed or no-longer-damageable destination makes the effect do
nothing. The component is collected only while its damageable battlefield
source exists; complete copy-layer interaction remains outside this slice.

`replacement.life.gain.multiplier.v1` contributes a fixed integral multiplier
to a positive `life.change` result. The focused
`semantic_runtime/life_replacements.py` registry owns its lowering and source
discovery; damage results only compose nested life events and ordinary life
effects no longer depend on the damage-result registry. `life_change.py` owns
event preparation, APNAP choices, replay, and commit through the mutation-only
`life_state.py` boundary. Oracle IR emits this descriptor for the
closed static life-doubling sentence, so Boon Reflection and Rhox Faithmender no
longer require source-pinned programs. `replacement.damage.result.life_floor.v1`
caps the life-loss child of one complete `damage.results` root; Worship remains
a source-pinned official-shape witness. Both handlers are generic and source-
hash invalidated.

The trusted capabilities are deliberately narrow:

- `damage.replacement.static_quantity`
- `damage.prevention.static_fixed`
- `damage.prevention.persistent_amount`
- `damage.prevention.aftermath.damage`
- `damage.redirection.static_to_source`
- `damage.result.infect`
- `damage.result.wither`
- `damage.result.lifelink`
- `damage.result.toxic`
- `damage.result.replacement_order`
- `life.gain.replacement.static_multiplier`

They exclude arbitrary opaque referred-object provenance, source-characteristic
predicates beyond the closed color/type/subtype/supertype/keyword vocabulary,
face-down source characteristics,
combat-only filters, life-gain prevention, non-effect-runtime life producers,
aftermath forms beyond represented life, permanent counters, and source-
controller damage, CR 615.13 prevention-triggered abilities, finite partial
redirection, attached or equipped destinations,
replacement with a non-damage event, dynamic toxic values, unrepresented
continuous ability grants, and uncompiled result-replacement families.
The broad `damage.replacement.order` and `damage.prevention.order` capabilities
remain blocked.

## Corpus result

The complete pinned census binds Infect, Wither, Lifelink, and fixed Toxic
nodes to trusted fine-grained result capabilities. Oracle IR v20 recognizes
closed whole-line grammar for static double damage, fixed static prevention,
finite and divided shield creation, chosen-source next-instance/all-damage
families, represented life/counter aftermath, static life-gain doubling, and
static redirection to a damageable source. The corrected fixed independent
life sequence matches one Oracle object in the pinned corpus: Healing Grace.
It moves from partial/residual to exact/capability-closed without changing its
rules meaning into CR 615.5 aftermath. The closed source-controller damage
production additionally moves Deflecting Palm to exact/capability-closed; it
does not promote the neighboring triggered New Way Forward wording. The generated
[compiler coverage report](../COMPILER_COVERAGE_STATUS.md) is the authority for
totals and residual deltas; these gains do not imply complete damage,
prevention, or Oracle coverage.

## Choice, privacy, and replay

The affected player, or the damaged permanent's controller, selects among
competing applicable effects. A seat packet contains only public option labels
and stable IDs. The immutable event payload, object IDs, effect set, and prior
journal remain in the authoritative continuation.

Combat and semantic continuations persist the exact ordered selections, same-
chooser simultaneous-event order, and any finite-shield allocation in Game
Record v3. Replay rebuilds the transaction, validates the chooser, event IDs,
available amount, and current option set, and must reach the same final state
hash. Nested damage aftermath journals its own replacement selections and
recursively emits final normalized events. Checkpoints also serialize durable
shield, aftermath, and redirection state. A replacement choice discovered while a mana ability is paying for a
cast or activation rolls the partial payment back, persists a strict payment
frame, and resumes the exact original action after the seat chooses.

## Remaining boundaries

The remaining damage/prevention work must broaden explicit referred-object
provenance and source-characteristic grammar, represent face-down source
characteristics, migrate non-effect-runtime life producers to `life.change`,
add life-gain prevention, CR 615.13 prevention-trigger stack ownership,
explicit-target and mixed aftermath forms, partial and
attached-destination redirection, non-damage transformations, remaining result-
replacement families, excess-damage selection, and complete dynamic
characteristic closure. Broader Oracle lowering must compile those families
into typed descriptors before their capabilities can be promoted.

Primary assurance is split across `test_damage_replacement_model.py`,
`test_damage_replacement_multiplayer.py`, and
`test_damage_replacement_integration.py`, with immutable-model hardening in
`test_replacement_model_hardening.py`, physical designation coverage in
`test_commander_damage_identity.py`, legacy result regressions in the state-
action, combat, monarch, mana, and turn-history modules, and focused mutants in
`test_capability_implementation_mutations.py` and the focused CR 120.3/120.4c
witnesses in `test_damage_result_events.py`. Durable prevention and redirection
coverage lives in `test_damage_prevention_shields.py`,
`test_damage_prevention_creation.py`, `test_damage_prevention_aftermath.py`,
`test_prevention_immediate_sequencing.py`, `test_life_change.py`,
`test_semantic_choice_characterization.py`,
`test_copy_objects.py`, `test_replacement_event_ordering.py`,
`test_mana_mode_effects.py`, and `test_damage_redirection.py`.
