# Rules completeness implementation status

Last updated: 2026-07-31

This is the durable execution ledger for the snapshot-scoped rules
completeness program. It records implementation evidence without claiming
Arena parity, complete Comprehensive Rules enforcement, or complete Oracle
coverage.

## Pinned baseline

- Repository: private `MoellerJDev/mtg-commander-sim`
- Branch: `agent/rules-completeness`
- Rules integration PR:
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
| Mechanic contracts | In progress | 35 partial/untrusted contracts; 390 mechanics unclassified; 0 trusted |
| Typed Oracle IR | In progress | `oracle-ir-v2`, source spans, fail-closed material residuals |
| Object and zone identity | Partial | CR 400 logical incarnations, permanent-spell continuation, serialized zone timestamps, target revalidation, and selected linked-effect guards |
| Continuous-effect layers | Partial | CR 613 evaluator and engine integration for selected derived characteristics |
| Replacement/prevention ordering | Partial | CR 615/616 typed primitives; stateful shields and event-producer integration incomplete |
| Damage, defense, and Battles | Partial | Type-driven CR 120/210/310 damage results, counter-derived battlefield defense, copied printed defense, Siege protector/combat routing, and exact-incarnation defeated-trigger exile/optional transformed cast |
| State-based actions | Partial | CR 704 snapshot evaluator, token/copy cessation, World rule, numeric maximum-counter restrictions, Battle defense/protector checks, and fixed-point engine integration for the reviewed subset |
| Full Oracle compilation | In progress | exact 2,957; partial 15,691; unresolved 19,725; 69,664 material residuals |
| Commander-legal Oracle compilation | In progress | exact 338; partial 14,354; unresolved 16,930; 61,212 material residuals |
| Official-source conformance/property/mutation gates | In progress | 3,300 source-pinned cases and per-rule inventory tests exist; 428 cases in CR 120/210/310/506/507/508/509/510/511/512/513/514/600/601/602/603/604/605/606/607/608/609/614/615/616 are reviewed, with 60 semantic passes, 309 blocked cases, and 59 definition-only cases |
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
- [x] Reviewed both CR 210 Defense cases, including fail-closed tests for
  absent, malformed, and negative printed defense; 210.1 remains blocked on
  replacement ordering and broader face/copy interactions.
- [x] Reviewed all 26 CR 120 Damage cases, fixed zero/negative damage
  boundaries, and recorded the unresolved source-keyword, replacement,
  prevention, excess, trigger, regeneration, and advanced-combat families.
- [x] Reviewed all 10 CR 616 replacement/prevention ordering cases:
  7 primitive-level behaviors pass, 2 remain dependency-blocked, and the
  section heading is definition-only. Nested events fail closed rather than
  being flattened into an incorrect choice.
- [x] Reviewed all 16 CR 615 Prevention Effects cases: modified events,
  per-event static prevention, and one application to unpreventable damage
  pass; 11 stateful/integrated behaviors remain blocked, and 2 records are
  definition-only. Negative prevention fails closed.
- [x] Reviewed all 38 CR 614 Replacement Effects cases: one application per
  event, zero-damage event absence, and self-replacement priority pass; 29
  integrated families remain blocked, and 6 records are definition-only.
  Unsupported skip, regeneration, redirection, and prohibition operations
  fail closed.
- [x] Reviewed all 13 CR 609 Effects cases: 9 broad behaviors remain
  dependency-blocked and 4 framework records are definition-only. Supplied
  damage-source properties are rechecked without consuming a mismatching
  immutable shield, and unknown replacement-condition predicates fail closed.
  No generic `as though`, zone-scope, tie, impossible-instruction, source
  selection, or authoritative source-property claim is made.
- [x] Reviewed all 25 CR 608 Resolving Spells and Abilities cases: the top
  stack object after successive passes, ordinary untargeted permanent
  resolution, and same-object permanent-spell-copy token conversion pass.
  Nineteen target, choice, APNAP, LKI, look-back, Aura, mutate,
  cannot-enter, and resolution-trigger behaviors remain dependency-blocked;
  3 framework records are definition-only. Partial witnesses are not promoted
  to broad support.
- [x] Reviewed all 26 CR 607 Linked Abilities cases: all 24 behavioral
  records remain dependency-blocked and 2 taxonomy records are
  definition-only. Exact-incarnation linked moves, chosen-name behavior, and
  an undefined Pithing Needle choice provide partial witnesses only. Generic
  pair IDs, linked sets/facts, cross-object links, and copied or jointly
  acquired link provenance are absent.
- [x] Reviewed all 7 CR 606 Loyalty Abilities cases: loyalty-symbol
  identification and the controller/main-phase/empty-stack/once-per-permanent
  activation rule pass; the heading and taxonomy record are definition-only.
  Base positive and negative costs work, but the 3 cost-modification,
  combined-cost, and modified-payability records remain blocked. Recognized
  modifiers and multiple loyalty-symbol costs fail closed.
