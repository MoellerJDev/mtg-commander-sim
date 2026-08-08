---
title: "Counter-placement transaction"
status: "current"
authoritative_source: "quorune/counter_placement.py, quorune/counter_state.py, quorune/entry_counter_model.py, quorune/entry_counters.py, semantic_runtime/counter_replacements.py, ADR 0011, and ADR 0034"
verified: "2026-08-08"
audience: "rules, semantics, replay, and architecture contributors"
maintenance: "hand-maintained"
---

# Counter-placement transaction

`counter_placement.py` is the focused authoritative owner for represented
effect-generated counters placed on players, battlefield permanents, and the
already modeled card-zone counter children. It separates the operation into
preparation and commit:

1. Resolve each subject and build immutable player- or object-affected
   `counter.place` events.
2. Discover active trusted runtime descriptors against the pre-mutation state.
3. Traverse simultaneous events in APNAP order and let the affected player or
   permanent's controller choose among represented applicable replacements.
4. Suspend through the ordinary seat-scoped replacement continuation when a
   real choice exists.
5. Commit only after every selection is complete, every player still exists,
   and every permanent is still the same object in the expected zone.

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

Zone-destination replacements use the closed
`CreateAffectedObjectCounter` operation to derive a typed child from the
parent zone event. The operation binds the affected physical object and the
already transformed destination at application time, so one immutable source
effect can serve every event in a simultaneous batch. The containing zone
event is exhausted before its child is considered. Every replacement choice
is complete before the move; the child counter commits only after the card
reaches its validated destination. A counter on a card outside the battlefield
is represented for ordering but remains outside the permanent-only quantity
component.

The Oracle compiler lowers the closed “an opponent's card from anywhere would
enter a graveyard; exile it with one named counter instead” family to this same
destination handler and nested counter operation. Different owners, origins,
object kinds, optional wording, counter-free moves, and alternate destinations
remain residual rather than being inferred at runtime.

## Ownership and dependencies

`counter_placement.py` depends on immutable replacement values and narrow host
protocols. It delegates the one atomic write plan to `counter_state.py`, which
owns poison, energy, arbitrary normalized player counters, and permanent
counter maps.
`semantic_runtime/counter_replacements.py` validates source descriptors and
returns immutable effects; architecture policy prohibits it from importing the
engine, `GameState`, transport, persistence, or projection code.

The engine retains compatibility facades and supplies the host protocol. New
positive fixed counter operations must enter the transaction instead of adding
another direct engine write. Removal, payment, and rule actions remain distinct
until their ordering and continuation semantics are modeled.

## Current producer inventory

The shared transaction currently owns the typed `place_counters` operation,
legacy-compatible positive `add_counter_selected`, positive generic `counter`,
`counter_all_subtype`, direct transaction calls, typed nested zone-replacement
counters, ordinary positive-integral Fabricate choices, the conditional +1/+1
counter from one permanent exploring once, and ordinary single-instruction
Proliferate over players and permanents. These paths prepare before mutation
and can safely suspend.

Intrinsic Planeswalker loyalty and Battle defense now use the same boundary.
The card-form compiler reads the canonical parsed type set and printed integral
characteristic once, emits a type-line-spanned CardProgram declaration, and
requires `counter.producer.intrinsic_entry`. Entry preparation lowers that
declaration to a mandatory self-replacement on the containing zone event; its
typed nested counter event follows any later destination replacement before
the ordinary affected-controller quantity-replacement ordering. A resolving
permanent can suspend through `resolving_entry` and resume without replaying
earlier spell effects. Simultaneous entries prepare in APNAP order without
mutation.

Oracle IR v49 lowers one closed reusable fixed-placement grammar through the
typed operation in spell, triggered, and activated contexts. It accepts one
positive exact quantity of one named counter on the source, the exact named
source, or one direct battlefield permanent target. Direct targets may use one
permanent card type or one pinned creature subtype, a fixed controller
relation, and source exclusion. The strict runtime handler lowers only to
`PlaceCountersIntent`; it neither parses Oracle text nor mutates state.

The bounded Proliferate family compiles an unmodified `Proliferate.` clause in
spell, triggered, and activated contexts to CardProgram V2. The resolving
controller chooses any number of eligible public subjects. The continuation
pins physical and logical permanent identity plus every positive counter kind;
one additional counter of each kind then enters one simultaneous
replacement-aware batch. The transaction permits an empty selection and
rejects a changed subject or counter-kind snapshot before any counter changes.
Two-Headed Giant shared poison totals, repeated or variable Proliferate,
Proliferate replacement effects, and broader granted/copy propagation remain
explicitly unsupported.

The bounded Explore family compiles source/self and “target creature you
control” instructions to CardProgram V2. It publicly reveals the current
controller's top card, uses a replacement-aware zone move for a revealed land
or chosen nonland, places the counter only on the same current phased-in
logical incarnation, and emits one typed completion event. Its preparation
continuation pins the exact counter or zone intent, so a replacement choice
cannot repeat the prior reveal. Controller last-known information is captured
when the source leaves the battlefield. Simultaneous multi-permanent Explore,
repeated Explore, Explore replacement effects, and broader granted/copy
propagation remain explicit residuals.

The following producers and wordings remain deliberately outside this slice:

- Saga lore rule actions and stun-counter removal;
- loyalty activation costs and damage-counter removal;
- cumulative upkeep;
- optional, variable, distributed, set-based, fixed player-counter, and
  multiple-counter placement clauses;
- conditional targets and non-creature subtype predicates;
- Fabricate counter choices now suspend and resume through the typed semantic-completion continuation, while zero, variable, copied, and granted Fabricate variants remain explicit compiler residuals;
- Planeswalker or Battle token entry with an applicable quantity replacement
  remains fail closed until token creation has an identity-pinned resumable
  continuation; replacement-free token entry uses the canonical counter owner;
- unsupported Battle subtype protector procedures and unrepresented
  copy-layer, face-down, or dynamic entry-characteristic interactions;
- counter removal and movement, state-based removals, and card-specific
  continuation paths such as Demonic Junker.

Several of those operations occur inside a larger semantic continuation after
earlier instructions have already mutated state. Routing them through a choice
that can suspend would replay prior side effects unless the enclosing
instruction first gains a typed resumable frame. They are recorded blockers,
not silently approximated migrations.

The component also excludes fractional or halving replacements, dynamic
quantities, counter movement, prevention, other enters-with-counter wordings,
and universal placing-player derivation. Broad CR 122/614/616 stays blocked
until those families and producers are integrated.

Primary assurance is in `test_counter_placement_replacements.py`,
`test_proliferate_rules.py`, `test_proliferate_compiler.py`, and
`test_fixed_counter_placement_effects.py`, plus intrinsic entry coverage in
`test_intrinsic_entry_counters.py`, with shared event-order coverage in
`test_replacement_event_tree.py` and focused mutation evidence in
`test_capability_implementation_mutations.py`.

Current aggregate corpus counts and remaining blockers are generated in
[`docs/COMPILER_COVERAGE_STATUS.md`](../COMPILER_COVERAGE_STATUS.md). They
measure represented behavior against the pinned corpus, not matchup results or
complete Oracle correctness.
