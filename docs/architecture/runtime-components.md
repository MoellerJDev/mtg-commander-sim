---
title: "CardProgram runtime components"
status: "current"
authoritative_source: "mtg_commander_sim/semantic_runtime component registries, mtg_commander_sim/drawing, and ADRs 0007/0010/0011/0012"
verified: "2026-08-06"
audience: "rules, compiler, runtime, replay, and extension contributors"
maintenance: "hand-maintained"
---

# CardProgram runtime components

Runtime components represent CardProgram behavior that participates outside one
immediate stack-resolution instruction. Family registries own validation and
lowering; the global inventory only provides stable metadata and a fingerprint.
Components receive bounded read-only contexts and return immutable replacement
effects or continuous effects. They never receive `CommanderEngine`, mutable
`GameState`, projection internals, or persistence objects, and they never
mutate state.

Every registered handler declares a stable ID, schema version, exact family and
event, rule references, capability dependencies, strict descriptor validator,
and deterministic inventory entry. A malformed descriptor for a registered ID
fails closed. Only an entirely unregistered legacy operation may use the
measured compatibility dispatcher.

## Current bounded families

`replacement.token.additional.v1` supports a mandatory fixed additional-token
result for its declared token type and controller. Multiple current effects use
the affected controller's seat-scoped order, effects created by earlier
applications are rediscovered, and the exact event path and selection journal
replay. Added tokens receive their own default status rather than inheriting
the original token's tapped, attacking, protector, or temporary-keyword state.
The family does not claim optional descriptors, quantity doubling, or state-
derived token definitions.

`replacement.zone.destination.v1` supports a reviewed source-stamped zone-
destination replacement and typed nested counter events. It uses the controller of
an object on the battlefield or stack and the owner otherwise, prepares
simultaneous changes against the same pre-move source snapshot, and suspends
competing choices to the affected seat. Dauthi Voidwalker's reviewed behavior
is the current source-pinned witness; the engine no longer selects it by
Oracle ID. The containing zone event is exhausted before its counter child,
and all choices finish before the move commits.

`replacement.counter.quantity.v1` supports fixed integral multiplication and
addition for effect-generated counters placed on battlefield permanents. It
can restrict placing-player relation, affected permanent controller, counter
name, and effective type. Competing effects are chosen by the affected
permanent's controller; simultaneous events traverse APNAP order. Doubling
Season and Doc Samson, Super Psychiatrist are the source-pinned witnesses.
Player counters, costs, dynamic quantities, halving, movement, removal,
prevention, full entry ordering, and continuation-sensitive legacy producers
remain outside the component.

`replacement.damage.quantity.v1` and `prevention.damage.fixed.v1` participate
in the same immutable damage event before any life, marked-damage, defense,
loyalty, commander-damage, or trigger mutation. They support fixed integral
quantity changes or fixed positive prevention with declarative source,
recipient, controller, characteristic, and combat predicates. Competing
effects use the affected player or damaged permanent controller and traverse
simultaneous four-player events in APNAP order.

Durable finite and next-instance shields lower to typed
`PreventUsingShield` operations owned by `damage_prevention.py`. The owner
validates cross-event remaining amounts, cleanup expiration, simultaneous
allocation, commit-time state fingerprints, and unpreventable nonconsumption.
`replacement.damage.redirect-to-source.v1` lowers a current damageable
battlefield source to typed `RedirectDamage`; a complete recipient snapshot is
substituted before the replacement loop is rediscovered. Dynamic/divided and
independent per-object shield creation is owned by the focused
`damage-modifiers.v1` effect family. Chosen-source version 3 covers public CR
609.7a candidates plus explicitly referred former-zone objects, exact
incarnation matching, permanent-spell-to-permanent continuity, and one strict
serialized `ObjectQuerySpec` for effective color/type/subtype/supertype/keyword
rechecks. Historical version-0 through version-2 source snapshots remain
replay-compatible. Represented CR 615.5 life
aftermath enters the replacement-capable `life.change` transaction; permanent-
counter aftermath remains on the counter-placement transaction. Typed source-
controller damage aftermath pins immutable source LKI and recursively prepares
through the canonical damage transaction against projected modifier state.
Same-chooser
event order and replacement choices during mana payment use strict replayable
continuations. A fixed independent life sentence after a prevention sentence
is an ordered sibling, not aftermath: source choice creates the shield, then
the sibling enters `life.change` immediately and exactly once. Arbitrary opaque
references, wider source predicates, life-gain prevention, broader conditional
prevention-trigger results, explicit-target or mixed aftermath forms, finite partial or
attached redirection, and non-damage
transformations remain outside these components.

`replacement.draw.dredge.v1` discovers a trusted keyword-derived replacement
only while its exact physical source is in its owner's graveyard. It checks the
current library threshold, emits one immutable optional `DredgeDraw`, and pins
the source incarnation through any private affected-player choice. The
`drawing` package applies it before ordinary empty-library handling and
completes its mill-and-return result before later draws or later resolution
instructions resume. The companion draw registries lower unconditional fixed
instruction doubling and live fixed no-draw/maximum-one battlefield
restrictions. These components have no mutable-state access and do not imply
conditional/dynamic limits, complete draw-as-cost production, shared-team
ordering, or the complete replacement corpus.

`action.draw.reveal-first.v1` discovers mandatory or optional first-draw
policies from live phased-in battlefield sources. The component returns an
immutable physical-source policy; the draw coordinator owns private choice,
ordinal revalidation, non-draw replacement exclusion, and exact resume, while
the draw transaction reveals before the card enters hand. The normalized event
retains source identity so only that source's closed basic-land or creature
draw rider triggers. Other qualities and compound reveal riders remain outside
the component rather than being interpreted from Oracle text at runtime.

