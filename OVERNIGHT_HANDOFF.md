# Overnight handoff

Last updated: 2026-07-30

## Repository

- Authenticated GitHub owner: `MoellerJDev`
- Repository: `mtg-commander-sim`
- Visibility: private
- Remote: `https://github.com/MoellerJDev/mtg-commander-sim.git`
- Default branch: `main`
- Review-MVP branch: `agent/review-mvp`
- Rules branch: `agent/rules-completeness`
- Stacked draft PR:
  `https://github.com/MoellerJDev/mtg-commander-sim/pull/1`
- Rules-program base: `d099fe4`
- This continuation started at:
  `6517dc0870ee9344ea6a2be89bf3b2ea36b61d37`
- Ending checkpoint: the branch `HEAD` containing this handoff
- Package version: `0.8.0`

The ending hash is intentionally referenced as the containing `HEAD`; embedding
that commit's own hash would change the commit. The final task report and
remote branch identify the exact immutable hash.

## Current rules checkpoint

The checkpoint adds versioned partial CR 120/210/310/704 contracts and generic
Battle defense/protector behavior on top of the existing
logical-incarnation, timestamp, World-rule, token/copy-lifecycle, and
maximum-counter foundation. It now:

- serializes a monotonically increasing logical incarnation beside stable
  physical card identity;
- routes ordinary zone changes, draws, and casts through that boundary;
- treats same-zone exile and command moves as new objects;
- revalidates targets against the selected incarnation;
- identity-guards implemented linked delayed moves, including the Daretti
  ruling witness;
- clears stale counters/annotations while preserving explicit entry
  continuations;
- lets a token reach its first destination, prevents another move, and causes
  it to cease in the next shared CR 704 snapshot;
- allocates a serialized timestamp moment for each new zone incarnation;
- assigns one shared moment to objects moved simultaneously to a destination;
- separately records when a battlefield object most recently gained World;
- enforces CR 704.5k by keeping the unique newest World permanent or moving
  every World permanent when the newest duration is tied;
- preserves a permanent spell's logical incarnation under CR 400.7a;
- represents spell copies and card copies as serialized noncard objects;
- enforces CR 704.5e when those copies enter invalid zones;
- converts a resolving copied permanent spell into the same token object,
  without emitting a token-creation event;
- derives reviewed numeric maximum-counter abilities from effective Oracle
  text and enforces them in the shared CR 704 snapshot;
- derives Battle and planeswalker printed defense/loyalty through the
  continuous-characteristic path;
- reports a battlefield Battle's effective defense from its current defense
  counters while retaining printed defense off the battlefield and for its
  intrinsic entry replacement;
- initializes defense and loyalty counters on battlefield entry, including
  copied Battle defense rather than copied current counters;
- applies typed permanent damage results: marked creature damage, removed
  planeswalker loyalty, and removed Battle defense;
- chooses a Siege protector during resolution rather than during casting;
- exposes only the public protector seat in pilot projections;
- permits every player other than the protector to attack a Battle and routes
  blocker decisions to the protector;
- prohibits Battle creatures from being declared as attackers or blockers;
- repairs invalid Siege protectors through replayable controller choices;
- preserves a Battle's single protector through type and copy changes,
  handles the distinct attacked-Battle repair branches, and moves a Battle
  with no legal protector to its owner's graveyard;
- queues the intrinsic Siege trigger on last-defense removal and matches
  pending source triggers to the represented logical incarnation;
- exiles that exact Siege incarnation and offers a replayable optional cast of
  its transformed face without paying its mana cost;
- exposes compiled target schemas for transformed spells and stops for
  arbitration when mandatory target grammar is unresolved;
- omits physical/incarnation identifiers from seat projections;
- omits authoritative zone/World timestamps from seat projections;
- preserves exact command replay with the new authoritative fields.
- generates one source-pinned conformance record and inventory-linkage test
  for every one of the 3,300 numbered rules;
- invalidates reviewed conformance metadata when the pinned source or
  individual rule-text hash changes;
- uses source-pinned family review overlays as the authoritative semantic
  review source, so stale or deleted reviews cannot persist through the
  generated case file;
- source-reviews both CR 210 Defense cases and fails closed for absent,
  malformed, or negative represented printed defense;
- source-reviews all 26 CR 120 Damage cases, rejects negative damage, clamps
  negative combat power to zero damage, and suppresses zero before any damage
  result or commander attribution;
- preserves marked damage through loss of creature type until cleanup and
  leaves destruction or graveyard movement to the subsequent state-action
  pass;
- source-reviews all 10 CR 616 ordering rules and verifies the five priority
  classes, arbitrary choice within the current class, one-application
  journaling, deterministic replay, applicability rechecks, and newly
  applicable effects;
- rejects unsupported nested replaceable events instead of flattening child
  choices into the containing event;
- source-reviews all 16 CR 615 Prevention Effects rules, rejects negative
  prevention amounts, and preserves unpreventable damage while still applying
  and journaling the prevention effect once;
- verifies modified damage events and independent per-event static
  prevention, while keeping stateful shields, simultaneous source allocation,
  source selection/rechecks, and prevention triggers blocked;
- source-reviews all 38 CR 614 Replacement Effects rules, expands the
  contract to every family record, and verifies one application per event,
  zero-damage event absence, and self-replacement priority;
- rejects unsupported skip, regeneration, redirection, and prohibition
  operations instead of approximating them;
- keeps inventory-only cases separate from executable semantic passes.

The prior permanent snapshot behavior remains: toughness, lethal/deathtouch,
loyalty, supported attachment legality, and opposing counter pairs are
detected from one immutable snapshot. `CommanderEngine` applies the combined
batch and repeats before priority.

