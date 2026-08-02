---
title: "CardProgram runtime components"
status: "current"
authoritative_source: "mtg_commander_sim/semantic_runtime component registries and ADRs 0007/0010"
verified: "2026-08-02"
audience: "rules, compiler, runtime, replay, and extension contributors"
maintenance: "hand-maintained"
---

# CardProgram runtime components

Runtime components represent CardProgram behavior that participates outside one
immediate stack-resolution instruction. Family registries own validation and
lowering; the global inventory only provides stable metadata and a fingerprint.
Components receive bounded read-only contexts and return immutable replacement
effects or continuous effects. They never receive `CommanderEngine`, mutable
`GameState`, projection internals, or persistence objects, and they never
mutate state.

Every registered handler declares a stable ID, schema version, exact family and
event, rule references, capability dependencies, strict descriptor validator,
and deterministic inventory entry. A malformed descriptor for a registered ID
fails closed. Only an entirely unregistered legacy operation may use the
measured compatibility dispatcher.

## Current bounded families

`replacement.token.additional.v1` supports a mandatory fixed additional-token
result for its declared token type and controller. Multiple current effects use
the affected controller's seat-scoped order, effects created by earlier
applications are rediscovered, and the exact event path and selection journal
replay. Added tokens receive their own default status rather than inheriting
the original token's tapped, attacking, protector, or temporary-keyword state.
The family does not claim optional descriptors, quantity doubling, or state-
derived token definitions.

`replacement.zone.destination.v1` supports a reviewed source-stamped zone-
destination replacement and fixed counter intents. It uses the controller of
an object on the battlefield or stack and the owner otherwise, prepares
simultaneous changes against the same pre-move source snapshot, and suspends
competing choices to the affected seat. Dauthi Voidwalker's reviewed behavior
is the current source-pinned witness; the engine no longer selects it by
Oracle ID. Its counter intent is not yet routed through a universal counter-
placement replacement boundary, so broad CR 614/616 remains blocked.

`continuous.anthem.power_toughness.v1` supports a fixed same-controller subtype
anthem in layer 7c. The source must be represented, on the battlefield, and not
phased out. Applicability uses characteristics produced by prior layers, and
independent sources stack by timestamp and component identity. It does not
claim CDAs, base-setting, state-derived modifiers, ability removal, same-layer
dependencies, or complete CR 613.

## Participation and assurance

Descriptors live inside the canonical CardProgram fingerprint. Strict preflight
binds their dependencies to the applicable capability closure. Game Record v3
pins the component inventory and registry fingerprint, and exact replay rejects
drift. Component contexts contain only public or source-authorized facts; no
component expands a principal projection.

Continuous collection is currently uncached. Instrumentation counts collection
calls, battlefield objects inspected, CardProgram lookups, descriptors
inspected, and effects produced for deterministic benchmark scenarios. The
structural baseline is CI-gated; latency is observational until a stable budget
exists. Any future cache requires exact invalidation for state, program,
component, timestamp, characteristic, and ruleset changes.

`token_creation.py` is the focused authoritative mutation owner for token
commit and enter-event dispatch. `replacement_effects.py` and
`replacement_decisions.py` own immutable event trees and replayable choice
continuations; runtime components remain pure participants.

Primary tests are `test_replacement_event_tree.py`,
`test_token_creation_replacements.py`, `test_graveyard_rules.py`,
`test_continuous_effect_components.py`, `test_card_program_trust.py`, and
`test_continuous_effect_performance.py`. See the
[extension guide](../extension/runtime-component.md) and
[ADR 0007](../adr/0007-cardprogram-runtime-components.md) plus
[ADR 0010](../adr/0010-replacement-event-tree-and-token-owner.md).
