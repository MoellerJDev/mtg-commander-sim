# Comprehensive Rules conformance cases

The pinned June 19, 2026 Comprehensive Rules snapshot has one stable
conformance case record for each of its 3,300 numbered rules and subrules.
This is a work queue and audit boundary, not a claim that all 3,300 rules are
implemented.

## Artifacts

- `rules/conformance-cases.json` contains the source-pinned case records.
- `schemas/rule-conformance-case.schema.json` defines case version 1.
- `tests/test_rule_conformance_inventory.py` generates one source-linkage
  unittest for every record.
- `coverage/rules-conformance.json` and `.md` report semantic and
  nonsemantic statuses separately.

The tracked artifacts do not contain Comprehensive Rules prose. Each case
stores the rule ID, source span, raw-snapshot hash, and rule-text hash.

## Honest status model

A new or changed rule starts as:

```json
{
  "status": "unreviewed",
  "classification": "unclassified",
  "assertion_kind": "inventory_only",
  "reviewed": false,
  "blockers": ["semantic_review_not_completed"]
}
```

The generated per-rule test proves only that this record still points to the
correct rule in the pinned snapshot. It does not count as a semantic pass.

The report distinguishes:

- `passing`: reviewed executable engine semantics with linked tests and every
  declared scenario covered;
- `failing`: reviewed executable semantics whose expected behavior is not
  satisfied;
- `blocked`: reviewed work whose dependencies or representation are missing;
- `skipped`: deliberately deferred work with a recorded reason;
- `definition_only`: reviewed nonbehavioral text with static traceability;
- `unreviewed`: inventory exists, but semantic analysis has not happened.

`inventory_only_cases` is always reported separately from
`semantic_passing_cases`. Repository verification rejects a passing case
without implementation components, executable test IDs, required scenarios,
or complete scenario coverage.

## Regeneration and invalidation

`rules sync` regenerates the complete case set from `rule-index.json`.
Reviewed fields survive only when both the pinned CR source hash and that
rule's text hash are unchanged. Changed, added, or renumbered rules return to
the unreviewed inventory state. Missing, duplicate, stale, or source-mismatched
cases fail `rules verify`.

```bash
python simctl.py rules sync --root .
python simctl.py rules conformance --root .
python simctl.py rules next --root . --limit 20
python simctl.py rules verify --root .
```

`rules next` prioritizes failing, blocked, unreviewed, and skipped conformance
cases. It does not treat a source-linkage test as an implementation test.

## Review workflow

For each rule:

1. Read the pinned source at the recorded source span.
2. Classify it as behavioral, definition-only, structural, example, or
   dependency text.
3. Identify generic implementation components and dependency rules.
4. Declare the relevant positive, negative, interaction, multiplayer, replay,
   and hidden-information scenarios.
5. Add deterministic tests against authoritative engine behavior.
6. Record exact test IDs and implementation components.
7. Mark the case passing only after every declared scenario passes.

Rules that expose missing behavior should remain failing or blocked until the
generic engine gains that behavior. Tests and implementation should target
rules concepts, not the names of decks or cards that happened to reveal them.

## Current checkpoint

All 3,300 cases exist and all 3,300 inventory/source-linkage tests pass. All
3,300 cases remain unreviewed and inventory-only, so the executable semantic
pass count is 0 and snapshot completeness remains false. Subsequent work
promotes cases family by family while preserving this denominator.
