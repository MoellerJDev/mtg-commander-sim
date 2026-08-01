---
title: "Card override extension guide"
status: "current"
authoritative_source: "CardProgram V2 validation, semantic pack compatibility, and compiler trust policy"
verified: "2026-08-01"
audience: "rules and compiler contributors"
maintenance: "hand-maintained"
---

# Card override extension guide

A card override is a last-resort, reviewed program for behavior that cannot yet
be expressed by reusable compiler nodes and capabilities. It belongs in
metadata/override scope, never as a printed-name or Oracle-ID branch in the
kernel.

An override is a CardProgram V2 producer, not a parallel runtime format. It
must emit the same typed ability fields and exact fingerprints as generated or
reviewed pack input. `simctl card overrides` lists only programs with explicit
override metadata; ordinary reviewed semantic packs are not silently relabeled
as typed overrides.

## Required evidence

1. Record the exact Oracle ID, Oracle text hash, rulings hash, rules snapshot,
   semantic schema, and compiler version.
2. Classify every material compiler residual and explain why a reusable node is
   not yet appropriate.
3. Declare zones, timing, targets, costs, choices, events, replacements,
   visibility, replay behavior, and capability dependencies.
4. Add positive, negative, rollback, replay, projection/privacy, and relevant
   interaction tests.
5. Add a removal plan that names the generic capability or compiler family that
   will supersede the override.

An override with a stale source fingerprint is unavailable, not approximately
valid. A third substantially similar override must generalize the common
pattern or carry an ADR explaining why it cannot. Ordinary architecture
allowance refresh also requires an ADR and cannot be hidden inside a card-data
index update.
