---
title: "CardProgram runtime components"
status: "current"
authoritative_source: "mtg_commander_sim/semantic_runtime component registries and ADR 0007"
verified: "2026-08-01"
audience: "rules, compiler, runtime, replay, and extension contributors"
maintenance: "hand-maintained"
---

# CardProgram runtime components

Runtime components represent CardProgram behavior that participates outside one
immediate stack-resolution instruction. Family registries own validation and
lowering; the global inventory only provides stable metadata and a fingerprint.
Components receive bounded read-only contexts and return typed replacement
intents or continuous effects. They never receive `CommanderEngine`, mutable
`GameState`, projection internals, or persistence objects, and they never
mutate state.

Every registered handler declares a stable ID, schema version, exact family and
event, rule references, capability dependencies, strict descriptor validator,
and deterministic inventory entry. A malformed descriptor for a registered ID
fails closed. Only an entirely unregistered legacy operation may use the
measured compatibility dispatcher.

## Current bounded families

`replacement.token.additional.v1` supports a mandatory fixed additional-token
result for its declared token type and controller. It does not claim optional
replacement, general CR 616 ordering, rediscovery, or quantity doubling.

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

Primary tests are `test_token_replacements.py`,
`test_continuous_effect_components.py`, `test_card_program_trust.py`, and
`test_continuous_effect_performance.py`. See the
[extension guide](../extension/runtime-component.md) and
[ADR 0007](../adr/0007-cardprogram-runtime-components.md).
