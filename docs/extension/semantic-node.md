---
title: "Semantic node extension guide"
status: "current"
authoritative_source: "Oracle IR and semantic executor implementation"
verified: "2026-08-07"
audience: "compiler and rules contributors"
maintenance: "hand-maintained"
---

# Semantic node extension guide

Add a semantic node only for reusable Oracle grammar with a deterministic
runtime contract. A node is not trusted merely because parsing succeeds.

## Checklist

- Define a typed schema with closed vocabularies and source spans.
- Specify zones, timing, controller/owner meaning, targets, choices, costs,
  event inputs/outputs, replacement participation, visibility, and replay.
- Lower exact positive grammar and retain unknown suffixes as residuals.
- Reject malformed or ambiguous variants; do not broaden via substring guesses.
- Define a stable typed handler with an immutable query, typed intent, and
  explicit capability dependencies; place family logic in its family module
  and never import engine/state authority.
- Execute intents through canonical mutation methods with transactional
  validation and remove the migrated legacy-dispatch branch.
- Add compiler positive/negative tests and runtime legal/illegal, malformed
  schema, rollback, replay, projection, interaction, and implementation
  mutation tests.
- Update capability dependencies and generated coverage artifacts.

New operations cannot be registered casually: the architecture baseline
ratchets the operation vocabulary. A new compiler stage, schema version, or
custom runtime extension interface requires an ADR.

See the [typed semantic handler architecture](../architecture/semantic-handlers.md)
for the migration sequence and current operation inventory. Bounded examples
include tap state in
[ADR 0009](../adr/0009-typed-tap-state-mutation-owner.md), direct permanent
destruction in [ADR 0027](../adr/0027-typed-permanent-destruction.md), and
direct return to an owner's hand in
[ADR 0028](../adr/0028-typed-return-to-owner-hand.md).
