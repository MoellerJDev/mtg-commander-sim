---
title: "ADR 0005: canonical CardProgram V2"
status: "ADR"
authoritative_source: "this decision record"
verified: "2026-08-01"
audience: "rules, compiler, replay, and semantic-pack contributors"
maintenance: "hand-maintained"
adr_id: "0005"
decision_status: "accepted"
date: "2026-08-01"
---

# ADR 0005: canonical CardProgram V2

## Context

Generated Oracle IR, hand-authored semantic packs, runtime ability lookup, and
Game Record provenance previously described related behavior through separate
card-level and ability-level views. `SemanticProgram` was executable and
source-pinned, but there was no canonical card aggregate containing every
ability family, face identity, residual, capability closure, and replayable
program fingerprint.

A wholesale semantic-pack rewrite would make historical Game Record v3 files
unreplayable. Letting both representations evolve independently would create a
second rules authority and allow silent disagreement.

## Decision

Introduce CardProgram schema version 2 as the canonical card aggregate. It
contains pinned card/face identity and source hashes; stable ability IDs;
typed projections for timing, costs, modes, targets, choices, effects,
triggers, static/replacement/prevention/continuous effects, linkage,
durations, delayed behavior, copying, and zone permissions; source spans;
capabilities; residuals; provenance; semantic/trust hashes; and a deterministic
artifact fingerprint.

Existing `SemanticProgram` objects remain the executable ability objects
inside the aggregate. Semantic pack v3 files are compatibility inputs and are
adapted deterministically by Oracle ID. The registry's legacy `programs` map
is a derived key index for current engine callers and historical record
readers. Saved registries also contain CardProgram V2 objects; loading rejects
any disagreement between the canonical and compatibility views.

Generated Oracle IR lowers into the same aggregate, with reviewed pack
abilities overriding the same semantic key. Missing source metadata is allowed
only as an explicitly untrusted compatibility case. Conflicting nonempty
source hashes, ambiguous face ownership, stale source hashes, residuals,
fingerprint mismatch, or typed/runtime projection mismatch fail closed.

Game Record v3 remains version 3. New manifests add the complete CardProgram
fingerprint map, and commands add fingerprints for programs actually used.
Replay validates those fields when present; historical records without them
retain their existing semantic-registry verification.

## Alternatives

- Replace semantic packs and Game Record v3 immediately. Rejected because it
  breaks replay compatibility without improving rules behavior.
- Keep only independent per-ability hashes. Rejected because face/card
  residuals and cross-ability trust would remain unauditable.
- Store CardProgram and `SemanticProgram` as unrelated authorities. Rejected
  because mismatches could silently select different runtime behavior.
- Parse Oracle text during a state transition. Rejected because runtime
  determinism requires pinned compiled artifacts.

## Consequences

- `mtg_commander_sim/card_programs/` owns the pure schema model, adapters,
  audit commands, and runtime identity/source validation. It owns no game
  state and performs no state mutation.
- `SemanticRegistry` owns canonical grouping and the derived semantic-key
  index. The engine retrieves compiled abilities and never parses Oracle prose
  during a transition.
- `simctl card compile|explain|audit|diff|overrides|coverage` is the supported
  inspection surface; the older `oracle` commands remain compatibility tools.
- CardProgram V2 does not imply full Oracle or rules coverage. Empty typed
  families and residual/trust blockers remain explicit.
- Phase 4 may replace central effect-operation dispatch with typed handlers
  without another card-program schema split.