- [x] Reviewed all 14 CR 605 Mana Abilities cases: immediate stackless
  activated-mana resolution and the rule that a mana-producing spell remains
  a spell pass; 7 classifier, payment-window, reentry, and triggered-mana
  behaviors remain blocked, and 5 framework records are definition-only.
  Targeted and loyalty abilities are no longer misclassified as mana
  abilities.
- [x] Reviewed all 9 CR 604 Handling Static Abilities cases: 7 behavioral
  records remain dependency-blocked and 2 taxonomy records are
  definition-only. Padeem source-lifetime, moved Lightning Greaves, stack
  uncounterability, and Gravecrawler zone permission are partial witnesses
  only; no generic CDA or static-effect compiler is claimed.
- [x] Reviewed all 48 CR 603 Handling Triggered Abilities cases: represented
  trigger placement before priority, source-controller capture,
  intervening-condition rechecks, and delayed exact-incarnation behavior
  pass. Forty grammar, event, ordering, choice, zone-change, provenance,
  state/player-loss, look-back, linked, and reflexive behaviors remain
  dependency-blocked; 4 taxonomy records are definition-only.
- [x] Reviewed all 28 CR 601 Casting Spells cases: the mana-ability payment
  window passes with explicit and automatic plan witnesses. Twenty-four
  announcement-order, mode/target/division, total-cost, payment-order,
  permission, alternative-characteristic, frozen-proposal, opponent-choice,
  and cost-effect records remain dependency-blocked; 3 taxonomy records are
  definition-only. Submitted failures restore every partial mutation, and
  manual mana plans now record their real source rather than `null`.
- [x] Reviewed the sole CR 600 General record as definition-only taxonomy,
  pinned it to the CR 601-609 dependency contracts, and added an executable
  traceability test without inventing behavior for a section heading.
- [x] Reviewed all 4 CR 513 End Step records: the ordinary no-turn-action
  priority transition and the no-backing-up rule pass. Permanent and delayed
  trigger families are both collected before priority, late sources and
  delayed triggers wait for the next end step in multiplayer, turn-duration
  effects continue to cleanup, and the command path replays exactly. The
  heading and historical Oracle-errata record are definition-only.
- [x] Reviewed all 5 CR 514 Cleanup Step records: private exact-count
  simultaneous discard and ordinary no-priority cleanup pass. Represented
  state-action/trigger exceptions now grant priority and start another cleanup
  after the empty-stack pass cycle. Universal simultaneous duration expiration
  and complete state-action, replacement, trigger, APNAP, hidden-information,
  multiplayer, and replay interactions remain blocked; the heading is
  definition-only.
- [x] Reviewed all 20 CR 602 Activating Activated Abilities cases:
  activated-only classification, tap/untap summoning sickness,
  object-scoped once-per-turn restrictions, and sorcery/instant timing pass.
  Twelve cost, activation-transaction, hidden reveal, CR 601 parity,
  opponent-choice, cost-altering, prohibition, and acquired-ability records
  remain dependency-blocked; 3 taxonomy records are definition-only.
- [x] Reviewed all 11 CR 510 Combat Damage Step records. Exact effective-power
  totals, legal multi-blocker recipients, strict assignment fields, atomic
  rejection, and exact replay pass for the represented ordinary assignment
  boundary. The parent sequence, complete unblocked nonplayer recipient
  matrix, multi-attacker blocker assignment, simultaneous replacement and
  prevention batching, post-damage APNAP triggers, first/double strike,
  trample, and lifelink remain dependency-blocked.
- [x] Reviewed all 29 CR 506 Combat Phase records. Tapping and untapping
  preserve represented attacking and blocking relationships. Zone, control,
  phasing, creature-type, Battle-type, and attacking-controller invalidation
  remove represented combatants while retaining the historical attacker
  predicate required by CR 508.8. Alternate multiplayer options, generic
  effect-created or effect-removed combatants, planeswalker destinations,
  complete restrictions and requirements, “alone” provenance, extra combats,
  and combat-relative timing grammar remain dependency-blocked.
- [x] Reviewed all 3 CR 507 Beginning of Combat Step records. Supported
  Commander profiles establish all active opponents as defending players
  without a defender-choice action, permanent and delayed boundary triggers
  coexist before active-player priority, and exact replay reaches declare
  attackers. Single-defender multiplayer variants remain fail-closed and
  dependency-blocked.
- [x] Reviewed all 39 CR 508 Declare Attackers Step records. Ordinary
  eligibility, current target validation, tapping/vigilance, attacking-state
  lifetime, active-player priority, atomic rejection, exact replay, and
  empty-combat step skipping pass for the represented boundary. Planeswalkers,
  restrictions, requirements, banding, attack costs, declaration triggers,
  entry-attacking effects, defending-player LKI, and target reselection remain
  dependency-blocked.
