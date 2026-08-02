---
title: "ADR 0009: typed tap-state effects and focused mutation ownership"
status: "ADR"
authoritative_source: "this decision record and platform/architecture-policy.json"
verified: "2026-08-01"
audience: "rules, semantics, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0009"
decision_status: "accepted"
date: "2026-08-01"
---

# ADR 0009: typed tap-state effects and focused mutation ownership

## Context

The legacy semantic dispatcher directly implemented `tap`, `untap`, and
`untap_all_creatures` inside the oversized `CommanderEngine.apply_effect`
function. That path mixed node validation, object resolution, effective-type
queries, stun-counter replacement, mutation, and event logging. It also logged
an untap that did not happen when a stun counter replaced the action.

The typed semantic boundary established by ADR 0006 requires reusable families
to lower through immutable context and typed intents. Moving these operations
also changes mutation ownership, which requires an explicit decision record.

## Decision

The `permanent.tap_state` semantic family owns three strict registered
operations in `semantic_runtime/tap_state_handlers.py`:

- `tap` lowers to `SetPermanentTappedIntent(tapped=True)`;
- `untap` lowers to `SetPermanentTappedIntent(tapped=False)`;
- `untap_all_creatures` lowers to `UntapAllCreaturesIntent`.

Handlers receive no card object or mutable state. They validate a closed field
schema against `ReadOnlyHandlerContext` and produce typed nodes and intents.
A malformed registered operation fails closed and never falls back to legacy
dispatch.

`mtg_commander_sim/tap_state.py` is a focused rules-layer mutation owner behind
the semantic executor. Its `TapStateHost` protocol exposes only battlefield
object resolution, the existing stun-aware untap primitive, effective
characteristics, deterministic active-seat order, and authoritative logging.
It commits actual state changes and emits no false tap/untap event for an
object already in the requested state. Aggregate creature untap uses effective
types, skips phased-out objects, and applies the stun replacement separately to
each permanent.

The three capabilities remain `tested`, not `trusted`. The implementation does
not claim complete tap/untap prohibitions, replacement ordering beyond the
represented stun-counter rule, or complete derived-characteristic closure.
Those materially reachable interactions remain explicit blockers.

## Alternatives

- Leave the operations in `apply_effect`. Rejected because it preserves mixed
  validation and mutation ownership in the central debt hotspot.
- Give handlers `CommanderEngine` or `GameState`. Rejected because it would
  turn the typed boundary into another mutable monolith.
- Add three new engine methods and call them from the executor. Rejected
  because it grows the engine and does not establish focused ownership.
- Build the complete replacement pipeline before migrating untap. Rejected
  because the existing stun-aware primitive can be preserved exactly while
  the capability remains honestly blocked on broader replacement semantics.

## Consequences

- The semantic-handler registry fingerprint changes from three to six
  handlers, and exact runtime capability evidence binds to the new handler
  module identities.
- The legacy `apply_effect` branch count and engine logical size decrease.
- `tap_state.py` is an explicit replay-participating mutable owner and is
  covered by the default-deny module and direct-write policies.
- Resolution rollback, exact replay, implementation mutation, malformed input,
  stun replacement, effective-type, and phased-object behavior have focused
  deterministic evidence.
- Historical CardPrograms remain `legacy_reviewed` unless their complete
  capability closure is independently trusted; registering these handlers
  does not upgrade their trust basis.

## Removal condition

Replace the transitional `TapStateHost` port when the universal typed mutation
and replacement/prevention transaction pipeline owns tap-state events. That
migration must preserve the registered operations and replay fingerprints or
provide an explicit compatible record migration; it must not move mutable
state authority back into semantic handlers.
