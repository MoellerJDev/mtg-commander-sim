# Rules completeness implementation status

Last updated: 2026-07-30

This is the durable execution ledger for the snapshot-scoped rules
completeness program. It records implementation evidence without claiming
Arena parity, complete Comprehensive Rules enforcement, or complete Oracle
coverage.

## Pinned baseline

- Repository: private `MoellerJDev/mtg-commander-sim`
- Branch: `agent/rules-completeness`
- Stacked draft PR:
  `https://github.com/MoellerJDev/mtg-commander-sim/pull/1`
- Rules-program base: `d099fe4`
- Continuation start: `6517dc0`
- Package version: `0.8.0`
- Comprehensive Rules effective date: 2026-06-19
- CR SHA-256:
  `e99cd70eb64ca854acb6420ebbf06e369e3f258e0cfba4f03f70bd881386f79b`
- Oracle bulk snapshot: 2026-07-28, 38,373 Oracle IDs
- Rulings bulk snapshot: 2026-07-28, 77,999 rulings

## Program gates

| Workstream | Status | Current evidence |
|---|---|---|
| Versioned rules corpus | Implemented, not complete | 3,300 rules, 156 sections, 733 glossary entries, 425 mechanics |
| Mechanic contracts | In progress | 16 partial/untrusted contracts; 409 mechanics unclassified; 0 trusted |
| Typed Oracle IR | In progress | `oracle-ir-v2`, source spans, fail-closed material residuals |
| Object and zone identity | Partial | CR 400 logical incarnations, permanent-spell continuation, serialized zone timestamps, target revalidation, and selected linked-effect guards |
| Continuous-effect layers | Partial | CR 613 evaluator and engine integration for selected derived characteristics |
| Replacement/prevention ordering | Partial | CR 616 typed ordering primitive; event-producer integration incomplete |
| Damage, defense, and Battles | Partial | Type-driven CR 120/210/310 damage results, counter-derived battlefield defense, copied printed defense, Siege protector/combat routing, and exact-incarnation defeated-trigger exile/optional transformed cast |
| State-based actions | Partial | CR 704 snapshot evaluator, token/copy cessation, World rule, numeric maximum-counter restrictions, Battle defense/protector checks, and fixed-point engine integration for the reviewed subset |
| Full Oracle compilation | In progress | exact 2,957; partial 15,691; unresolved 19,725; 69,664 material residuals |
| Commander-legal Oracle compilation | In progress | exact 338; partial 14,354; unresolved 16,930; 61,212 material residuals |
| Official-source conformance/property/mutation gates | In progress | 3,300 source-pinned cases and per-rule inventory tests exist; all 24 CR 310 cases are reviewed, with 5 semantic passes, 13 blocked cases, and 6 definition-only cases |
| Complete-rules claim gate | Failing by design | `current_snapshot_complete=false`, 0 trusted mechanics |

## Completed rules-program checkpoints

- [x] Pinned official CR/Oracle/rulings corpus and deterministic indexes.
- [x] Added `rules sync`, `inventory`, `diff`, `coverage`, `next`, `verify`,
  and `report`.
- [x] Added versioned mechanic-contract validation and generated registry
  overlays.
- [x] Added typed, source-spanned Oracle IR with material residuals.
- [x] Added generic whole-text lowering for selected common effect, keyword,
  mana, trigger, entry, counter, token, and temporary-modifier families.
- [x] Added CR 613 continuous-effect ordering primitives.
- [x] Added CR 616 replacement/prevention ordering primitives.
- [x] Added a CR 704 permanent snapshot and deterministic action batch.
- [x] Added serialized CR 400 logical incarnations, target identity
  revalidation, selected linked-effect identity guards, and CR 111 token
  lifecycle integration.
- [x] Added serialized zone/World-since timestamp moments and the CR 704.5k
  World rule, including simultaneous-entry ties.
- [x] Added serialized spell/card-copy objects, CR 704.5e cessation, and
  same-object token conversion for permanent-spell copies.
- [x] Added CR 704.5r numeric maximum-counter extraction and snapshot
  enforcement, including overlap with opposing-counter removal.
- [x] Added partial CR 120/210/310 and CR 704.5v/w/x Battle behavior:
  copied/entry defense, typed damage results, exact-incarnation defeated
  triggers, replayable Siege protector and transformed-cast choices, and
  protector-aware combat.