This is not complete CR 120/210/310/400/111/615/616/704/707 support. Complete
replacement ordering for the defeated-Siege exile, transformed cast grammar
outside compiled target/cost schemas, nonspell Battle entry choices, Battle
type/control changes during combat, complete damage replacement/prevention,
and future Battle subtype predicates remain blocked. Complete
copiable values, card-copy casting and playing, Prepare's exile exception,
face-down and linked copy interactions, and copied choice/cost/target
exceptions also remain blocked.
The complete CR 400.7 exception matrix, merged/melded identity, stickers, all
legacy linked references, complete CR 613.7m APNAP relative timestamps,
consumption of serialized timestamps by every continuous-effect source,
maximum-counter wording outside the reviewed self-restriction family, Sagas,
dungeons, space sculptor, Roles, speed, player-attached Auras, full
enchant qualities, regeneration, and simultaneous replaceable loss/action
events also remain blockers.

## Pinned coverage

- CR effective date: 2026-06-19
- CR SHA-256:
  `e99cd70eb64ca854acb6420ebbf06e369e3f258e0cfba4f03f70bd881386f79b`
- Indexed rules: 3,300
- Conformance cases: 3,300
- Inventory-only cases: 3,184
- Reviewed blocked cases: 75
- Reviewed definition-only cases: 18
- Executable semantic passes: 23
- Indexed sections: 156
- Glossary entries: 733
- Discovered mechanics: 425
- Partial/untrusted mechanic contracts: 17
- Unclassified mechanics: 408
- Trusted mechanics in the new corpus registry: 0
- `current_snapshot_complete`: false
- Full Oracle snapshot: 2,957 exact; 15,691 partial; 19,725 unresolved;
  69,664 material residuals
- Commander-legal snapshot: 338 exact; 14,354 partial; 16,930 unresolved;
  61,212 material residuals

## Validation

- Compilation: pass
- Rebuilt compact CI database: 181 cards, 185 aliases, 443 rulings
- Unit/integration tests: 3,735 passed
- Noninventory unit/integration tests: 435 passed
- Generated per-rule inventory/source-linkage tests: 3,300 passed
- Focused object identity/token lifecycle tests: 15 passed
- Focused copy-object lifecycle tests: 8 passed
- Focused CR 120/210/310/704 tests: 60 passed
- Focused CR 616 replacement-ordering tests: 13 passed
- Focused CR 615 prevention-effect tests: 7 passed
- Focused CR 614 trace/fail-closed tests: 2 passed
- Seed-20260730 corrected decision/opportunity test: pass
- Seed-20260730 exact replay: pass
- Seed-20260730 hidden-information audit: pass
- `suppressed_meaningful_windows`: 0 in the regression
- Exact Zimone and Dina preflight: 100 fully playable, 0 partial, 0
  unresolved, trusted-only ready, 0 expected arbiter calls
- Exact Mishra, Eminent One preflight: 100 fully playable, 0 partial, 0
  unresolved, trusted-only ready, 0 expected arbiter calls
- Four-player protocol demo: pass
- Protocol packet benchmark: 1,549 bootstrap / 269 repeated / 108
  declaration estimated tokens
- Repository/history/secret/artifact validation: pass
- JSON schemas checked: 14
- Pinned rules verification: 3,300 rules, 3,300 conformance cases, and 425
  mechanics pass
- Wheel clean installation/import/CLI smoke: pass
- Wheel:
  `mtg_commander_sim-0.8.0-py3-none-any.whl`
- Wheel SHA-256:
  `3bdcb6a4b46daaeeafe9b9c4460b0be9bdaf11b74868243bf0eec4804cf6ea2f`

## Deck-review evidence state

- Qualifying full games: 0
- `deck_operation_evidence`: 0
- `matchup_evidence`: 0
- Duplicated-pod fixtures remain ineligible for matchup evidence.
- No deck list was modified.

The existing exact-list preflight is semantic closure for the two pinned lists,
not broad Oracle completeness and not game/deck-quality evidence.

## GitHub state

- Authentication: active as `MoellerJDev`; no credential value was recorded.
- Open pull requests at handoff preparation: stacked draft PR #1.
- Draft rules-completeness PR:
  `https://github.com/MoellerJDev/mtg-commander-sim/pull/1`
- Exact-SHA CI evidence is reported from the remote checks after push; this
  document avoids embedding the hash of the commit that contains it. All
  required local gates above pass.

## Known limitations and next step

There is no external blocker. The rule-by-rule conformance program has moved
from scaffold to its first complete family review:

1. all 3,300 pinned rules have a versioned stable case and generated
   inventory/source-linkage test;
2. source-pinned family overlays are authoritative and fail closed when their
   source or rule-text hashes change;
3. all CR 120/210/310/614/615/616 cases are reviewed: 23 narrow rules pass
   with executable evidence, 75 expose recorded dependency gaps, and 18 are
   definition-only;
4. CR 310.11b remains blocked after adding its native replayable Siege
   continuation because replacement ordering and broader cast grammar are
   incomplete;
5. continue reviewing and promoting cases by dependency-ordered rules family;
6. migrate remaining physical-reference links to typed incarnation/LKI
   handles and finish CR 400.7 continuation policies;
7. integrate destruction/loss with typed replacement and regeneration;
8. add the remaining specialized CR 704.5 permanent/layout actions and
   interaction tests;
9. integrate serialized object timestamps into every continuous-effect source
   and implement CR 613.7m APNAP relative ordering;
10. implement complete copiable-value, card-copy casting, Prepare, and
   specialized copy interactions behind the CR 707 contract;
11. rerun full coverage and every validation gate.

The review-MVP branch still separately lacks three consecutive qualifying
persistent-Codex games, review-batch aggregation, and per-deck operation
reports. Those requirements remain active and must not be inferred from this
rules checkpoint.
