# Rules completeness implementation status

Last updated: 2026-07-31

This is the durable execution ledger for the snapshot-scoped rules
completeness program. It records implementation evidence without claiming
Arena parity, complete Comprehensive Rules enforcement, or complete Oracle
coverage.

## Pinned baseline

- Repository: public `MoellerJDev/mtg-commander-sim`
- Current integration branch: `main`
- Rules integration PRs #1–#17, #24, and #25 are merged; the cumulative PR
  #24 tip incorporated the exact CR 400–408 heads before PRs #18–#23 closed as
  superseded
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
| Mechanic contracts | In progress | 49 partial/untrusted contracts; 376 mechanics unclassified; 0 trusted |
| Typed Oracle IR | In progress | `oracle-ir-v2`, source spans, fail-closed material residuals |
| Object and zone identity | Partial | All 30 CR 400 records reviewed; owner-zone routing, logical incarnations, permanent-spell continuation, serialized zone timestamps, target revalidation, hidden outside-game movement, and selected linked-effect guards |
| Library | Partial | All 8 CR 401 records reviewed; hidden order/public count, bounded look/reorder, shuffle knowledge clearing, and Nth-from-top placement; simultaneous owner ordering and continuous top-card visibility remain blocked |
| Hand | Partial | All 4 CR 402 records reviewed; starting/maximum size, cleanup-only excess discard, public count, scoped identity, public-to-hand knowledge, and controller dual-hand access; continuous no-maximum and arbitrary reveal/look grammar remain blocked |
| Battlefield | Partial | All 6 CR 403 records reviewed; one shared multiplayer domain, controller-index integrity, ordinary battlefield-only scope, permanent categorization, and ordinary new-object entry; the complete CR 400.7 exception matrix remains blocked |
| Graveyard | Partial | All 4 CR 404 records reviewed; public owner-indexed membership, ordering, and exact-incarnation moves pass for the represented subset; arbitrary ordering and broader replacement interactions remain blocked |
| Stack | Partial | All 15 CR 405 records reviewed; one shared LIFO stack, public ordering, top-object resolution, and exact replay pass for represented objects; full copying, targets, and unsupported stack-object forms remain blocked |
| Exile | Partial | All 11 CR 406 records reviewed; public/face-down visibility, owner routing, linked exact-incarnation return, and fail-closed unsupported identity access are represented |
| Ante | Unsupported | All 5 CR 407 records reviewed; Commander deck validation rejects pinned-illegal ante cards and no ante variant actions or zone are exposed |
| Command | Partial | All 4 CR 408 records reviewed; public Commander cards and typed emblem objects are represented, while non-Commander casual variants and arbitrary emblem compilation remain blocked |
| Continuous-effect layers | Partial | CR 613 evaluator and engine integration for selected derived characteristics |
| Replacement/prevention ordering | Partial | CR 615/616 typed primitives; stateful shields and event-producer integration incomplete |
| Damage, defense, and Battles | Partial | Type-driven CR 120/210/310 damage results, counter-derived battlefield defense, copied printed defense, Siege protector/combat routing, and exact-incarnation defeated-trigger exile/optional transformed cast |
| State-based actions | Partial | CR 704 snapshot evaluator, token/copy cessation, World rule, numeric maximum-counter restrictions, Battle defense/protector checks, and fixed-point engine integration for the reviewed subset |
| Full Oracle compilation | In progress | exact 2,957; partial 15,691; unresolved 19,725; 69,664 material residuals |
| Commander-legal Oracle compilation | In progress | exact 338; partial 14,354; unresolved 16,930; 61,212 material residuals |
| Official-source conformance/property/mutation gates | In progress | 3,300 source-pinned cases and per-rule inventory tests exist; 557 cases are reviewed, with 106 executable passes, 371 blocked cases, and 80 definition-only cases; 2,743 remain unreviewed |
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
- [x] Reviewed all 4 CR 503 Upkeep Step records. The ordinary no-turn-action
  priority boundary passes. Represented triggers from untap, permanent upkeep
  abilities, and delayed upkeep abilities wait without priority and share one
  APNAP/controller-order batch with exact replay. Complete CR 502 event
  production, CR 603.3b trigger-on-trigger ordering, additional upkeep
  scheduling, and after-first-upkeep casting grammar remain dependency-blocked;
  the heading is definition-only.
- [x] Reviewed both CR 501 Beginning Phase records. The ordinary untap,
  upkeep, then draw structure passes with exact replay into precombat main.
  A duel turn-one draw skip suppresses only the draw action, not the draw
  step. Generic additional or skipped phases and steps remain CR 500
  dependencies; the heading is definition-only.