- [x] Added a versioned conformance case and generated source-linkage test for
  all 3,300 pinned rule IDs, with separate semantic, failing, blocked,
  skipped, definition-only, unreviewed, and inventory-only reporting.
- [x] Added source-pinned family review overlays whose stale or deleted
  reviews cannot survive through the generated conformance artifact.
- [x] Reviewed all 24 CR 310 cases without promoting partial behavior:
  5 executable passes, 13 dependency-blocked cases, and 6 definition-only
  cases.

## Current CR 120/210/310/704 Battle slice

Battle behavior is derived from the effective card type, subtype, defense
characteristic, counters, controller, and protector. It contains no
printed-name branch. Off the battlefield, a Battle exposes its printed or
copied defense. On the battlefield, its effective defense is its current
defense-counter count. A Battle entering as itself or as a copy initializes
from printed entry characteristics rather than copying the source permanent's
current counters. Damage marks a creature, removes planeswalker loyalty, and
removes Battle defense for every applicable type on a multi-typed permanent.

For the pinned rules snapshot, a Siege chooses an opponent as protector while
the spell resolves. Every player other than the protector may attack it; only
the protector receives the corresponding blocker task. Missing or invalid
protectors are repaired through a replayable controller choice. A missing
protector waits while the Battle is attacked, while a Siege whose controller
is its protector is repaired even during that attack under CR 704.5x. A
Battle with no Battle type designates its controller. If no legal protector
exists, the Battle goes to its owner's graveyard. Protector designations
survive the permanent ceasing to be a Battle and becoming a copy of another
Battle. Removing the last defense counter queues the
intrinsic Siege trigger with the source's exact logical incarnation. A trigger
from an old incarnation does not prevent the zero-defense state action.

Native Siege trigger resolution exiles the exact source incarnation and gives
its controller a replayable choice to cast the transformed face without paying
its mana cost or decline. Tokens cease after exile, an object that left and
returned is not followed, and an ordinary cast cannot select a transforming
card's back face. A compiled target schema is projected for a transformed
instant or sorcery; unresolved mandatory target grammar stops for arbitration.
The two Control Point previews in the July 28 Oracle corpus are
not-yet-Commander-legal and postdate the June 19 CR snapshot, so their
protector rules fail closed.

## Prior CR 400/613/111/704/707 foundation

Every card retains a stable physical `object_id`, while a serialized
`zone_change_counter` identifies its current logical incarnation. The
canonical zone path advances the incarnation for ordinary cross-zone moves,
including draws and casts, and for same-zone exile/command moves. It clears
state that does not survive the move and preserves only explicitly implemented
entry continuations. A permanent spell keeps that incarnation when it becomes
a permanent under CR 400.7a. Targets compare their selected incarnation at
resolution. Daretti's delayed emblem return carries the recorded graveyard
incarnation, so the effect does not follow a card that leaves and reenters.
Neither physical IDs nor counters are projected to pilots.

Every new zone incarnation also receives an authoritative timestamp moment.
Objects moved simultaneously to one destination share that moment. A separate
World-since timestamp records when a battlefield object most recently gained
the World supertype; losing and regaining World allocates a new moment even
without a zone change. The CR 704.5k action keeps the unique newest World
permanent and moves all World permanents when the newest duration is tied.
Timestamp fields and the global allocator are serialized for exact replay and
omitted from pilot projections.

The engine now discovers the following permanent actions from one immutable
snapshot before applying mutations:

- tokens outside the battlefield cease to exist;
- creature toughness 0 or less;
- lethal marked damage and deathtouch destruction, with indestructible
  distinguished from non-destruction graveyard moves;
- planeswalker loyalty 0;
- unattached or illegally attached Auras for supported enchant predicates;
- illegal Equipment/Fortification attachment;
- attached creatures, battles, and nonattachment permanents becoming
  unattached;
- pairwise removal of +1/+1 and -1/-1 counters;
- counters above a permanent's reviewed numeric self-restriction;
- older World permanents, or all World permanents on a newest-duration tie.

Aura restrictions reuse the declarative target-domain evaluator without
incorrectly treating shroud or hexproof as attachment restrictions.
Protection from supported color qualities is rechecked. Animate Dead records
its changed enchant restriction as data instead of relying on a
printed-name-only state-action branch. The engine applies the batch, preserves
pre-move last-known information, and repeats to a fixed point.

Tokens reach their first nonbattlefield destination before the next state
check, so zone-change triggers observe the move. They cannot move again after
leaving the battlefield and cease without generating a second zone-change
event.

