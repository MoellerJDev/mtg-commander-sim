---
title: "Semantic node extension guide"
status: "current"
authoritative_source: "Oracle IR and semantic executor implementation"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
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
- Execute through a generic registered operation with transactional validation.
- Add compiler positive/negative tests and runtime legal/illegal, rollback,
  replay, projection, and interaction tests.
- Update capability dependencies and generated coverage artifacts.

New operations cannot be registered casually: the architecture baseline
ratchets the operation vocabulary. A new compiler stage, schema version, or
custom runtime extension interface requires an ADR.
