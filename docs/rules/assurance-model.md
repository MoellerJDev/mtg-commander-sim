---
title: "Rules assurance model"
status: "current"
authoritative_source: "pinned rules corpus, conformance records, capability registry, CardPrograms, and generated coverage"
verified: "2026-08-06"
audience: "rules, compiler, engine, and assurance contributors"
maintenance: "hand-maintained"
concern: "rules-assurance"
---

# Rules assurance model

The rules program links a pinned Comprehensive Rules paragraph and Oracle/ruling
snapshot to reusable implemented behavior and executable evidence. It controls
claims; it is not a checklist whose completion can be inferred from a parser
match, witness card, test name, or generated row.

MTG Commander Sim is a partial, snapshot-scoped implementation. Current states,
counts, fingerprints, and blockers are generated in
[rules status](../RULES_COMPLETENESS_STATUS.md),
[compiler status](../COMPILER_COVERAGE_STATUS.md),
[rules coverage](../../coverage/rules-coverage.md),
[conformance coverage](../../coverage/rules-conformance.md), and the
[dependency queue](../RULES_DEPENDENCY_QUEUE.md).

## Source precedence

Use this order when evidence disagrees:

1. pinned source text and implemented executable behavior;
2. versioned schemas, machine-readable policy, and source manifests;
3. executable tests and mutation results tied to exact components;
4. generated coverage and dependency reports;
5. current explanatory documentation;
6. ADRs and the changelog as historical rationale.

The official downloaded rules prose and full card-data exports remain ignored
local inputs. Tracked indexes retain source IDs, hashes, spans, classification,
dependencies, and reviewed summaries rather than redistributing the prose.

## Assurance artifacts

- `rules/manifest.json` pins derived rules and card-data source identity.
- `rules/rule-index.json`, `glossary-index.json`, and `mechanic-index.json`
  inventory source-linked records without rules prose.
- `rules/conformance-cases.json` stores one stable claim record per reviewed
  rules unit.
- `rules/conformance-reviews/` stores subsystem reviews and evidence mappings.
- `rules/dependency-graph.json` and `platform/rules-subsystems.json` describe
  dependency and ownership scheduling.
- `mtg_commander_sim/rules/capability-registry.json` and generated evidence
  define fine-grained executable trust.
- CardPrograms bind Oracle spans to required capabilities and runtime
  descriptors.
- `coverage/*.json` and compressed JSON own complete measured inventories;
  generated Markdown is a navigation and top-state view.

Derived records never replace source meaning. A successful structural validator
proves internal consistency, not rules completeness.

## Classification model

A conformance record distinguishes:

- `unreviewed`: inventoried but not behaviorally assessed;
- `definition_only`: terminology or structure with no independent transition;
- `blocked`: required behavior or dependency is missing;
- `partial`: a bounded represented slice has evidence while the broader claim
  remains open; and
- `passing`: every declared in-scope behavior and dependency has current
  executable evidence for the supported profiles.

Parser statuses such as exact, partial, and unresolved describe Oracle
representation, not rule conformance. Capability-closed and trusted CardProgram
are stronger but separate card/runtime claims. A broad rule remains blocked
when an applicable interaction or dependency is unresolved even if one
subsection or card works.

## Generic card-support path

```text
pinned rules + Oracle + rulings
             |
       typed Oracle IR
             |
    source-spanned CardPrograms
             |
capability + interaction + profile closure
             |
typed queries, proposals, coordinators, and mutation owners
```

Equivalent supported wording benefits every card. Unsupported wording remains
a precise residual and fails strict preflight. Reviewed card overrides are
compatibility exceptions; repeated descriptors must become a generic compiler
production and rules family.

## Trust requirements

Every behavioral claim declares the applicable evidence classes:

- positive behavior and negative/unavailable behavior;
- malformed-input rejection and transactional rollback;
- multiplayer, APNAP, affected-player/controller, and simultaneous choices;
- exact replay, canonical hashes, and save/load for persistent state;
- privacy/projection for hidden information and private choices;
- replacement, prevention, copy, layers, zone identity, and Commander
  interactions where reachable;
- dependency and unsupported-variant fail-closed behavior;
- bounded property or fuzz exploration for meaningful state spaces; and
- a focused killed implementation mutation.

An omitted applicable class requires a reviewed not-applicable rationale.
Evidence IDs must resolve to current tests and implementation components.
Missing dependencies, surviving critical mutations, source drift, or stale
generated data block trust.

## Rules-family acceptance

A coherent rules family:

1. implements reusable Comprehensive Rules behavior through one typed owner;
2. routes every represented producer through that owner;
3. shares advertisement and command validation;
4. removes the competing legacy path;
5. lowers applicable Oracle grammar without runtime text parsing;
6. declares precise capabilities and ambient interactions;
7. rejects unsupported variants before mutation;
8. preserves record, replay, projection, and compatibility contracts;
9. improves or holds measured ownership, direct-write, and specificity debt;
10. regenerates affected rules/card reports once at the final exact head.

Do not select work one numbered rule at a time or preserve a false positive to
avoid a measured demotion. Prefer a subsystem-sized family that removes a
shared blocker and has one reviewable mutation boundary.

## Invalidation and replay

Rules, Oracle, rulings, compiler, capability, interaction, semantic, and
implementation fingerprints form one trust chain. Changing a source or owner
invalidates dependent evidence until regeneration and tests pass. Game replay
uses the identity pinned at creation; an old record is never reinterpreted as
if it used current rules or card data.

## Commands

```powershell
.\.venv\Scripts\python.exe simctl.py rules verify --root .
.\.venv\Scripts\python.exe simctl.py rules coverage
.\.venv\Scripts\python.exe simctl.py rules queue
.\.venv\Scripts\python.exe simctl.py rules next
.\.venv\Scripts\python.exe simctl.py pieces next
.\.venv\Scripts\python.exe scripts\update_rules_scheduler.py --check
```

Run focused evidence during implementation, regenerate full-corpus artifacts at
the final head, and require normal exact-head CI before merging behavioral or
generator changes.

## Claim boundary

Never describe the project as complete Magic or Commander rules support.
Generated status states exactly which snapshot-scoped records, CardPrograms,
capabilities, and profiles close and which blockers remain. Matchup or deck
claims require separate terminal replay, privacy, legal-action exposure,
provider, and sample-methodology gates beyond rules conformance.
