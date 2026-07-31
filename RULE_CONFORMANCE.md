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
All 452 cases in CR 120, CR 210, CR 310, CR 502, CR 503, CR 504, CR 505, CR 506, CR 507,
CR 508, CR 509, CR 510, CR 511, CR 512, CR 513, CR 514, CR 600, CR 601,
CR 602, CR 603, CR 604, CR 605, CR 606, CR 607, CR 608, CR 609, CR 614,
CR 615, and CR 616 are source-reviewed: 67 narrow behavioral or structural
rules pass with generic executable evidence, 322 are blocked with exact missing
dependencies, and 63 are definition-only with contract traceability. The
remaining 2,848
cases are
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
CR 601 adds a passing executable invariant for activating mana abilities
after the total cost option is determined and before payment. Submitted cast
failures transactionally restore mana, sources, zones, stack, and capability,
and represented cast triggers are queued above the spell before priority.
Those are partial witnesses only: the implementation still moves the card to
the stack after choices and costs, and complete modes, targets, division,
cost ordering, proposal-dependent permissions, alternative characteristics,
frozen proposals, and opponent-made choices remain blocked.
CR 600 contains only the General section heading. It is source-reviewed as a
definition-only taxonomy record linked to the dependent CR 601-609 contracts;
it makes no independent engine-behavior claim.
CR 502 records ordinary simultaneous, stackless active-player untaps,
represented stun and one-shot non-untap handling, and exact replay of a held
untap trigger into upkeep. A permanent with phasing and an active global
maximum-untap restriction now pause before any untap mutation instead of
silently producing the wrong state. All behavioral CR 502 records remain
blocked: direct/indirect phasing, day/night, shared-team turns, arbitrary
selection, universal replacement ordering, and complete trigger production
are not implemented.
CR 503.1 passes for the represented upkeep boundary: the step performs no
turn-based action, represented abilities triggered during untap and at the
beginning of upkeep share one APNAP/controller-order batch, state-based actions
precede trigger placement, and the active player receives priority afterward.
The ordinary boundary and ordering path replay exactly. CR 503.1a remains
blocked for the complete CR 502 event surface and CR 603.3b two-part process;
CR 503.2 remains blocked for additional-upkeep scheduling and after-first-
upkeep casting grammar.
CR 505.2, 505.6, 505.6a, and 505.6b pass for the represented ordinary
main-phase boundary: an empty-stack all-player pass advances the phase, a
nonempty stack resolves without ending it, the active player receives
priority, ordinary sorcery-speed spells require a true main phase and empty
stack, and land plays are stackless authoritative actions that consume one
allowance. The internal `main` marker is one phase-boundary sentinel, not a
rules substep. Skipped/additional combat and main phases, main-phase ordinal
identity, Archenemy schemes, Attractions, and complete simultaneous Saga
counter/replacement/trigger ordering remain blocked.
CR 504.1 and CR 504.2 pass for the represented draw-step boundary: the active
player's normal draw or trusted replacement completes without using the stack,
state-based actions are checked, and waiting semantic and delayed triggers are
combined into one APNAP/order batch before priority. Empty-library loss,
multiplayer and duel first-turn modifiers, hidden draw identity, and exact
 replay have direct evidence. The complete draw-replacement, prevention, and
continuous-effect interaction corpus remains outside this partial contract.
CR 506.4b passes for the represented combat-state invariant that tapping or
untapping an attacking or blocking creature does not remove it from combat.
The engine also removes represented combatants after zone, control, phasing,
creature-type, Battle-type, or attacking-controller invalidation and preserves
the historical “had an attacker” predicate needed by CR 508.8. Those are
partial witnesses only. Alternate multiplayer options, generic effects that
create or remove combatants, planeswalker destinations, restriction snapshots,
“alone” provenance, extra combats, and the complete combat-relative timing
grammar remain blocked.
CR 507.2 passes for the supported beginning-of-combat boundary: represented
permanent and delayed triggers coexist before the active player receives
priority, and a four-player priority round advances to declare attackers with
exact command replay. CR 507.1 remains blocked because Commander multiplayer
uses the attack-multiple-players option while single-defender variants are not
implemented; those unsupported profiles fail closed at game creation.
CR 510.1a, 510.1c, and 510.1e pass for exact effective-power totals,
multi-blocker recipient constraints, strict nested assignment fields, and
atomic illegal-assignment rollback with exact replay. The parent assignment
sequence, complete unblocked/Battle/planeswalker matrix, multi-attacker
blocking, simultaneous replacement/prevention batch, post-damage trigger
ordering, first/double strike, trample, and lifelink remain blocked.
CR 508.1a, 508.1f, 508.1k, 508.2, and 508.8 pass for the represented
ordinary declaration boundary: only eligible attackers are offered and
revalidated, ordinary attackers tap while vigilance is preserved, attacking
state lasts through combat, the active player receives priority, and an empty
combat skips blocker and damage steps. Opponent and Battle targets have
partial multiplayer evidence. Planeswalkers, restrictions, requirements,
banding, attack costs, generic attack triggers, entry-attacking effects,
defending-player LKI, and target reselection remain blocked.
CR 509.1a, 509.1g, and 509.2 pass for ordinary eligible-blocker derivation,
defending-player routing, blocking-state lifetime, multiplayer declaration
order, atomic rollback, exact replay, and the no-trigger priority handoff.
Requirements, the full restriction grammar, costs and their mana window,
declaration triggers, multi-attacker blocking, blocked-status effects, and
entry-blocking remain blocked.
CR 511.1 and CR 511.3 pass for the represented boundary: no turn-based action
precedes active-player priority, combat state remains live during that window,
and all objects leave combat before postcombat main. CR 511.2 remains blocked
because arbitrary effects lasting until end of combat lack a generic duration
registry, even though represented permanent and delayed triggers coexist.
CR 512.1 passes as a structural rule: the authoritative turn table contains
exactly the end step followed by cleanup, ordinary passage reaches the next
turn only after cleanup, and a cleanup discard decision prevents premature
advancement. Exact command replay covers the ordinary path. This does not
promote the broader partial CR 513 or CR 514 behavior.
CR 513 adds passing evidence that the end step performs no turn-based action,
collects represented permanent and delayed boundary triggers before active-
player priority, does not back up for a permanent or delayed trigger created
later in the step, and leaves turn-duration effects active until cleanup.
Ordinary command passage through the step replays exactly. Historical printed
`at end of turn` wording is definition-only because the engine consumes current
Oracle text.
CR 514 adds passing evidence for exact private discard to maximum hand size and
for the ordinary rule that cleanup grants no priority. Represented state
actions and delayed cleanup triggers now stabilize before exceptional priority,
and passing through that empty-stack window starts another cleanup step.
Universal simultaneous turn-duration expiration and complete replacement,
state-action, trigger, APNAP, multiplayer, hidden-information, and replay
interactions remain blocked.
CR 602 adds passing activated-only classification, creature tap/untap
summoning-sickness and haste behavior, object-scoped once-per-turn history
that survives control changes, and sorcery/instant activation timing. Complete
cost and instruction grammar, transactional illegal-action rollback, CR
601.2b-i parity, hidden-zone reveal behavior, opponent-made choices,
prospective cost-altering effects, universal prohibitions, and acquired-
ability provenance remain blocked.
Snapshot completeness remains false.
