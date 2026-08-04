---
title: "ADR 0019: normalized zone-change trigger discovery"
status: "ADR"
authoritative_source: "this decision record and platform/architecture-policy.json"
verified: "2026-08-03"
audience: "rules, compiler, semantics, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0019"
decision_status: "accepted"
date: "2026-08-03"
---

# ADR 0019: normalized zone-change trigger discovery

## Context

The canonical zone-move path committed an object move and then asked a large
`CommanderEngine` method to reconstruct several enter, leave, dies, discard,
and graveyard events from mutable live state. Trigger matching, condition
evaluation, additional-trigger handling, and ordinary stack-item construction
were also embedded in the engine. This made last-known-information behavior
difficult to test independently and gave generic Oracle lowering no explicit
capability for the event-detection dependency.

The unified CR 603.3 batch from ADR 0018 already owns APNAP placement after an
ability has triggered. Detection must feed that owner without creating another
queue or teaching the detector to mutate a game.

## Decision

`zone_trigger_events.py` owns a strict immutable version-1
`ZoneChangeOccurrence`. The canonical move adapter captures stable physical and
logical identity, old and new controller, old and new characteristics,
attachments, zone-change counter, and public move reason at the commit
boundary. Every supplied value is deep-frozen, canonical serialization has a
stable fingerprint, and malformed values fail before discovery.

The pure `normalized_zone_trigger_events` function derives the represented
closed vocabulary. Enter events use current characteristics and the live
battlefield source set. Leave-the-battlefield and dies events use previous
characteristics, previous controller, and the source-zone snapshot captured
before the simultaneous move. `zone_trigger_processing.py` coordinates these
facts with turn history, legacy compatibility hooks, Saga lore, and the single
ordinary trigger batch.

`trigger_discovery.py` owns read-only semantic event matching, declarative
condition evaluation, controller-at-trigger-time selection, and generic
`StackItem` construction. It imports no engine and receives only a narrow host
protocol. Additional-trigger behavior is identified from generic Oracle facts
and chosen-type state, not a printed card name. The engine retains thin
compatibility methods for existing callers and isolated legacy special cases.

Oracle IR v22 declares `trigger.event.normalized_zone_change` separately from
`trigger.placement.apnap` and from the effect result capability. Exact,
capability-closed generated trigger programs may be trusted at session load;
an exact permanent spell is auto-resolved only when every represented trigger
program for it is current, trusted, and needs no arbiter. Thus fixed self-ETB
life triggers compose the normalized event, ordinary stack placement, and
canonical life transaction, while a draw trigger remains provisional until
the draw capability closes.

## Alternatives

- Keep reconstructing events inside `CommanderEngine`. Rejected because it
  preserves mutable-state coupling and prevents independent LKI evidence.
- Persist a second trigger journal or zone-trigger queue. Rejected because ADR
  0018 already owns the ordinary occurrence and placement boundary.
- Promote every syntactically exact generated program. Rejected because exact
  parsing is not capability closure; promotion is limited to exact trigger
  programs whose event, placement, and result dependencies are trusted.
- Treat all draw-to-hand moves as trusted while compiling ETB draw creatures.
  Rejected because draw replacement and complete draw-event participation are
  still explicit blockers.

## Consequences

- Simultaneously departing sources can observe represented deaths using one
  immutable pre-event snapshot.
- Event derivation and semantic trigger discovery are independently testable,
  canonical, replay-stable, and free of `GameState` mutation ownership.
- `CommanderEngine` loses the generic zone-event construction and trigger-
  discovery implementations while retaining historical compatibility seams.
- Generic fixed-life self ETB/dies templates can become capability-closed
  without one handler per card.
- Complete CR 603 event grammar, every CR 603.6/603.10 exception, intervening-
  if closure, delayed creation, reflexive and state triggers, hidden-zone
  visibility, and draw replacement remain outside this bounded decision.