- [x] Reviewed all 16 CR 500 General turn-structure records. The ordinary
  five-phase table, full empty-stack priority pass round, ordinary
  no-priority boundaries, mana emptying before the next step, and atomic
  phase/step transition behavior pass. Unsupported pre-populated skipped-step
  schedules now fail closed before mutation. Generic duration expiry,
  retained mana, complete boundary-trigger production, simultaneous extra
  turns, added phases or steps, controller-relative suppression, and generic
  skip replacement ordering remain dependency-blocked; two taxonomy records
  are definition-only.
- [x] Reviewed all 15 CR 405 Stack records. Top insertion, complete-pass LIFO
  resolution, direct effects, represented static abilities, and represented
  state actions pass, including exact replay. A non-top object now cannot
  begin resolution. Stack-first casting, complete effect-created APNAP
  placement, characteristics, triggered mana, the full special/turn-based
  action catalogs, concession outside priority, and complete player-leaves-
  game ordering remain dependency-blocked; two taxonomy records are
  definition-only.
- [x] Reviewed all 30 CR 400 General records. Zone topology, owner routing,
  logical incarnation changes, permanent-spell continuation, represented LKI,
  authorized face-down identity, and hidden outside-game movement pass.
  Same-graveyard moves are no-ops and instant or sorcery battlefield entry is
  rejected transactionally. The complete new-object exception matrix,
  special command-zone objects, sideboards and wish effects, simultaneous
  replacement integration, and whole-zone grammar remain blocked; three
  taxonomy records are definition-only.
- [x] Reviewed all 8 CR 401 Library records. Deck-to-library initialization,
  public counts, hidden order, bounded look/reorder, shuffle knowledge
  clearing, and Nth-from-top insertion pass. Zero and malformed look counts
  and stale reorder groups now fail safely. Generic simultaneous owner-secret
  insertion order, continuous top visibility and procedure freezing, and
  reveal-continuity new-object identity remain blocked; the heading is
  definition-only.
- [x] Reviewed all 4 CR 402 Hand records. Configured starting-hand draws,
  finite maximum size, cleanup-only excess discard, public counts, owner and
  viewer-scoped identity, and private hand order pass. Hidden-zone movement
  now separates an opaque public event from the authorized identity event,
  public-to-hand identity remains known, and a player controlling another
  player retains both private views. CR 613.11 maximum modifiers, no-maximum
  effects, and complete arbitrary hand reveal/look grammar remain blocked;
  the heading is definition-only.
- [x] Reviewed all 6 CR 403 Battlefield records. Controller-indexed
  presentation lists form one shared multiplayer target domain and now fail
  an invariant check if storage and controller diverge. Cross-controller
  attachments preserve both relationships. Unqualified target schemas and
  ordinary destroy, sacrifice, and bounce operations use battlefield scope,
  permanent category follows battlefield membership, and ordinary entry
  creates a new logical incarnation while CR 400.7a preserves a resolving
  permanent spell. The complete CR 400.7 exception matrix remains blocked;
  the heading and legacy in-play terminology are definition-only.
- [x] Reviewed all 6 CR 502 Untap Step records. Ordinary stackless untaps,
  represented stun and next-untap restrictions, held-trigger handoff, and
  exact replay are characterized. Phasing and global maximum-untap choices now
  fail closed before mutation. Direct/indirect phasing, day/night,
  shared-team turns, arbitrary selection, complete replacement ordering, and
  universal trigger production remain dependency-blocked; the heading is
  definition-only.
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

## Current CR 120/210/310/400/401/402/403/405/500/501/502/503/506/507/508/509/510/511/512/513/514/600/601/602/603/604/605/606/607/608/609/614/615/616/704 slice

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

Ordinary modal double-faced cards now distinguish their front spell face from
each playable land face during legal-action generation. A selected land face
drives battlefield type validation, active-face projection, and face-specific
entry text, including generic exact-N optional life payments such as Agadeem,
the Undercrypt's 3 life. This closes the observed silent non-entry defect; it
does not claim complete transforming-double-faced-card, copy, replacement, or
alternate-casting coverage.

## CR 400/613/111/704/707 foundation

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

The completed CR 400 family review additionally prevents an instant or sorcery
card from entering the battlefield before any mutation, treats an ordinary
same-zone graveyard move as a true no-op rather than a reorder, routes
nonbattlefield destinations to the owner's corresponding zone, and preserves
the visibility of a hidden card moved outside the game instead of revealing it
globally. A face-down object in a public zone is identifiable only to its owner
or another viewer who is explicitly authorized to know it.

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

Emblems now have a distinct serialized noncard object kind. The generic
creation primitive puts one in the receiving player's public command-zone
presentation with only its created abilities as characteristics. Daretti's
reviewed emblem uses this primitive, and its artifact trigger records the exact
emblem source. Other emblem programs and Planechase, Vanguard, Archenemy, and
Conspiracy Draft command objects remain unimplemented and fail closed.

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

