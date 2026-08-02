---
title: "Damage transaction"
status: "current"
authoritative_source: "mtg_commander_sim/damage.py, mtg_commander_sim/damage_results.py, semantic_runtime/damage_replacements.py, semantic_runtime/damage_results.py, ADR 0012, and ADR 0013"
verified: "2026-08-02"
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

The transaction has four explicit stages:

1. Snapshot the source and recipient identities and relevant characteristics.
2. Build immutable positive `damage` events and discover active trusted
   replacement/prevention components against the pre-mutation state.
3. Apply forced damage effects or suspend an affected-player/controller choice
   before mutation.
4. Group every simultaneous life, poison, -1/-1, marked-damage, loyalty,
   defense, lifelink, toxic, and nested replacement result beneath immutable
   affected-player or affected-permanent `damage.results` roots. Resolve the
   containing event before its contained result events.
5. Validate every result and object incarnation, build a mutation-only plan,
   commit the complete result batch atomically, then
   publish one final `DamageEvent` for each positive proposal. Fully prevented
   events remain in the audit result but do not dispatch `damage.dealt`.

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

`replacement.life.gain.multiplier.v1` contributes a fixed integral multiplier
to a positive `life.change` result. `replacement.damage.result.life_floor.v1`
caps the life-loss child of one complete `damage.results` root. Boon Reflection
and Worship are source-pinned official-shape witnesses; the handlers are
generic and source-hash invalidated.

The trusted capabilities are deliberately narrow:

- `damage.replacement.static_quantity`
- `damage.prevention.static_fixed`
- `damage.result.infect`
- `damage.result.wither`
- `damage.result.lifelink`
- `damage.result.toxic`
- `damage.result.replacement_order`
- `life.gain.replacement.static_multiplier`

They exclude persistent or divisible shields, redirection, replacement with a
non-damage event, dynamic toxic values, unrepresented continuous ability grants
or source last-known information, uncompiled life/counter/result replacement
families, and a replacement choice arising inside an in-progress mana payment.
The broad `damage.replacement.order` and `damage.prevention.order` capabilities
remain blocked.

## Corpus result

The complete pinned census now binds Infect, Wither, Lifelink, and fixed Toxic
nodes to trusted fine-grained result capabilities. It also recognizes a closed
whole-line grammar for static double-damage and fixed-prevention effects and
lowers those cards to typed runtime handlers. Commander-legal exact Oracle
objects rise from 338 to 403, trusted CardPrograms from 359 to 403, and material
residuals fall from 61,213 to 60,793. The generated
[compiler coverage report](../COMPILER_COVERAGE_STATUS.md) is authoritative;
these gains do not imply complete damage, prevention, or Oracle coverage.

## Choice, privacy, and replay

The affected player, or the damaged permanent's controller, selects among
competing applicable effects. A seat packet contains only public option labels
and stable IDs. The immutable event payload, object IDs, effect set, and prior
journal remain in the authoritative continuation.

Combat and semantic continuations persist the exact ordered selections in Game
Record v3. Replay rebuilds the transaction, validates the chooser and current
option set, and must reach the same final state hash. A mana-result damage event
with a real replacement choice currently fails before damage because the
enclosing mana-payment continuation cannot yet resume safely.

## Remaining boundaries

The next damage/prevention work must add persistent shield ownership and
consumption, allocation/division, redirection, non-damage transformations,
remaining result-replacement families, excess-damage selection, complete
dynamic characteristic closure, and resumable choices during mana
payment. Broader Oracle lowering must compile those families into typed
descriptors before their capabilities can be promoted.

Primary assurance is split across `test_damage_replacement_model.py`,
`test_damage_replacement_multiplayer.py`, and
`test_damage_replacement_integration.py`, with immutable-model hardening in
`test_replacement_model_hardening.py`, physical designation coverage in
`test_commander_damage_identity.py`, legacy result regressions in the state-
action, combat, monarch, mana, and turn-history modules, and focused mutants in
`test_capability_implementation_mutations.py` and the focused CR 120.3/120.4c
witnesses in `test_damage_result_events.py`.