`continuous.anthem.power_toughness.v1` supports a fixed same-controller subtype
anthem in layer 7c. The source must be represented, on the battlefield, and not
phased out. Applicability uses characteristics produced by prior layers, and
independent sources stack by timestamp and component identity. It does not
claim CDAs, base-setting, state-derived modifiers, ability removal, same-layer
dependencies, or complete CR 613.

`continuous.anthem.fixed-query.v2` generalizes that source-pinned witness to a
closed compiler-produced predicate. It binds relative controller constraints
to the live source controller, excludes the source when the wording requires
"other," and emits only fixed layer-7c power/toughness operations. The source
must remain on the battlefield and phased in; target membership changes as
earlier-layer characteristics, control, entry, and departure change. The
runtime model is immutable and never receives `GameState`.

The predicate is one complete canonical `ObjectQuerySpec`, including all/any
type and color terms, subtypes, supertypes, keywords, token and tap state,
phasing policy, owner/controller relations, visibility, and source exclusion.
The CardProgram handler footprint fingerprints that full value plus every
modifier field. Schema-v1 query payloads omit the additive `types_any` member
when replayed so historical Game Record v3 bytes remain stable; new values use
the complete schema. The compiler's creature-subtype branch is additionally
closed over the pinned CR 205.3m registry rather than capitalization.

Resolution-created fixed modifiers are not components that remain active at a
source. Typed effect-runtime producers prepare an exact object set and commit
an additive `ContinuousEffect` journal entry through
`continuous_effect_state.py`. Cleanup expires the represented end-of-turn
duration. Historical Game Record v3 checkpoints without this journal keep the
annotation compatibility path explicitly.

## Participation and assurance

Descriptors live inside the canonical CardProgram fingerprint. Strict preflight
binds their dependencies to the applicable capability closure. Game Record v3
pins the component inventory and registry fingerprint, and exact replay rejects
drift. Component contexts contain only public or source-authorized facts; no
component expands a principal projection.

Continuous collection is currently uncached. Instrumentation counts collection
calls, battlefield objects inspected, CardProgram lookups, descriptors
inspected, and effects produced for deterministic benchmark scenarios. The
structural baseline is CI-gated; latency is observational until a stable budget
exists. Any future cache requires exact invalidation for state, program,
component, timestamp, characteristic, and ruleset changes.

`token_creation.py` is the focused authoritative mutation owner for token
commit and enter-event dispatch. `replacement/` owns immutable models, typed
operations, applicability, ordering, and strict replay;
`replacement_effects.py` is its compatibility facade, and
`replacement_decisions.py` owns replayable choice
continuations. `counter_placement.py` owns pre-mutation preparation and final
commit for represented permanent-counter events. `damage.py` coordinates
represented damage batches, while `damage_source.py` owns immutable source LKI
and `damage_values.py` owns recipient/proposal values. `damage_results.py` owns
result-event materialization, commit
planning, and atomic CR 120.3 result mutation. `damage_prevention.py` owns
durable shield/redirection state and its mutation-only commit plan;
`damage_prevention_creation.py` and `damage_prevention_aftermath.py` own the
corresponding typed creation and result transactions. `life_change.py` owns
replacement-capable life-event preparation, APNAP selection, replay, and commit
through the mutation-only `life_state.py` owner;
`semantic_runtime/life_replacements.py` owns the one `life.change` component
registry and source discovery. The six closed effect
runtime families now include `damage-modifiers.v1` for shield/redirection
creation and `life-effects.v2` for replacement-capable typed effect life
changes. `drawing/model.py`, `drawing/continuation.py`,
`drawing/coordinator.py`, and `drawing/transaction.py` own the draw boundary;
`semantic_runtime/draw_replacements.py` owns Dredge and fixed instruction-
quantity lowering, while `semantic_runtime/draw_restrictions.py` owns live
permission restrictions and `semantic_runtime/draw_reveals.py` owns CR 121.9
source-policy discovery.
Runtime components remain pure participants.

Primary tests are `test_replacement_event_tree.py`,
`test_token_creation_replacements.py`, `test_graveyard_rules.py`,
`test_counter_placement_replacements.py`,
`test_damage_replacement_model.py`,
`test_damage_replacement_multiplayer.py`,
`test_damage_replacement_integration.py`,
`test_damage_prevention_shields.py`, `test_damage_redirection.py`,
`test_damage_prevention_creation.py`, `test_damage_prevention_aftermath.py`,
`test_life_change.py`, `test_replacement_event_ordering.py`, `test_life_effect_runtime.py`,
`test_mana_mode_effects.py`,
`test_replacement_model_hardening.py`,
`test_damage_result_events.py`,
`test_continuous_effect_components.py`, `test_continuous_effect_duration.py`,
`test_draw_replacement_components.py`, `test_draw_transaction_model.py`,
`test_draw_transaction_commit.py`, `test_draw_continuation.py`,
`test_draw_reveal_as_drawn.py`,
`test_card_program_trust.py`, and
`test_continuous_effect_performance.py`. See the
[extension guide](../extension/runtime-component.md) and
[ADR 0007](../adr/0007-cardprogram-runtime-components.md) plus
[ADR 0010](../adr/0010-replacement-event-tree-and-token-owner.md),
[ADR 0011](../adr/0011-counter-placement-event-and-mutation-owner.md), and the
[counter-placement architecture](counter-placement.md), plus
[ADR 0012](../adr/0012-damage-transaction-and-static-prevention.md) and the
[damage transaction](damage-transactions.md), plus
[ADR 0013](../adr/0013-damage-result-event-ownership.md).
The continuous-effect state decision is
[ADR 0020](../adr/0020-continuous-effect-duration-and-applicability.md).
