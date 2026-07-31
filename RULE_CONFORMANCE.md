# Comprehensive Rules conformance cases

The pinned June 19, 2026 Comprehensive Rules snapshot has one stable
conformance case record for each of its 3,300 numbered rules and subrules.
This is a work queue and audit boundary, not a claim that all 3,300 rules are
implemented.

## Artifacts

- `rules/conformance-cases.json` contains the source-pinned case records.
- `rules/conformance-reviews/*.json` contains the maintainable, family-scoped
  semantic-review overlays.
- `schemas/rule-conformance-case.schema.json` defines case version 1.
- `schemas/rule-conformance-review.schema.json` defines review-overlay
  version 1.
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
When `rules/conformance-reviews/` exists, those overlays are the authoritative
source of every reviewed field; the generated case file is never used as a
fallback. Each overlay pins the effective date, complete source hash, and
individual rule-text hash. Deleting an overlay therefore returns its cases to
the unreviewed inventory state. A stale, duplicate, malformed, or
source-mismatched overlay fails `rules sync` and `rules verify`, and its
reviews are not applied.

Repositories without an overlay directory retain the compatibility behavior:
reviewed fields survive regeneration only when both the complete source hash
and the individual rule-text hash are unchanged. Changed, added, or
renumbered rules always return to the unreviewed inventory state.

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

All 3,300 cases exist and all 3,300 inventory/source-linkage tests pass.
All 278 cases in CR 120, CR 210, CR 310, CR 602, CR 603, CR 604, CR 605,
CR 606, CR 607, CR 608, CR 609, CR 614, CR 615, and CR 616 are
source-reviewed: 39 narrow behavioral rules pass with generic executable
evidence, 196 are blocked with exact missing dependencies, and 43 are
definition-only with contract traceability. The remaining 3,022 cases are
unreviewed and
inventory-only.

The passing CR 310 rules are battlefield defense (310.4c), Battle damage
(310.6), the zero-defense state action (310.7), single-protector replacement
(310.8f), and protector persistence through type/copy changes (310.8g).
Broader Battle casting, entry replacement ordering, arbitrary
defending-player Oracle bindings, attachment interactions, nonspell entry,
future Battle types, and the complete defeated-Siege transformed cast remain
blocked. CR 210.1 additionally records that represented printed defense and
fail-closed validation are tested, but it cannot pass while complete intrinsic
entry-replacement ordering and face/copy interactions remain incomplete.
CR 120 adds passing evidence for damageable permanent types, planeswalker and
Battle results, state-action timing, and zero-damage suppression. Infect,
wither, lifelink, toxic, the full four-part replacement/prevention pipeline,
excess damage, regeneration, source selection, damage-trigger correlation,
and advanced combat remain explicitly blocked.
CR 616 adds passing evidence for self-replacement, enters-control,
enters-copy, enters-back-face, ordinary-choice, repeat/recheck, and
newly-applicable-effect ordering. Simultaneous affected-player or
affected-object choices still lack engine-wide APNAP collection, and nested
replaceable events fail closed until a typed event tree and replay path exist.
CR 615 adds passing evidence for modified damage events, per-event static
prevention, and applying a prevention effect exactly once to unpreventable
damage. Negative prevention fails closed. Stateful shields, simultaneous
source allocation, source selection and rechecks, and prevention-trigger
dispatch remain explicitly blocked.
CR 614 adds passing evidence for one application per event, zero-damage event
absence, and self-replacement priority. Draw, entry, and Dauthi graveyard
replacements provide partial dedicated evidence, while skip, regeneration,
redirection, prohibition, nested entry events, and broad linked replacements
remain blocked and fail closed where invoked generically.
CR 609 and CR 608 pin the effect and resolution taxonomies, with narrow
top-of-stack, ordinary permanent, and permanent-spell-copy behavior passing
while incomplete targets, choices, LKI, APNAP, `as though`, Aura, mutate, and
resolution-trigger dependencies remain blocked.
CR 607 pins every linked-ability family without promoting exact-incarnation or
chosen-name witnesses to generic pair, set, fact, copied, or cross-object
support.
CR 606 adds passing loyalty-symbol identification and base activation timing
for any permanent. Modified, combined, and modified-payability loyalty costs
remain blocked and fail closed.
CR 605 adds passing stackless activated-mana resolution and spell
classification. Target/loyalty exclusions are corrected, while complete
possible-output recognition, arbitrary payment windows, activation reentry,
and generic triggered mana abilities remain blocked.
CR 604 records partial source-lifetime, moved-attachment, stack-static, and
zone-permission witnesses. Generic characteristic-defining abilities, static
Oracle compilation, broad attachment modifiers, and universal
current-information rather than LKI queries remain blocked.
CR 603 adds passing engine-level invariants for pending trigger placement
before priority, source-controller capture at trigger time, intervening
conditions checked at trigger and resolution, and exact-incarnation delayed
effects. Complete trigger syntax and event coverage, trigger-on-trigger APNAP
ordering, modes and choices, zone-change finding, delayed provenance, state
and player-loss triggers, the full look-back list, linked middle-sentence
triggers, and reflexive triggers remain blocked.
CR 602 adds passing activated-only classification, creature tap/untap
summoning-sickness and haste behavior, object-scoped once-per-turn history
that survives control changes, and sorcery/instant activation timing. Complete
cost and instruction grammar, transactional illegal-action rollback, CR
601.2b-i parity, hidden-zone reveal behavior, opponent-made choices,
prospective cost-altering effects, universal prohibitions, and acquired-
ability provenance remain blocked.
Snapshot completeness remains false.
