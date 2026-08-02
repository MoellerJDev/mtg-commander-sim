---
title: "Damage transaction"
status: "current"
authoritative_source: "mtg_commander_sim/damage.py, semantic_runtime/damage_replacements.py, and ADR 0012"
verified: "2026-08-02"
audience: "rules, semantics, replay, and architecture contributors"
maintenance: "hand-maintained"
---

# Damage transaction

`damage.py` is the authoritative owner for represented damage proposals,
replacement/prevention preparation, base result commit, and normalized final
events. Combat, semantic single-target damage, semantic each-opponent damage,
and damage produced by represented mana abilities use the same transaction.

The transaction has four explicit stages:

1. Snapshot the source and recipient identities and relevant characteristics.
2. Build immutable positive `damage` events and discover active trusted
   replacement/prevention components against the pre-mutation state.
3. Apply forced effects or suspend an affected-player/controller choice before
   any life, counter, marked-damage, commander-damage, or trigger mutation.
4. Validate every result in the simultaneous batch, commit base results, then
   publish one final `DamageEvent` for each positive proposal. Fully prevented
   events remain in the audit result but do not dispatch `damage.dealt`.

Zero assignments create no event. Unsupported infect, wither, toxic, stale
recipient identity, or malformed result semantics reject the batch before any
result commits. State-based actions still occur after damage; the transaction
does not destroy creatures or remove defeated players itself.

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

The trusted capabilities are deliberately narrow:

- `damage.replacement.static_quantity`
- `damage.prevention.static_fixed`

They exclude persistent or divisible shields, redirection, replacement with a
non-damage event, damage-result replacement, and a replacement choice arising
inside an in-progress mana payment. The broad `damage.replacement.order` and
`damage.prevention.order` capabilities remain blocked.

## Corpus result

The complete pinned-corpus census produced no Oracle exact/residual or
CardProgram trusted-count promotion. Exact current counts remain in the
generated [compiler coverage report](../COMPILER_COVERAGE_STATUS.md). The delta
is zero because these source-pinned witness descriptors depend on deliberately
blocked static damage capabilities; Furnace of Rath and Daunting Defender are
regression witnesses, not a format-wide support claim.

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
result-replacement ordering, infect/wither/toxic outcomes, and resumable
choices during mana payment. Broader Oracle lowering must compile those
families into typed descriptors before their capabilities can be promoted.

Primary assurance lives in `test_damage_replacement_pipeline.py`, with legacy
result regressions in the state-action, combat, monarch, mana, and turn-history
test modules and focused mutants in
`test_capability_implementation_mutations.py`.
