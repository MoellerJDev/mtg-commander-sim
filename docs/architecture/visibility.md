---
title: "Visibility and projection"
status: "current"
authoritative_source: "StateProjector, protocol schemas, and privacy tests"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "client, server, pilot, and security contributors"
maintenance: "hand-maintained"
---

# Visibility and projection

Authoritative state is never a client payload. `StateProjector` derives a
principal-specific full view; delta delivery is computed from projected views.
Players see their own legally known private data, public game data, and their
current capability. Opposing hands and libraries remain counts unless a rule
explicitly makes information known. Spectators receive only public data and no
action capability. Analysts are an out-of-band postgame role.

## Invariants

- A principal cannot be selected by request content; authentication fixes it.
- Projection occurs before transport serialization or patch generation.
- Raw capabilities, physical card IDs, incarnation/timestamp internals, hidden
  event details, pilot memory, and analyst artifacts do not enter another
  principal's view.
- Reconnect starts with a full projection and a new connection cursor.
- Public logs apply visibility filtering independently from live deltas.

## Extension rule

Every new state field, choice, event, zone, semantic node, or server endpoint
must declare visibility for owner, controller, opponent, spectator, and analyst
contexts. Add positive and negative projection tests before exposing it. See
the [privacy testing guide](../testing/privacy.md) and
[threat model](../THREAT_MODEL.md).
