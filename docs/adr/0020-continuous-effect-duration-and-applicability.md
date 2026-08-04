---
title: "ADR 0020: continuous-effect duration and applicability ownership"
status: "ADR"
authoritative_source: "this decision record and platform/architecture-policy.json"
verified: "2026-08-03"
audience: "rules, compiler, semantics, replay, projection, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0020"
decision_status: "accepted"
date: "2026-08-03"
---

# ADR 0020: continuous-effect duration and applicability ownership

## Context

Temporary type, subtype, keyword, and power/toughness changes were stored in
mutable card annotations. Static CardProgram components produced layer values,
but authoritative evaluation and seat projection did not consume the same
effect set. The model also could not express the CR 611 distinction between a
resolution-created effect whose affected objects are fixed and a static
ability whose membership changes continuously.

Extending the annotation vocabulary would have made duration, source presence,
object incarnation, serialization, replay, and projection correctness depend
on more ad hoc engine branches.

## Decision

`continuous_effect_model.py` owns the strict, deeply immutable, versioned
continuous-effect value model. An effect declares its origin, duration, layer,
sublayer, operations, source identity, applicability predicate, and—when
required—an exact set of physical plus logical object identities. Equivalent
construction order has one canonical fingerprint and deserialization rejects
unknown or malformed fields.

`continuous_effect_state.py` owns the additive authoritative journal for
resolution-created effects. The rules transaction resolves a predicate once,
locks the matching physical/logical objects, and commits the effect only after
all source and operation facts validate. Until-end-of-turn effects expire at
cleanup. A card that changes zones is a new logical object and does not retain
membership; control changes alone do not replace the object.

Static CardProgram components remain pure. They emit live `ObjectQuerySpec`
predicates and a source identity; applicability is recomputed from current
characteristics and ends when the source is absent, phased out, or no longer in
its represented source zone. `characteristic_evaluation.py` is the shared
layer evaluator used by both `CommanderEngine` and principal-scoped projection.

`GameState.continuous_effects` is an additive Game Record v3 checkpoint field.
Its absence means an explicitly historical record whose temporary effects use
the prior annotation representation; it is never silently synthesized into a
new journal during replay.

Oracle IR v23 lowers only closed fixed-query static power/toughness wording and
closed controlled-creature until-end-of-turn modifiers. Stateful quantities,
combat-only qualifications, targets whose dependency closure is incomplete,
permissions, control changes, and unsupported duration grammar remain material
residuals.

## Alternatives

- Continue adding temporary annotations. Rejected because annotations lack a
  closed duration, source, applicability, and replay contract.
- Recompute every resolution-created affected set continuously. Rejected
  because it violates CR 611.2c for the represented object-modifying effects.
- Persist evaluated characteristics instead of effect values. Rejected because
  static membership and earlier-layer changes must be reevaluated from current
  state.
- Give projection a separate lightweight evaluator. Rejected because it could
  display characteristics different from those used for legality.

## Consequences

- Represented resolution-created and static effects now have different,
  explicit applicability semantics and share one evaluator.
- Temporary effects, exact replay, save/load, source departure, control change,
  object reentry, multiplayer evaluation, and projection are independently
  testable without authoritative IDs entering client packets.
- `CommanderEngine` loses base-card adaptation and the legacy layered evaluator;
  the compiler gains reusable static and temporary modifier families rather
  than card-name dispatch.
- Complete CR 611 duration grammar, player/rules-modifying effects, control-
  changing effects, dependency discovery, CDA closure, and complete CR 613
  layer behavior remain outside this decision.
