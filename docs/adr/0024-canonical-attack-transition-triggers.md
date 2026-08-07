---
title: "ADR 0024: canonical attack-transition trigger ownership"
status: "ADR"
authoritative_source: "this decision record and typed attack-transition implementation"
verified: "2026-08-06"
audience: "rules, compiler, replay, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0024"
decision_status: "accepted"
date: "2026-08-06"
---

# ADR 0024: canonical attack-transition trigger ownership

## Context

Attack-triggered keyword families need the same completed declaration facts,
but their eligibility and affected objects differ. Deriving each family inside
`CommanderEngine`, reparsing Oracle text at runtime, or reading mutable combat
state during resolution would create competing authorities and make source
departure, multiplayer ordering, rollback, and replay unreliable.

Some generic keyword and display values, including `melee` and `Battle Cry`,
also collide with printed card names in the architecture specificity scanner.
Those values are rules vocabulary rather than card dispatch and therefore need
an explicit, narrowly reviewed allowance.

## Decision

One immutable canonical attack-transition value seals the declared attackers,
their recipients, current controllers, logical identities, and typed keyword
fragments after a complete legal declaration. Pure derivation creates ordinary
Exalted, Battle Cry, and Melee trigger occurrences from that value. The shared
trigger subsystem owns APNAP placement, and the continuous-effect subsystem
owns identity-pinned layer 7c results until end of turn.

The compiler lowers only closed printed keyword grammar to typed ability
fragments with source spans and fine-grained capabilities. Runtime code consumes
those fragments and never branches on printed names or Oracle IDs. Conditional,
granted, copied, face-down, put-attacking, and trigger-modification variants
remain explicit residuals until their dependencies are represented.

The ADR-bound specificity refresh records only the generic keyword literals
introduced by this family. It does not authorize card-specific conditionals,
helpers, operations, or overrides.

## Alternatives

- Discover each keyword independently from mutable combat state. Rejected
  because later control, zone, and characteristic changes would rewrite the
  triggering event.
- Resolve the bonuses directly in the engine. Rejected because temporary
  power/toughness mutation already has a canonical continuous-effect owner.
- Treat all attack-trigger wording as equivalent to the printed keywords.
  Rejected because conditions, granted abilities, and rules-text variants have
  different capability and interaction dependencies.

## Consequences

- Represented attack-trigger families share one deterministic event identity,
  multiplayer ordering boundary, rollback path, and replay serialization.
- Advertised combat relationships and accepted declarations feed the same
  sealed transition.
- Keyword literals that coincide with card names remain reviewable without
  weakening the printed-name growth guard.
- Additional attack-trigger families can reuse the transition only after their
  own typed grammar, capability closure, and resolution owner are certified.

## Removal condition

The narrow engine adapter may disappear when declaration coordination consumes
the typed transition port directly. The residual boundaries may be removed only
when their characteristic, copy, face-down, put-attacking, and trigger-changing
dependencies are implemented and evidenced.