- 3,925 unit/integration tests pass: 625 ordinary tests plus 3,300 generated
  inventory/source-linkage tests. The latter are not semantic passes.
- Seven focused CR 403 tests cover exact source traceability, empty and shared
  four-player battlefield structure, controller-index integrity,
  cross-controller attachment projection, ordinary battlefield-only scope,
  permanent categorization, instant/sorcery entry rejection, ordinary and
  CR 400.7a entry identity, and pinned Oracle terminology.
- Seven focused CR 404 tests cover public owner-indexed graveyards, exact
  ordering and incarnation moves, multiplayer visibility, transactional
  rejection, and replay boundaries without promoting complete ordering or
  replacement behavior.
- Seven focused CR 406 tests cover public and face-down exile visibility,
  owner routing, linked exact-incarnation movement, projection boundaries,
  rejection of unavailable identities, and replay.
- Five focused CR 407 tests pin the unsupported ante boundary, reject
  Commander-illegal ante cards across deck sections, and prove that no ante
  zone, contribution action, ownership transfer, or variant profile is
  exposed.
- Seven focused CR 408 tests cover the shared public command presentation,
  typed noncard emblem objects, ordinary destroy exclusion, exact Daretti
  source binding, unsupported casual-variant rejection, state round trip, and
  replay.
- Eight focused CR 402 tests cover exact source traceability, configured
  starting hands, above-maximum state until cleanup, hidden-move event
  redaction, public-to-hand knowledge, viewer-scoped reveal, retained own-hand
  access while controlling another player, private order, and public counts.
- Seven focused CR 401 tests cover exact source traceability, deck
  initialization, public counts and hidden order, zero/invalid look handling,
  exact current-top reorder validation, Nth-from-top/bottom fallback, and
  shuffle knowledge clearing.
- Six focused CR 400 tests cover exact source traceability, zone topology and
  visibility, owner-zone routing, transactional instant/sorcery battlefield
  rejection, same-graveyard no-op behavior, and hidden outside-game movement.
- Six focused CR 405 tests cover exact source traceability, two-object LIFO
  priority and replay, transactional non-top rejection, immediate activated
  mana, direct effect/state-action execution, and leaving-player stack
  cleanup.
- Five focused CR 500 tests cover exact source traceability, the ordinary
  five-phase table, a four-player empty-stack priority round with exact
  replay, mana emptying before the next step, and transactional rejection of
  an unsupported skipped-step schedule.
- Three focused CR 501 tests cover source traceability, the exact ordinary
  untap/upkeep/draw table, a turn-one skipped draw action without a skipped
  draw step, transition into precombat main, and exact replay.
- Six focused CR 502 tests cover source traceability, ordinary simultaneous
  stackless untap, represented stun and one-shot prohibitions, fail-closed
  phasing, fail-closed maximum-untap selection, held-trigger timing, and exact
  replay.
- Five focused CR 503 tests cover source traceability, the ordinary no-turn-
  action priority boundary, one APNAP/controller-order batch spanning untap
  and upkeep trigger times, state actions before trigger placement, late-
  trigger deferral, and two exact replay paths.
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
  establish inventory linkage only. All 557 cases in the current reviewed
  families are source-reviewed: 106 pass with executable engine evidence, 371
  remain blocked, and 80 are definition-only. The other 2,743 cases remain
  unreviewed.

Repository demo, repository audit, wheel build, clean wheel installation, and
final push evidence are recorded in `OVERNIGHT_HANDOFF.md` after the complete
checkpoint validation.

## Next dependency-ordered work

Broad sequential rules review is frozen after the CR 400–408 and CR 500–512
integration reached `main`. The first authoritative server/browser slice now
has a shared, versioned form adapter for the engine's current choice schemas,
four-context private mulligan coverage, and process-restart recovery with exact
replay. The owner-only administrative stop/resume and seated-member safe
inspection slice is now implemented. It preserves exact replay through process
restart and cannot override a material rules/fidelity pause. Invited spectators
now receive only public projections and a complete durable public log. The next
steps are:

1. Fix the full-database browser regression in which Sunscorched Desert's ETB
   was omitted and Orcish Bowmasters produced a browser-inaccessible
   `arbiter.resolve` boundary instead of a visible trusted-only pause.
2. Continue server operations hardening: expiry/rate limits, deployment
   boundaries, and multi-process ownership design.
3. Harden browser accessibility, command-retry presentation, and any
   new choice-schema family only when the engine introduces it.
4. Resume rules work for defects that block those slices; defer broad
   CR-number traversal until it has concrete executable evidence.

No deck list has been modified, and no current game result is promoted to
matchup evidence.
