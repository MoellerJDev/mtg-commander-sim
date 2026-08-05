---
title: "Counter-placement transaction"
status: "current"
authoritative_source: "mtg_commander_sim/counter_placement.py, semantic_runtime/counter_replacements.py, and ADR 0011"
verified: "2026-08-05"
audience: "rules, semantics, replay, and architecture contributors"
maintenance: "hand-maintained"
---

# Counter-placement transaction

`counter_placement.py` is the focused authoritative owner for represented
effect-generated counters placed on battlefield permanents. It separates the
operation into preparation and commit:

1. Resolve each target object and build immutable `counter.place` events.
2. Discover active trusted runtime descriptors against the pre-mutation state.
3. Traverse simultaneous events in APNAP order and let each affected
   permanent's controller choose among applicable replacements.
4. Suspend through the ordinary seat-scoped replacement continuation when a
   real choice exists.
5. Commit only after every selection is complete and every permanent is still
   the same object in the expected zone.

This order enforces the represented portions of CR 122.6, 614.1, 614.16,
616.1, 616.1f, and 616.1g without giving pure runtime components mutable state.
The choice projection contains labels and stable option IDs only; the event
payload, object identifier, replacement batch, and prior journal remain in the
authoritative continuation. Exact replay reconstructs and validates the path,
chooser, and selected effect.

`replacement.counter.quantity.v1` is the current bounded component. It applies
fixed positive integral multiplication or fixed nonnegative addition to an
effect-generated placement on a battlefield permanent. The descriptor may
restrict the placing player, permanent controller, counter name, and effective
permanent type. The reviewed source-pinned witnesses are Doubling Season and
Doc Samson, Super Psychiatrist. Cost-generated counters and inactive sources
do not match.

Zone-destination replacements can create a typed nested counter event. The
containing zone event is exhausted before that child is considered. All
replacement choices are resolved before the zone move; the child counter is
committed only after the card reaches its validated destination. A nested
counter on a card outside the battlefield is represented for ordering but is
outside the permanent-only quantity component.

## Ownership and dependencies

`counter_placement.py` depends on immutable replacement values and narrow host
protocols. It may mutate only the target permanent's counter map during commit.
`semantic_runtime/counter_replacements.py` validates source descriptors and
returns immutable effects; architecture policy prohibits it from importing the
engine, `GameState`, transport, persistence, or projection code.

The engine retains compatibility facades and supplies the host protocol. New
positive fixed counter operations must enter the transaction instead of adding
another direct engine write. Removal, payment, and rule actions remain distinct
until their ordering and continuation semantics are modeled.

## Current producer inventory

The shared transaction currently owns positive `add_counter_selected`, positive
generic `counter`, `counter_all_subtype`, direct transaction calls, and typed
nested zone-replacement counters. These paths prepare before mutation and can
safely suspend.

The following producers remain deliberately outside this slice:

- intrinsic planeswalker and battle entry counters;
- Saga lore rule actions and stun-counter removal;
- loyalty activation costs and damage-counter removal;
- explore, cumulative upkeep, fabricate, and proliferate;
- player counters, state-based removals, and card-specific continuation paths
  such as Demonic Junker.

Several of those operations occur inside a larger semantic continuation after
earlier instructions have already mutated state. Routing them through a choice
that can suspend would replay prior side effects unless the enclosing
instruction first gains a typed resumable frame. They are recorded blockers,
not silently approximated migrations.

The component also excludes fractional or halving replacements, dynamic
quantities, counter movement, prevention, complete enters-with-counter
ordering, and universal placing-player derivation. Broad CR 122/614/616 stays
blocked until those families and producers are integrated.

Primary assurance is in `test_counter_placement_replacements.py`, with shared
event-order coverage in `test_replacement_event_tree.py` and focused mutation
evidence in `test_capability_implementation_mutations.py`.

## Pinned-corpus effect

Against the 2026-07-31 local Scryfall snapshot, this counter-placement tranche
added two reviewed ability programs but no capability-closed cards by itself,
because the bounded counter-quantity capability remained tested and the
witness cards retained material behavior outside the slice. Current aggregate
counts are generated in
[`docs/COMPILER_COVERAGE_STATUS.md`](../COMPILER_COVERAGE_STATUS.md); later
damage work changes those totals. These figures measure representation, not
matchup or complete Oracle correctness.