- [x] Reviewed all 24 CR 509 Declare Blockers Step records. Ordinary
  eligible-blocker derivation, declaration state, lifetime, priority handoff,
  atomic rejection, multiplayer sequencing, and exact replay pass for the
  represented boundary. Requirements, complete restrictions, block costs,
  declaration triggers, multi-attacker blocking, blocked-status effects, and
  entry-blocking remain dependency-blocked.

## Current CR 120/210/310/506/507/508/509/510/511/512/513/514/600/601/602/603/604/605/606/607/608/609/614/615/616/704 slice

At the beginning of combat, supported two-player and multiplayer Commander
profiles establish every active opponent as a defending player without
issuing a defender-choice task. Represented permanent and delayed
beginning-of-combat triggers are both collected before active-player priority.
Alternate multiplayer options that require choosing one defender are rejected
at the profile boundary and remain blocked.

The combat snapshot authoritatively records the active attacking player, all
rules-defined defending players for supported Commander profiles, current
attacker/blocker relationships, and whether any attacking creature existed
during the combat. Represented combatants are removed when they leave the
battlefield, phase out, cease to be creatures, become Battles, or undergo an
invalidating control change. Tapping and untapping alone preserve combat
status. Generic effects that put creatures into combat or remove them, the
complete restriction/requirement and “alone” query systems, alternate
multiplayer options, extra combats, planeswalker destinations, and universal
combat-relative timing remain blocked.

Ordinary attacker declarations are server-derived from current public combat
state. Only controlled, untapped, present, nonphased creature permanents that
are not Battles and are not summoning sick without haste are offered and
revalidated. Opponent and opponent-protected Battle destinations are
validated, ordinary attackers tap while vigilance is preserved, illegal mixed
declarations roll back atomically, and attacking relationships last through
combat. If combat has no attackers after the required priority window, declare
blockers and combat damage are skipped. Planeswalkers, complete restrictions
and requirements, banding, attack costs, generic declaration triggers,
entry-attacking effects, defending-player LKI, and target reselection remain
blocked.

Ordinary blocker declarations are server-derived from current public combat
state. Only untapped, present, nonphased creature permanents that are not
Battles are offered, and each may block only an attacker assigned to the
declaring defender. The complete declaration is transactional, blocking
relationships persist until removal from combat or combat finalization, and
the command replays exactly. The engine does not claim the complete
restriction/requirement constraint problem, block costs, declaration-trigger
provenance, one blocker blocking several attackers, or entry-blocking effects.

Manual combat-damage assignment is server-authoritative. The engine derives
the current combat sources, permitted recipients, and required effective-power
total from authoritative state; the client may submit only source, target, and
integer amount. A source with power 0 or less submits no assignment. Noncombat
sources, unrelated recipients, missing or excessive totals, duplicate pairs,
malformed fields, and client-supplied semantic flags are rejected before
damage is applied. Ordinary multi-blocker damage command-replays exactly.
Unsupported first strike, double strike, trample, and lifelink fail closed
before a damage decision is exposed.

Battle behavior is derived from the effective card type, subtype, defense
characteristic, counters, controller, and protector. It contains no
printed-name branch. Off the battlefield, a Battle exposes its printed or
copied defense. On the battlefield, its effective defense is its current
defense-counter count. A Battle entering as itself or as a copy initializes
from printed entry characteristics rather than copying the source permanent's
current counters. Damage marks a creature, removes planeswalker loyalty, and
removes Battle defense for every applicable type on a multi-typed permanent.
Negative damage fails closed. A source with negative power assigns zero combat
damage, and zero is suppressed before life, counters, marked damage,
commander attribution, or a damage event can occur. Damage results do not
destroy or move a permanent directly; the subsequent immutable state-action
batch does that work. Marked damage survives loss of creature type and clears
at cleanup.

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

- 3,829 unit/integration tests pass: 529 ordinary tests plus 3,300 generated
  inventory/source-linkage tests. The latter are not semantic passes.
- Six focused CR 506 tests cover all-rule traceability, the empty-combat phase
  boundary and exact replay, authoritative attacking/defending roles, removal
  after zone/control/phasing/type invalidation, historical-attacker retention,
  and tapping/untapping preservation.
- Five focused CR 507 tests cover all-rule traceability, the supported
  defending-player set, fail-closed single-defender variants, coexisting
  permanent/delayed triggers before priority, and exact replay into declare
  attackers.
- Eight focused CR 508 tests cover all-rule traceability, legal attacker
  exposure, tapping and vigilance, attacking-state lifetime, phased attacker
  and Battle-target rejection, duplicate rejection, atomic rollback,
  empty-combat step skipping, zero meaningful suppression, and exact command
  replay.
