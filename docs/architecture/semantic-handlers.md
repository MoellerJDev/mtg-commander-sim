---
title: "Typed semantic handlers"
status: "current"
authoritative_source: "mtg_commander_sim/semantic_runtime and platform/architecture-policy.json"
verified: "2026-08-07"
audience: "rules, compiler, and replay contributors"
maintenance: "hand-maintained"
---

# Typed semantic handlers

Typed semantic handlers execute one immediate CardProgram instruction. They
translate a validated typed node and bounded immutable rules query into typed
intents. Canonical engine or focused mutation owners commit those intents.
Handlers never receive mutable `GameState`, private projections, persistence
objects, or unrestricted engine access.

```mermaid
flowchart LR
    Node["CardProgram effect node"] --> Registry["Frozen handler registry"]
    Query["Immutable rules query"] --> Handler["Typed handler"]
    Registry --> Handler
    Handler --> Intent["Typed intent"]
    Intent --> Owner["Canonical mutation owner"]
```

Every registration declares a stable handler ID, schema version, exact
operation family, rule references, and bounded capability dependencies.
Duplicate ownership and unknown capabilities are rejected. Malformed input to
a registered operation is a rules error and cannot fall back to permissive
string dispatch. Strict preflight fingerprints the registry and recomputes its
capability closure.

Family modules own lowering; the aggregate registry owns only discovery and a
stable inventory. A handler may request a narrowly defined continuation for a
choice or replacement-aware transaction, but it may not retain mutable state
or commit around the canonical owner. Rollback must leave no partial mutation.

Behavior that participates in later events—replacements, prevention, static
effects, and other persistent descriptors—belongs to
[runtime components](runtime-components.md), not this boundary. Family-specific
mutation and ordering contracts belong in subsystem documents such as
[drawing](drawing.md), [damage](damage.md), [prevention](prevention.md), and
[counter placement](counter-placement.md). Direct permanent destruction,
permanent exile, and return-to-owner-hand instructions lower through strict
handlers into identity-pinned transactions; none reparses Oracle text or owns
the underlying counter or zone mutation. Broad legacy exile operations remain
separate because they also represent stack and hidden-zone movement outside the
direct battlefield-target grammar.

The direct-target compiler families share structural builders for their one
effect, closed target schema, and mechanics tuple, while each family retains
its own grammar and capability owner. Their runtime handlers likewise share
strict operation, reference, reason, and immutable replacement-selection field
validation. This shared code does not choose a target, infer a card family, or
create a generic move operation.

Mandatory direct stack counters lower through a separate strict handler to one
typed intent. The focused stack owner performs counterability, stack removal,
replacement-aware physical spell movement, normalized pre-counter and
post-graveyard event dispatch, and journaling; target legality and source exclusion
come from the same closed schema used by action offers. The exact intrinsic
sentence “This spell can't be countered” is compiled once as a trusted
stack-active declaration and pinned during cast commit. Conditional counter
clauses, countered ability and spell-copy look-back triggers, and broader
prohibitions remain residual rather than falling back to runtime Oracle parsing.

To migrate an instruction, characterize existing output and replay, define the
smallest typed node/query/intent surface, register one stable handler, add
success and malformed-input rollback tests, and remove every parallel dispatch
path. Registration does not itself raise the trust level of any CardProgram.

See [ADR 0006](../adr/0006-typed-semantic-handler-boundary.md),
[ADR 0009](../adr/0009-typed-tap-state-mutation-owner.md), and
[ADR 0014](../adr/0014-typed-semantic-choice-and-effect-ownership.md),
[ADR 0027](../adr/0027-typed-permanent-destruction.md),
[ADR 0028](../adr/0028-typed-return-to-owner-hand.md),
[ADR 0029](../adr/0029-typed-permanent-exile.md), and
[ADR 0030](../adr/0030-typed-stack-counter.md).
