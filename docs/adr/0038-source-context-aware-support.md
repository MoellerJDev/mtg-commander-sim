---
title: "ADR 0038: source-context-aware Support lowering"
status: "ADR"
authoritative_source: "this decision record and the typed Support compiler production"
verified: "2026-08-08"
audience: "rules, compiler, replay, privacy, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0038"
decision_status: "accepted"
date: "2026-08-08"
---

# ADR 0038: source-context-aware Support lowering

## Context

CR 701.41a gives Support N two closely related meanings. On a permanent it
puts one +1/+1 counter on each of up to N *other* target creatures. On an
instant or sorcery spell it omits that source exclusion. The typed bounded
target-set transaction from ADR 0037 already owns target selection,
resolution-time revalidation, simultaneous replacement ordering, mutation,
privacy, and replay, but its ordinary Oracle grammar deliberately excluded
Support because it did not carry this source context.

## Decision

Compile one whole fixed positive `Support N` instruction only when the source
face has an exact parsed permanent type or an exact instant/sorcery type.
Permanent sources emit the existing creature target schema with
`source_exclusion`; instant and sorcery sources emit the same schema without
it. Ambiguous or unrelated source types fail closed. Spell, triggered, and
activated contexts share the source-spanned `SupportCounterPlacementTemplate`.

Support emits the existing `place_counters_on_targets` operation with one
+1/+1 counter per surviving target. The existing target-set handler,
read-only APNAP/logical-identity coordinator, replacement-aware counter
transaction, and counter-state mutation owner remain the only runtime path.
No Oracle text is parsed at runtime and no new authoritative write owner is
introduced.

## Alternatives

- Treat Support as ordinary “up to N targets” text. Rejected because that
  loses the mandatory permanent-source exclusion.
- Infer the source context from whether the type-line contains a substring.
  Rejected because malformed and mixed card types could be promoted falsely.
- Add a Support-specific runtime operation. Rejected because target-set
  revalidation and counter placement already have canonical typed owners.

## Consequences

- Advertised target candidates and accepted submissions use the same source
  exclusion and bounded creature predicate.
- Zero selections remain legal; partial illegality affects only the illegal
  targets; an originally nonempty wholly illegal set does not resolve.
- Counter quantity replacements, multiplayer ordering, private replacement
  choices, rollback, and exact replay are inherited from the shared family and
  explicitly evidenced for Support.
- Support X or zero and conditional, optional, repeated, copied, granted,
  modal, or compound Support instructions remain material residuals.

## Removal condition

Retire this production only if a successor typed keyword-action model preserves
the exact source-type distinction, permanent-source exclusion, source spans,
bounded distinct targets, resolution-time legality, single simultaneous
counter transaction, privacy, replay, and fail-closed unsupported forms.
