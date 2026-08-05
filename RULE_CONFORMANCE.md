---
title: "Comprehensive Rules conformance policy"
status: "current"
authoritative_source: "rules conformance schema, pinned rules corpus, evidence records, and validators"
verified: "2026-08-05"
audience: "rules and assurance contributors"
maintenance: "hand-maintained"
---

# Comprehensive Rules conformance policy

The conformance system links a pinned Comprehensive Rules paragraph to
implemented behavior and executable evidence. It is a claim-control mechanism,
not a checklist whose completion can be inferred from a test name or source
review.

Current counts, rule states and blockers are generated in
[`coverage/rules-conformance.md`](coverage/rules-conformance.md),
[`coverage/rules-coverage.md`](coverage/rules-coverage.md), and
[`docs/RULES_DEPENDENCY_QUEUE.md`](docs/RULES_DEPENDENCY_QUEUE.md).

## Artifacts

- `rules/source-manifest.json` pins the official rules source and hash.
- `rules/rules.jsonl.gz` contains normalized rule records and source spans.
- `rules/conformance-schema.json` defines conformance records.
- `rules/conformance.jsonl` records classification, dependencies, scenarios,
  implementation components, evidence and blockers.
- `rules/mechanics.jsonl` and `mechanics/contracts/` describe keyword and action
  families that span multiple numbered rules.
- `coverage/rules-*.json` and their Markdown renderings are generated views.

The pinned source text remains authoritative. Derived records never replace it
or silently alter a rule's meaning.

## Status model

A rule record distinguishes:

- `unreviewed`: inventoried but not behaviorally assessed;
- `definition_only`: terminology or structure with no independent transition;
- `blocked`: required behavior or dependency is missing;
- `partial`: a bounded represented slice has evidence but the rule claim is not
  closed;
- `passing`: every declared in-scope behavior and dependency has executable
  evidence for the supported profiles.

Source linkage, parsing, a witness card and a happy-path test are not passing
behavior. A broad numbered rule remains blocked when an applicable dependency
or interaction is unresolved, even if one subsection works.

## Evidence requirements

Every behavioral claim declares the applicable evidence classes before it can
pass:

- positive behavior;
- negative or unavailable behavior;
- malformed-input rejection and rollback;
- multiplayer/APNAP behavior;
- exact command replay and save/load when state persists;
- privacy/projection when hidden choices or information participate;
- interaction and dependency fail-closed behavior;
- property/fuzz evidence for meaningful state spaces;
- a focused killed implementation mutation.

An omitted applicable class requires an explicit reviewed not-applicable
rationale. Evidence IDs must resolve to current tests and implementation
components. Surviving critical mutations or missing dependencies block trust.

## Review workflow

For each coherent rules family:

1. Read the pinned paragraphs and relevant official rulings.
2. Classify each record as behavioral, definition-only, structural, example or
   dependency text.
3. Identify one reusable typed owner and every represented producer.
4. Declare dependencies, supported profiles and required scenarios.
5. Implement advertisement, validation, replacement/choice participation and
   mutation through the same canonical path.
6. Add deterministic evidence against authoritative behavior.
7. Record exact test IDs, components and blockers.
8. Regenerate and promote only the claims whose complete declared evidence
   passes.

Do not select work one numbered rule at a time. Complete a reusable family that
has coherent ownership, then update every affected rule record honestly.

## Invalidation and replay

The rules, Oracle, rulings, compiler, capability, mechanic, semantic and
implementation fingerprints form one trust chain. A changed source or behavior
invalidates dependent evidence until regeneration and tests pass. Replay uses
the pinned identity stored with a game; an old record is never reinterpreted as
if it used the new rules implementation.

Run the focused checks with the project interpreter:

```powershell
.\.venv\Scripts\python.exe simctl.py rules verify
.\.venv\Scripts\python.exe simctl.py rules coverage
.\.venv\Scripts\python.exe simctl.py rules queue
.\.venv\Scripts\python.exe scripts\update_rules_scheduler.py --check
```

Use `scripts/quick_gate.py` to select the adjacent conformance, replay, privacy,
property and mutation checks for a change. Public exact-head CI remains the
normal certification authority.

## Claim boundary

The simulator is a partial, snapshot-scoped implementation of Magic and
Commander. Generated conformance status states exactly which records pass and
which dependencies remain. Never summarize the project as “complete rules
support,” and never blame a player or client for behavior that the engine did
not legally expose.
