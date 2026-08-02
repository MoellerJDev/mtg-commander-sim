---
title: "ADR 0013: typed damage-result event ownership"
status: "ADR"
authoritative_source: "this decision record and platform/architecture-policy.json"
verified: "2026-08-02"
audience: "rules, semantics, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0013"
decision_status: "accepted"
date: "2026-08-02"
---

# ADR 0013: typed damage-result event ownership

## Context

ADR 0012 established one immutable damage proposal and quantity-replacement
transaction. Its result phase still mutated life, marked damage, loyalty, and
defense directly and rejected infect and wither. That shape could not apply a
replacement to the complete CR 120.3 result before replacements of contained
life-gain or counter-placement events, as required by CR 120.4c and 616.1g.

## Decision

`damage.py` remains the damage coordinator. It snapshots sources and
recipients, resolves damage-quantity replacement and prevention, then delegates
the final dealt components to `damage_results.py`.

`damage_results.py` is the sole owner of represented CR 120.3 result-event
materialization and atomic result mutation. It groups simultaneous results by
affected player or permanent, places life-change and counter events beneath a
containing `damage.results` event, resolves all applicable replacements, builds
a mutation-only plan, validates every leaf and object incarnation, and commits
only after the complete plan is valid.

`semantic_runtime/damage_results.py` remains pure. It validates and lowers
source-pinned result replacement descriptors such as a fixed life-gain
multiplier or a damage-result life floor. It has no mutation authority.

The source snapshot carries effective keyword facts and a represented fixed
total toxic value. Keyword dispatch is generic; production code does not
branch on printed card names or Oracle IDs. Unresolved toxic values and
unrepresented source last-known information fail before mutation.

## Alternatives

- Mutate each life or counter result as it is discovered. Rejected because a
  later failure would violate atomicity and containing-event replacements
  could not inspect the complete simultaneous result.
- Implement Worship or Boon Reflection by card name. Rejected because the
  runtime component boundary supports every source with the same bounded
  Oracle shape and preserves source-hash invalidation.
- Treat all life and counter replacement families as complete. Rejected
  because only bounded handlers have behavioral evidence; uncompiled families
  remain fail-closed.

## Consequences

- Infect, wither, lifelink, and fixed toxic values compose with combat and
  noncombat damage through one result path.
- Player and permanent result replacements use affected-subject ordering and
  exact replay paths before any authoritative mutation.
- Commander damage and damage history continue to derive from the final dealt
  amount even when a replacement changes the resulting life loss.
- The former result logic leaves the central engine and the damage coordinator
  becomes smaller in responsibility, while Game Record v3 remains unchanged.
- The reviewed architecture baseline is refreshed for the new dedicated owner
  and for generic rule words (`lifelink`, `toxic`, and `loss`) that coincide
  with printed card names. The ratchet still forbids new oversized functions,
  card-specific dispatch, or unreviewed specificity growth.

## Removal condition

The narrow direct-permanent compatibility adapter can be removed when its
remaining state-based-action tests and callers construct typed damage batches.
The partial mechanic contracts can become trusted only after continuous
ability grants/removals and source last-known-information are certified for
every represented source zone.