Spell and card copies now have serialized noncard object kinds. Spell copies
are spell targets on the stack; countered copies reach the instructed zone and
then cease under CR 704.5e. Card copies cease outside the stack or battlefield
and are never treated as card targets. A copied permanent spell becomes that
same object as a token permanent and does not generate a token-creation event.
The underlying object identity remains outside seat projections, and the
lifecycle command-replays exactly.

The CR 400, CR 111, CR 704, and CR 707 contracts remain partial and untrusted.
Outstanding blockers include:

- complete CR 707.2 copiable values and layer-1 interactions;
- casting or playing card copies, including complete cost and timing grammar;
- Prepare's exile exception and specialized copy/face-down/linked objects;
- copied-choice, target-retention, division, and cost-fact exceptions;
- the complete CR 400.7 exception matrix needs typed continuation policies;
- merged permanents, meld components, stickers, complete face-down identity,
  and migration of all legacy physical references;
- complete CR 613.7m APNAP relative timestamps and consumption of serialized
  timestamp moments by every continuous-effect source;
- maximum-counter wording outside the reviewed numeric self-restriction
  sentence family;
- Sagas, dungeons, space sculptor, Roles, and speed;
- complete exile-replacement ordering and transformed cast grammar outside
  compiled cost/target schemas, Battle type/control changes during combat,
  and future Battle-subtype protector predicates;
- Aura attachment to players and complete enchant-quality grammar;
- regeneration;
- one simultaneous replaceable event spanning every player loss and permanent
  action.

## Verification at this checkpoint

- 3,708 unit/integration tests pass: 408 ordinary tests plus 3,300 generated
  inventory/source-linkage tests. The latter are not semantic passes.
- Fifteen focused object/token tests cover monotonic incarnations, draws,
  timestamp moments, identity-sensitive targets and delayed links, private
  projection, token destination timing, move prevention, cessation, and exact
  replay.
- Eight focused copy-object tests cover serialized spell/card copies,
  counter/destination timing, card-versus-noncard targeting, same-object
  permanent resolution, projection privacy, and exact replay.
- Fifty focused CR 120/210/310/704 tests cover positive, negative,
  fixed-point, order-mutation, shared pre-action LKI,
  attachment/protection, counters, maximum-counter
  extraction/overlap/replay, sequential and simultaneous World behavior,
  printed-versus-battlefield defense, Battle-creature damage and combat
  restrictions,
  exact-incarnation triggers, protector choice/repair, projection, native
  transformed casting, decline/token/changed-object behavior, compiled and
  unresolved targets, contract pinning, and three command-replay paths.
- Exact Zimone closure: 27 tests pass.
- Exact Mishra closure: 23 tests pass.
- The seed-20260730 regression reaches its corrected main-phase opportunities,
  keeps `suppressed_meaningful_windows=0`, passes seat projection, and exact
  command replay.
- Rules corpus verification passes for all 3,300 indexed rules, 3,300
  conformance records, and 425 mechanics. The 3,300 generated per-rule tests
  establish inventory linkage only. All 24 CR 310 cases are source-reviewed:
  5 pass with executable engine evidence, 13 remain blocked, and 6 are
  definition-only. The other 3,276 cases remain unreviewed.

Repository demo, repository audit, wheel build, clean wheel installation, and
final push evidence are recorded in `OVERNIGHT_HANDOFF.md` after the complete
checkpoint validation.

## Next dependency-ordered work

1. Continue reviewing and promoting conformance cases by
   dependency-ordered rules family; keep exposed but unimplemented edge cases
   failing or blocked.
2. Complete the blocked CR 310 dependencies, beginning with 310.11b
   replacement ordering and cast grammar outside compiled
   cost/target schemas, then re-evaluate its blocked status.
3. Replace remaining physical-reference links with typed incarnation/LKI
   handles and implement the remaining CR 400.7 continuation policies.
4. Implement the remaining ordinary CR 704.5 specialized permanent/layout
   state actions.
5. Integrate state-action destruction/loss with typed replacement and
   regeneration events.
6. Continue CR 603 trigger ordering and state-action interaction coverage.
7. Continue migrating static characteristics to CR 613 and all replaceable
   event producers to CR 616.
8. Implement the remaining CR 707 copiable-value, card-copy casting, and
   specialized copy-object exceptions.
9. Recompute full and Commander-legal Oracle coverage after each generic
   compiler/mechanic slice.

No deck list has been modified, and no current game result is promoted to
matchup evidence.
