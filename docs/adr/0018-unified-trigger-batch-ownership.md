---
title: "ADR 0018: unified triggered-ability batch ownership"
status: "ADR"
authoritative_source: "this decision record and platform/architecture-policy.json"
verified: "2026-08-03"
audience: "rules, semantics, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0018"
decision_status: "accepted"
date: "2026-08-03"
---

# ADR 0018: unified triggered-ability batch ownership

## Context

The engine represented permanent-based semantic triggers as serialized
`StackItem` values in a mergeable APNAP batch, but delayed triggers used a
second controller-group loop, a second continuation shape, and a private stack
append path. This split could omit ordinary triggers when a delayed trigger
matched the same step, gave persistence two meanings for the same CR 603.3
process, and made every new trigger producer choose an executor.

CR 603.3 requires already-triggered abilities waiting since the previous
priority opportunity to enter the ordinary stack through one APNAP process.
Their discovery mechanism must not decide their batching, ordering, targeting,
or stack semantics.

## Decision

`trigger_batches.py` owns the strict version-1 pending-batch value. A
`PendingTriggerItem` deep-freezes one ordinary triggered-ability stack payload;
`TriggerControllerGroup` records one controller's waiting occurrences; and
`PendingTriggerBatch` records the active-player order, turn and priority epoch,
placement state, and groups. Unknown fields, malformed nested entries,
duplicate refs, invalid APNAP membership, and non-trigger stack objects fail
closed. New checkpoints include `schema_version: 1`; historical unversioned
Game Record v3 batch dictionaries deserialize through an explicit compatibility
shape and serialize canonically.

Static-source semantic detection, delayed-trigger matching, and typed dynamic
producers all lower to ordinary `StackItem` occurrences before batching.
`CommanderEngine._collect_trigger_items` coordinates static-source and delayed
discovery for one event without placing either. Every producer submits through
`_enqueue_trigger_batch`; every controller group completes through
`complete_pending_trigger_group`; and every item reaches the same
`_place_trigger_items` sink and target-at-placement pass.

An unstarted batch may merge later occurrences from the same priority epoch,
including triggers discovered during state-based-action stabilization. Starting
placement seals it. New occurrences then create a later batch for the repeated
CR 603.3 stabilization pass. Controllers no longer in the game are discarded
only when placement starts and APNAP order is recomputed.

One `trigger_batch_id` continuation owns same-controller bottom-to-top order for
all new source kinds. The continuation pins the exact trigger-ref set and fails
if it is malformed or stale. Historical `semantic_trigger_batch_id`
continuations remain accepted. Historical delayed-only `trigger_ids/groups`
continuations use a quarantined compatibility adapter that validates the whole
tree before mutation and materializes through the ordinary typed stack sink;
new games never write that shape.

## Alternatives

- Keep delayed triggers as IDs until ordering, then add adapters for each new
  dynamic trigger family. Rejected because it preserves several APNAP and
  persistence implementations.
- Convert every delayed-trigger creation record in the same slice. Rejected
  because creation provenance, recurrence, and event grammar are a separate CR
  603.7 boundary; detected occurrences can converge without claiming that
  broader implementation.
- Change Game Record v3. Rejected because an additive typed batch schema and
  explicit continuation compatibility preserve replay without a record
  redesign.

## Consequences

- A delayed trigger can no longer suppress represented static-source discovery
  at the same phase or step.
- Cleanup, draw, untap/upkeep, combat boundaries, and ordinary priority steps
  use one occurrence collection and one APNAP placement owner.
- Caller-owned dictionaries cannot mutate waiting trigger payloads, and
  save/load produces canonical versioned state.
- Trigger placement behavior is independently testable without constructing a
  complete engine.
- `CommanderEngine` loses the delayed-only grouping/ordering/queue executor and
  the semantic-only grouping helper.

## Remaining boundary

This decision does not claim complete CR 603. The generic Oracle trigger
grammar, normalized zone-event/LKI matrix, trigger-additional-times effects,
the special second part of CR 603.3b for abilities that trigger from abilities
triggering, modal/divided placement choices, intervening-if closure, state
triggers, reflexive triggers, complete delayed-trigger creation provenance, and
the full look-back exception matrix remain blocked.
