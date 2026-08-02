---
title: "Architecture decision records"
status: "current"
authoritative_source: "docs/adr decision records"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "maintainers and architecture contributors"
maintenance: "hand-maintained"
---

# Architecture decision records

ADRs are immutable decision history. Supersede an accepted ADR with a new one;
do not rewrite its outcome. Use the [template](template.md) for decisions that
change dependencies, persistence, CardProgram/compiler schemas, runtime
extension interfaces, mutation ownership, replay, ruleset pinning, trust,
deployment modes, or architecture review thresholds.

- [ADR 0001 — one serialized writer per game](0001-single-writer-game-actor.md)
- [ADR 0002 — seat-projected network protocol](0002-seat-projected-network-protocol.md)
- [ADR 0003 — ratcheted architecture and documentation enforcement](0003-ratcheted-architecture-enforcement.md)
- [ADR 0004 — fine-grained capability trust](0004-fine-grained-capability-trust.md)
- [ADR 0005 — canonical CardProgram V2](0005-card-program-v2.md)
- [ADR 0006 — typed semantic handler boundary](0006-typed-semantic-handler-boundary.md)
- [ADR 0007 — CardProgram runtime components](0007-cardprogram-runtime-components.md)
- [ADR 0008 — runtime trust and default-deny architecture governance](0008-runtime-trust-and-governance-hardening.md)
- [ADR 0009 — typed tap-state effects and focused mutation ownership](0009-typed-tap-state-mutation-owner.md)
- [ADR 0010 — replayable replacement-event trees and token mutation ownership](0010-replacement-event-tree-and-token-owner.md)
- [ADR 0011 — counter-placement event and mutation ownership](0011-counter-placement-event-and-mutation-owner.md)
- [ADR 0012 — damage transaction and static prevention ownership](0012-damage-transaction-and-static-prevention.md)
- [ADR 0013 — typed damage-result event ownership](0013-damage-result-event-ownership.md)
