---
title: "Rules completeness implementation status"
status: "current"
authoritative_source: "pinned rules and generated coverage artifacts"
verified: "2026-08-02"
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
- Oracle IR v25 provides source-spanned partial compilation and material
  residuals. Generated and reviewed abilities aggregate into deterministic
  CardProgram V2 artifacts with source, capability, trust, and replay
  fingerprints. Compilation remains partial and interleaved.
- Game Record v3 records accepted commands and supports exact deterministic
  replay for represented behavior.
- The engine represents ordinary turn and priority structure, zones and object
  incarnations, the stack, mana and costs, targets and choices, state-based
  actions, combat, Commander state, and selected continuous, replacement,
  prevention, trigger, and copy behavior.
- Typed helpers exist for several rules families. Six registered immediate
  semantic handlers cover draw, table-wide draw, monarch, and three bounded
  tap-state operations. Their handlers are read-only; focused rules modules
  now own tap-state, token creation, effect-generated permanent counters, and
  represented damage commits. Versioned runtime components represent fixed
  token additions, counter and damage quantity changes, fixed damage
  prevention, a fixed subtype anthem, and a reviewed zone-destination
  replacement without printed-name or Oracle-ID engine dispatch. Represented
  CR 615.5 life, permanent-counter, and source-controller-damage aftermath use
  typed precommit owners; nested damage reuses the canonical damage transaction.
  Closed CR 615.13 prevention-result triggers use immutable source-LKI
  occurrences, ordinary APNAP stack placement, represented target-at-placement,
  and the normal effect pipeline rather than immediate aftermath.
  Resolution-created fixed characteristic effects now use an immutable
  duration journal and locked physical/logical object sets; fixed-query static
  power/toughness effects use live source and membership applicability through
  the same evaluator consumed by seat projection.
  Bounded simple-object Auras use one immutable target grammar from compiler
  through casting, resolution, nonspell entry, token preflight, and CR 704
  legality; unsupported Enchant forms fail before mutation.
  Most other orchestration and mutation remains centralized in
  `CommanderEngine`.
- Reviewed semantic packs close selected card and interaction slices through
  an explicit `legacy_reviewed` compatibility basis. They are not
  capability-closed evidence or universal Oracle support.

## Known incomplete families

The generated compiler report is authoritative for exact residual categories.
The principal architectural and behavioral gaps include:

- remaining continuous-effect duration grammar, player/rules/control-changing
  effects, complete layer dependencies, timestamps, and CDAs;
- universal replacement/prevention event production and affected-player
  ordering;
- full alternate/additional costs, restricted mana, and cost-modification
  ordering;
- broad zone-casting permissions, special actions, face-down objects, linked
  abilities, copy effects, merged permanents, and complete Aura/Enchant
  quality and nonbattlefield attachment grammar;
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
benchmark. Immutable replacement-event trees now provide affected-object
identity, APNAP traversal, optional decline, containing-event-before-contained-
event ordering, exact choice journals, and seat-scoped suspension/replay for
the represented token-creation, zone-destination, counter-placement, and damage
producers. Fixed token, zone, counter, damage, prevention, and anthem
components remain bounded promises. The represented CR 611 boundary now
distinguishes locked resolution-created sets from live static membership and
persists until-end-of-turn fixed characteristic effects, but neither universal
CR 614/615/616 participation nor complete CR 611/613 dependencies are implied.

The measured Phase 2 migration routes `tap`, `untap`, and
`untap_all_creatures` through strict typed nodes and intents and a focused
tap-state mutation port. It removes their legacy `apply_effect` branches,
preserves stun-counter replacement, uses effective creature types, skips
phased-out permanents, and emits events only for actual state changes. The
three capabilities remain tested and blocked rather than trusted because
complete tap/untap prohibitions, universal replacement participation, and complete
derived-characteristic closure are not yet represented.

The complete traditional/Commander format-capability inventory is still
absent, so capability-only strict match creation fails closed while reviewed
declared-pool compatibility remains available. Each later slice must continue
to remove or migrate one coherent reusable responsibility before broad corpus
expansion resumes.

The scheduler conservatively queues every reviewed blocked behavioral rule and
every unclassified nonpassing rule. Normalized zone-change triggers, canonical
fixed life results, the shared CR 611 applicability/duration boundary, and the
bounded CR 303 Aura family now compose through typed replayable owners. The
generated compiler report records the resulting exact-card and residual deltas.
The canonical draw transaction, Dredge replacement, APNAP batches, private
continuations, fixed limits, instruction doubling, prospective-drawer optional
legality, iterative large-count coordination, and Oracle IR v27 compiler path
are now represented. Before broader promotion, the next bounded hardening batch
closes continuous-handler identity and qualified-creature grammar; typed Aura
descriptor/protection hardening follows it. CR 121.6c/121.7 draw-result action
and nested ordering remain the next draw semantics boundary after those trust
corrections.

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
