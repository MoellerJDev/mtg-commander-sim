---
title: "CardProgram runtime components"
status: "current"
authoritative_source: "quorune/semantic_runtime component registries and schemas/card-program-v2.schema.json"
verified: "2026-08-06"
audience: "rules, compiler, runtime, replay, and extension contributors"
maintenance: "hand-maintained"
---

# CardProgram runtime components

Runtime components represent CardProgram behavior that participates outside a
single immediate resolution instruction. Typical families discover immutable
replacement effects, prevention effects, draw policies, or continuous effects
from live source descriptors. Components participate in a subsystem-owned
transaction; they do not commit state.

## Lifecycle and participation

1. The compiler or reviewed program emits a versioned component descriptor.
2. CardProgram loading validates the descriptor against its registered family.
3. Strict preflight binds the descriptor and capability dependencies to the
   program, component inventory, and game-record fingerprints.
4. The owning subsystem discovers active descriptors through a bounded
   read-only context.
5. A family handler lowers each descriptor to an immutable participant.
6. The subsystem applies ordering and choices, then its canonical mutation
   owner commits the validated plan.

A source leaving its active zone, phasing out, changing incarnation, or
failing its declared predicate stops participating according to the family
contract. Discovery must be deterministic and may not expose facts outside the
requesting principal's authorized projection.

## Descriptor and registry contract

Every family declares a stable handler ID, schema version, event or layer,
rule references, capability dependencies, a strict descriptor validator, and
a deterministic inventory entry. Unknown registered fields, malformed values,
duplicate ownership, and unknown capabilities fail closed. The aggregate
registry provides discovery and a fingerprint only; family modules own
validation and lowering.

Descriptors are part of the canonical CardProgram fingerprint. Historical
records may use an explicit compatibility adapter, but the adapter cannot
rewrite the recorded program or silently promote trust. Current records pin
the descriptor and registry directly.

`ability.activated.mana.color-set.v1` binds a compiler-pinned relative object
query to the activating seat and reads only matching public battlefield
objects or that seat's graveyard. It derives colors from current effective
characteristics, feeds manual offers and automatic payment through the same
mode set, and treats an empty qualifying set as a legal activation that adds no
mana. Runtime code does not parse Oracle prose. Wider dynamic or conditional
mana wording remains residual.

`replacement.token.additional.v2` represents the closed mandatory fixed
additional-token family. Its descriptor carries an optional card-type and
subtype filter plus one immutable token definition. The replacement operation
updates the existing `token.create` event atomically, so newly added token
characteristics participate in the normal replacement rediscovery loop while
the same source cannot apply twice. The token owner commits every resulting
specification with one creation timestamp only after APNAP ordering completes.
The v1 handler remains registered solely for pinned reviewed semantic-pack
compatibility. Optional choices, quantity multipliers, state-derived token
definitions, and modified entry instructions remain unsupported.

## Ownership boundaries

Components receive immutable source-authorized facts, never
`CommanderEngine`, mutable `GameState`, projection internals, or persistence
objects. They do not select by printed card name or Oracle ID. Each subsystem
owns its event model, ordering, replay continuation, validation, and final
commit:

- [damage](damage.md) and [prevention](prevention.md)
- [drawing](drawing.md)
- [counter placement](counter-placement.md)
- token creation through `quorune/token_creation.py`
- [continuous-effect decisions](../adr/0020-continuous-effect-duration-and-applicability.md)

The [extension guide](../extension/runtime-component.md) defines the contributor
workflow. Architectural rationale remains in
[ADR 0007](../adr/0007-cardprogram-runtime-components.md),
[ADR 0010](../adr/0010-replacement-event-tree-and-token-owner.md),
[ADR 0011](../adr/0011-counter-placement-event-and-mutation-owner.md), and
[ADR 0008](../adr/0008-runtime-trust-and-governance-hardening.md).
