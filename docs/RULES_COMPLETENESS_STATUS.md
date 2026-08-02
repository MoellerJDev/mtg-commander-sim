---
title: "Rules completeness implementation status"
status: "current"
authoritative_source: "pinned rules and generated coverage artifacts"
verified: "2026-08-01"
audience: "rules, compiler, and engine contributors"
maintenance: "hand-maintained"
---

# Rules completeness implementation status

This document states the current rules boundary without duplicating generated
metrics. Exact counts and source fingerprints live in
[`COMPILER_COVERAGE_STATUS.md`](COMPILER_COVERAGE_STATUS.md); architecture and
test debt live in [`ARCHITECTURE_DEBT_STATUS.md`](ARCHITECTURE_DEBT_STATUS.md).
Dependency-ordered rules work lives in the generated
[`RULES_DEPENDENCY_QUEUE.md`](RULES_DEPENDENCY_QUEUE.md).

## Claim boundary

The simulator is a deterministic, replayable partial implementation of Magic
and Commander. It does not implement the complete Comprehensive Rules or every
Oracle card interaction. A generated card program is trusted only when its
required capabilities are implemented and validated; parsing text without that
closure is not evidence of executable correctness.

Unknown or materially unresolved semantics must fail closed. A test that only
proves source inventory or parsing does not prove game behavior. Browser,
server, provider, and pilot success never promote rules fidelity by themselves.

## Implemented foundation

- A pinned Comprehensive Rules corpus, Oracle snapshot, and rulings snapshot
  support deterministic inventories and reproducible source references.
- Oracle IR v12 provides source-spanned partial compilation and material
  residuals. Generated and reviewed abilities aggregate into deterministic
  CardProgram V2 artifacts with source, capability, trust, and replay
  fingerprints. Compilation remains partial and interleaved.
- Game Record v3 records accepted commands and supports exact deterministic
  replay for represented behavior.
- The engine represents ordinary turn and priority structure, zones and object
  incarnations, the stack, mana and costs, targets and choices, state-based
  actions, combat, Commander state, and selected continuous, replacement,
  prevention, trigger, and copy behavior.
- Typed helpers exist for several rules families. Six registered semantic
  handlers cover draw, table-wide draw, monarch, and three bounded tap-state
  operations. Their handlers are read-only; tap-state intent commit is owned by
  a focused rules module. Most other orchestration and mutation remains
  centralized in `CommanderEngine`.
- Reviewed semantic packs close selected card and interaction slices through
  an explicit `legacy_reviewed` compatibility basis. They are not
  capability-closed evidence or universal Oracle support.

## Known incomplete families

The generated compiler report is authoritative for exact residual categories.
The principal architectural and behavioral gaps include:

- complete continuous-effect layers, dependencies, timestamps, and CDAs;
- universal replacement/prevention event production and affected-player
  ordering;
- full alternate/additional costs, restricted mana, and cost-modification
  ordering;
- broad zone-casting permissions, special actions, face-down objects, linked
  abilities, copy effects, and merged permanents;
- complete target, search, trigger-order, loop, shortcut, multiplayer, and
  combat edge cases;
- broad fine-grained capability closure and migration of the remaining central
  semantic operations into the typed-handler boundary;
- property, differential, mutation, and performance gates at the target level.

## Current migration rule

Integrated runtime trust and governance hardening supplies generated explicit
capability evidence, separate dependency and implementation-mutation status,
CardProgram trust bases, intrinsic/format/match/dynamic closure, strict
handler/component binding, compatibility provenance, default-deny module and
stable-write governance, and an uncached continuous-effect structural
benchmark. Fixed additional-token replacements and fixed subtype anthems remain
bounded promises; neither general CR 616 ordering nor complete CR 613
dependencies are implied.

The measured Phase 2 migration routes `tap`, `untap`, and
`untap_all_creatures` through strict typed nodes and intents and a focused
tap-state mutation port. It removes their legacy `apply_effect` branches,
preserves stun-counter replacement, uses effective creature types, skips
phased-out permanents, and emits events only for actual state changes. The
three capabilities remain tested and blocked rather than trusted because
complete tap/untap prohibitions, general replacement ordering, and complete
derived-characteristic closure are not yet represented.

The complete traditional/Commander format-capability inventory is still
absent, so capability-only strict match creation fails closed while reviewed
declared-pool compatibility remains available. Each later slice must continue
to remove or migrate one coherent reusable responsibility before broad corpus
expansion resumes.

The scheduler conservatively queues every reviewed blocked behavioral rule and
every unclassified nonpassing rule. Its first selected implementation batch is
the coupled replacement-choice and nested-event cluster in CR 614/616. That is
a bounded next slice, not a declaration that all replacement or prevention
semantics can be completed in one pass.

Do not add a card-name branch to the core engine. A genuinely exceptional card
must use the eventual typed override boundary with source fingerprints,
capability requirements, interaction tests, replay tests, and an explicit
removal or permanence decision.

## Contributor workflow

Use the generated reports instead of hand-copying counts:

```bash
python scripts/update_architecture_audit.py --check
python scripts/update_rules_scheduler.py --check
python simctl.py rules verify
python simctl.py rules coverage
python simctl.py rules queue
python simctl.py rules next
```

When a coverage artifact changes intentionally, regenerate the corresponding
status document in the same commit. The repository validator rejects stale
generated outputs.