- Five focused CR 509 tests cover all-rule traceability, ordinary declaration
  and exact replay, phased/tapped exclusion, atomic malicious-declaration
  rollback, blocking-state lifetime, and the ordinary priority handoff.
- Nine focused CR 510 tests cover all-rule contract traceability,
  server-derived multi-blocker assignment, excessive-total rejection,
  noncombat-source rejection, nonpositive-power nonassignment,
  departed-blocker nonassignment, unrelated-recipient rejection, strict nested
  assignment fields, fail-closed first strike, atomic rollback, and exact
  command replay.
- Four focused CR 511 tests cover no-turn-action priority, coexisting
  permanent/delayed boundary triggers, multiplayer removal from combat, and
  exact replay into postcombat main.
- Four focused CR 512 tests pin the ending-phase contract, assert exact
  end-step/cleanup ordering, command-replay the next-turn handoff, and prove
  that a required cleanup discard prevents premature phase completion.
- Fifteen focused object/token tests cover monotonic incarnations, draws,
  timestamp moments, identity-sensitive targets and delayed links, private
  projection, token destination timing, move prevention, cessation, and exact
  replay.
- Eight focused copy-object tests cover serialized spell/card copies,
  counter/destination timing, card-versus-noncard targeting, same-object
  permanent resolution, projection privacy, and exact replay.
- Sixty focused CR 120/210/310/704 tests cover positive, negative,
  fixed-point, order-mutation, shared pre-action LKI,
  attachment/protection, counters, maximum-counter
  extraction/overlap/replay, sequential and simultaneous World behavior,
  printed-versus-battlefield defense, Battle-creature damage and combat
  restrictions,
  exact-incarnation triggers, protector choice/repair, projection, native
  transformed casting, decline/token/changed-object behavior, compiled and
  unresolved targets, contract pinning, and three command-replay paths.
- Seven focused CR 514 tests cover source traceability, exact private discard,
  invalid-action rollback, ordinary no-priority cleanup, state-action
  stabilization, delayed-trigger ordering, repeat cleanup, represented
  turn-duration clearing, and exact command replay.
- Five focused CR 513 tests cover source traceability, ordinary priority,
  coexisting permanent/delayed triggers, controller sentinels, late-source and
  late-trigger deferral, multiplayer, turn-duration handoff, and exact replay.
- Exact Zimone closure: 27 tests pass.
- Exact Mishra closure: 23 tests pass.
- The seed-20260730 regression reaches its corrected main-phase opportunities,
  keeps `suppressed_meaningful_windows=0`, passes seat projection, and exact
  command replay.
- Rules corpus verification passes for all 3,300 indexed rules, 3,300
  conformance records, and 425 mechanics. The 3,300 generated per-rule tests
  establish inventory linkage only. All 428 CR
  120/210/310/506/507/508/509/510/511/512/513/514/600/601/602/603/604/605/606/607/608/609/614/615/616
  cases are source-reviewed: 60 pass with executable engine evidence, 309
  remain blocked, and 59 are definition-only. The other 2,872 cases remain
  unreviewed.

Repository demo, repository audit, wheel build, clean wheel installation, and
final push evidence are recorded in `OVERNIGHT_HANDOFF.md` after the complete
checkpoint validation.

## Next dependency-ordered work

1. Continue reviewing and promoting conformance cases by
   dependency-ordered rules family; keep exposed but unimplemented edge cases
   failing or blocked. CR 506 Combat Phase is the current bounded family;
   retain alternate multiplayer options, generic effect-created combatants,
   requirement snapshots, extra combats, combat-relative timing, and universal
   same-controller/APNAP trigger batching as explicit blockers, along with the
   deeper CR 601.2a-i stack-first casting frame.
2. Wire the reviewed CR 614/615/616 primitives into the shared CR 120/310
   replacement and prevention event pipeline, including stateful shields and
   typed nested events, then re-evaluate the blocked damage sequence and
   310.11b exile/cast continuation.
3. Replace remaining physical-reference links with typed incarnation/LKI
   handles and implement the remaining CR 400.7 continuation policies.
4. Implement the remaining ordinary CR 704.5 specialized permanent/layout
   state actions.
5. Integrate state-action destruction/loss with typed replacement and
   regeneration events.
6. Continue the blocked CR 603 trigger-ordering, provenance, look-back,
   state-trigger, and reflexive-trigger dependencies.
7. Continue migrating static characteristics to CR 613 and all replaceable
   event producers to CR 616.
8. Implement the remaining CR 707 copiable-value, card-copy casting, and
   specialized copy-object exceptions.
9. Recompute full and Commander-legal Oracle coverage after each generic
   compiler/mechanic slice.

No deck list has been modified, and no current game result is promoted to
matchup evidence.
