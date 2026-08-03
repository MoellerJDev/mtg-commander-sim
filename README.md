---
title: "MTG Commander Sim"
status: "current"
authoritative_source: "implemented package, server/browser runtime, and generated status reports"
verified: "2026-08-02"
audience: "users and contributors"
maintenance: "hand-maintained"
---

# MTG Commander Sim 0.8.0

An experimental, deterministic, server-authoritative Commander platform under
active development. Four-player Free-for-All Commander is the primary product
target, with a browser client, durable game runtime, exact replay, and
snapshot-scoped rules enforcement. The current development line is a kernel and
protocol foundation, not a complete implementation of Magic's rules or Oracle
corpus.

Current development checkpoint: the deterministic foundation and reviewed
rules slices have an executable server/browser vertical slice. It provides
tab-isolated guest sessions, invite-only two- or four-seat rooms, deck
validation/preflight, a serialized single-writer game actor, SQLite control
plane, durable Game Record v3 acknowledgement, strict idempotent protocol 3.0
commands, seat-scoped WebSockets, reconnect and process-restart recovery, and a
responsive TypeScript/React table. Invited guests can also join as read-only
spectators: they receive only the public projection, cannot submit seat
commands, and can browse the complete durable public event log. One Python process now builds and serves the
browser, prepares the local Scryfall SQLite index, checks for updated Oracle and
rulings exports every 24 hours, and serves an on-demand local card-image cache.
The browser renders the engine's current generic choice vocabulary, locally
  cached card art, a persistent hover/focus card viewer, browsable public zones,
  card-specific play/cast/activate controls, resilient drag-to-play interaction,
  saved Auto-mana/Manual mana and Auto-pass/Full control preferences, visible
  tapped-card rotation and labels for every seat, a bottom-anchored resizable
  hand dock, reconnect and exact-command retry states,
  explicit active-player main-phase advancement, attack/block interaction,
  public commander-damage tracking, confirmed concession, and terminal
  winner/draw presentation,
  owner-only durable stop/resume controls, and a seat-safe record inspection
  panel. These paths are
end-to-end tested with four shared-cookie tab-isolated seats and a two-player
duel, plus an isolated invited spectator. A deterministic two-browser rules
journey also covers immediate targeted land ETBs, a real stack response,
rules-created Treasure payment, permanent-spell resolution, Amass, combat, and
a natural commander-damage winner. Future choice schemas, full account
identity, expiry/rate limits, and production operations remain incomplete.
The browser interaction slice is integrated. Development is now in a measured
architecture migration: dependency, mutation, card-specificity, compiler, and
documentation boundaries are enforced while the legacy kernel is decomposed.
Generated status documents record exact current counts.

This is a structural rewrite of the earlier two-player duel lab. The server-side game kernel is now separate from:

- untrusted browser, scripted, manual, subprocess, and optional AI clients
- semantic compilation and development-only rules arbitration
- hidden-information projections
- client transport and authentication
- reporting and deck-performance analysis

The engine is authoritative. Clients choose server-issued legal actions through
short-lived capabilities; they never write zones, life, mana, triggers, or
effects directly. Ordinary gameplay, rules enforcement, CI, and releases do not
require an LLM, Codex runtime, provider credential, or live AI ruling.

Start with [`docs/index.md`](docs/index.md), the authoritative map that labels
current, target, generated, ADR, and historical material.
See `docs/PLATFORM_IMPLEMENTATION_STATUS.md` for the generated integration,
rules, server, browser, persistence, replay, privacy, and validation ledger.
See `docs/ARCHITECTURE_DEBT_STATUS.md` and
`docs/COMPILER_COVERAGE_STATUS.md` for the measured migration baseline and the
current compiler/Oracle boundary.
See `SERVER_BROWSER.md` for the executable API, local run commands, browser
workflow, security boundary, and remaining UI/operations limits.

## Quick start

Install 64-bit CPython 3.12.x and Node.js 22+. Python 3.11 and 3.13+
are intentionally unsupported for this development line. On Windows, the
bootstrap script validates `py.exe`, explains the safe per-user `winget`
command if 3.12 is missing, creates `.venv`, and installs the project:

```powershell
.\scripts\bootstrap_windows.ps1
.\.venv\Scripts\python.exe -m server
```

The equivalent manual setup is `py -3.12 -m venv .venv`, followed by
`.\.venv\Scripts\python.exe -m pip install -e . -r requirements-dev.txt`.
Use the project interpreter directly for later commands; activation is
optional and must not hide which Python version is running.

That is the entire local application startup. The server installs browser
packages on the first run, rebuilds the browser when its sources change, and
prints `http://127.0.0.1:8000` without interrupting another browser session.
Open that URL yourself, or pass `--open` when you explicitly want automatic
browser launch. The UI shows first-run card-data progress.
Initial setup downloads Scryfall's compressed Oracle Cards and Rulings exports
and builds `data/scryfall-current.sqlite3`. It checks again every 24 hours.
Every startup checks the live manifest before enabling deck import. If the
local snapshot is stale, the setup screen remains visible until the replacement
is built and activated; if the check is offline, the existing snapshot becomes
available with a visible warning.
This follows [Scryfall's recommendation to use bulk data for large local card
and image workloads](https://scryfall.com/docs/faqs/i-m-having-trouble-accessing-the-scryfall-api-or-i-m-blocked-17)
instead of performing one API lookup per card.
After a successful refresh, the previous managed bulk archives are deleted;
only the current Oracle/rulings pair is retained. A refresh discovered during
a live process is staged and activated on the next restart so an in-progress
Game Record never changes rules data underneath itself. The previous SQLite
snapshot is retained by fingerprint only while a saved Game Record references
it; unreferenced database snapshots are deleted during activation.

Card images are not mirrored wholesale. Image references come from the same
bulk snapshot; the server downloads normal images for submitted decks in the
background and caches any other visible art on demand under `data/images/`.
The browser requests only the local `/api/v1/cards/.../image` route. Use
`Ctrl+C` to stop the application and rerun the same command to resume.
Images remain unmodified local third-party cache files and are never committed
or packaged. See [the content boundary](docs/LEGAL_CONTENT_BOUNDARY.md) for
attribution, display constraints, and deployment review requirements.

The current identity layer is an expiring, per-browser-tab guest session: choose
a display name, host or join a private 1v1 duel or four-seat room, or use the
same invite as a watch-only spectator. Seated players submit a
Moxfield URL or pasted deck, and start when every configured seat shows ready.
Incognito windows may share cookies without collapsing into one seat. The host invite remains
visible after readying and reload; the host can replace it if necessary, and
any player can **Change deck / Unready** before start. Owners can remove another
player or create a fresh room; nonowners can leave and release their seat. Full
password/OAuth accounts are not implemented yet.

Cards from a published preview that are present in Scryfall but not legal until
their future release date produce an explicit confirmation screen instead of a
generic rejection. The confirmation is bound to the exact deck fingerprint and
warning list and is saved with the deck/game provenance. It does not override
bans, deck-construction errors, missing card data, or unsupported rules
semantics; material semantic gaps still fail closed during play.

At the table, hover or keyboard-focus any visible card to show large art and its
full projected name, mana cost, type line, and Oracle text in the desktop card
viewer. Double-faced cards expose both visible faces. On a narrow screen, use
the floating **View card** control for the same enlarged view. Graveyard and
exile counts are buttons that open the complete public contents for that seat;
hands and libraries remain seat-private. **Public log** opens the complete
chronological public event history and remains available after reconnect or a
server restart; raw event details and private events never enter that response.

Cards with a current action are highlighted and labeled **PLAY**, **CAST**,
**ACTIVATE**, or **CHOOSE**. Select a hand, command-zone, public-zone, or
battlefield card to reveal only that object's current server-issued actions.
Drag a playable land or spell to your battlefield for the fast path; an
ambiguous card opens a short action chooser. Spell confirmation exposes the
default **Auto-mana** path. The table-level Auto-mana/Manual mana setting is
saved in this browser. Turn on **Manual mana** to highlight payable mana
abilities, then click those permanents in the order you want to activate them;
multi-color sources ask which exact mana to add. Choose the spell again after
floating mana. Manual mode controls source activation order while the server
still validates the pool and may complete a routine remaining payment.
Before that mana is spent, priority is passed, or the window otherwise changes,
click the same tapped source again (or its **Undo mana** control) to remove the
exact mana it produced and untap it. Activations with sacrifice, life payment,
restricted mana, or another side effect are intentionally not reversible.
Rules-created mana tokens are handled by the same path without requiring a
Scryfall printing. For example, Treasure offers only the five legal color
outputs and its tap/sacrifice costs are paid before mana is added; Auto-mana
may consume it only when those represented costs and outputs are fully
compiled.

Modal double-faced cards receive one action for each currently playable use.
For example, Agadeem's Awakening can be selected as a spell or as **Play
Agadeem, the Undercrypt**. The land action asks whether to pay exactly 3 life,
then enters and renders using the chosen land face. Client labels and drag
gestures never create legality; they invoke the same server-issued action IDs
as the ordinary action tray.

Additive basic-land-type effects use effective layer-4 characteristics rather
than printed card names. Under Urborg, Tomb of Yawgmoth, for example, Darksteel
Citadel keeps its Artifact/Land types, indestructible text, and colorless mana
ability while also receiving the intrinsic Swamp black-mana ability. The same
generic compiler/runtime path covers exact equivalent wording for every basic
land type.

Browser games expose every priority capability to the owning tab. **Auto-pass**
is on by default and submits an ordinary replayable pass command only in a safe
response window with no meaningful nonmana action. It never skips a playable
land, cast, target, combat declaration, or other player choice, and it never
advances the active player's empty-stack precombat or postcombat main phase.
Those two turn boundaries always require **Continue to combat** or **End turn**,
preventing two Auto-pass clients from silently cycling whole turns. Turn on
**Full control** at any time to hold every otherwise pass-only priority window;
the preference is saved in this browser.

Commander combat damage is always displayed separately by source commander on
every public player board, including an explicit zero before any is dealt.
**Concede game** is a server-issued action with an explicit
confirmation; cancelling it does nothing, while acceptance follows the same
transaction, persistence, projection, and replay path as any other command.
When a winner or draw is authoritative, both seats receive a terminal banner,
all action controls disappear, and that result survives process restart.

For offline development with an existing database:

```powershell
$env:MTG_CARD_DB = "data/test-ci.sqlite3"
.\.venv\Scripts\python.exe -m server --offline
```

The repository deliberately does not contain a full Scryfall export or SQLite
database. CI builds a small database from the committed public exact-list
fixture:

```bash
python scripts/build_test_database.py build \
  --fixture tests/fixtures/scryfall-exact-lists.json \
  --fixture tests/fixtures/browser-lifecycle-cards.json \
  --fixture tests/fixtures/damage-result-cards.json \
  --output data/test-ci.sqlite3
MTG_CARD_DB=data/test-ci.sqlite3 \
  python -m unittest discover -s tests -p "test_*.py" -v
```

In PowerShell, set the variable with
`$env:MTG_CARD_DB = "data/test-ci.sqlite3"` before running the tests. The
compact fixtures cover the bundled Zimone and Dina and Mishra, Eminent One
lists, the CR 120 damage-result witnesses, plus one vanilla commander used
only for deterministic combat/lifecycle
testing; they are not a substitute for the complete Oracle corpus or matchup
evidence.

For an exact-commit merge candidate, use the reusable gate after committing all
intended changes:

```powershell
.\.venv\Scripts\python.exe scripts/local_merge_gate.py `
  --expected-branch <branch> `
  --expected-sha <full-sha>
```

It rebuilds its database, runs the complete deterministic and focused
replay/privacy/game gates, creates a sanitized protocol demo, audits the
repository, builds and clean-installs the wheel, verifies a clean exit, and
writes ignored logs plus `summary.json` under
`local/merge-gates/<full-sha>/`.

To discover Scryfall's current timestamped Oracle and rulings exports and
atomically rebuild the local database before a game:

```bash
python scripts/bootstrap_data.py \
  --refresh-from-scryfall \
  --output data/scryfall-current.sqlite3
```

This follows `GET https://api.scryfall.com/bulk-data` at runtime and streams the
advertised `.jsonl.gz` files. Network access remains outside the game engine.

Game records, deck caches, bulk downloads, SQLite databases, pilot memories,
and live capability values are local-only artifacts under ignored paths such
as `run/` and `data/`. Do not commit them. The tracked `demo/` packets are
generated documentation fixtures with bearer capabilities redacted. See
`REPOSITORY_HYGIENE.md` and `SECURITY.md`.

## What is implemented

- 2–6 players; four-player free-for-all is the primary mode
- persistent libraries, hands, command zones, battlefields, graveyards, exile, stack, combat, and event history
- current multiplayer London mulligans:
  - declarations in turn order
  - all declared mulligans applied together after the round
  - seven cards redrawn each time
  - first multiplayer mulligan free
  - later penalties bottomed privately
- a configurable realistic mulligan guard: after the free redraw, a functional hand requires an explicit deck-specific reason before an LLM may go to six
- first-player draw in ordinary multiplayer Commander
- AP/NAP priority across every active seat
- automatic skipping of known-empty priority windows
- canonical meaningful-action signatures and conservative, invalidating yields
- an engine-side opportunity journal for every priority window, including
  delivered, safely yielded, pass-only, ordered-plan, and incorrectly
  suppressed dispositions
- attacks split among multiple defenders and defender-by-defender blocking
- extra-turn scheduling in most-recent-created-first order
- native upkeep/end-step delayed triggers
- snapshot-based state-action stabilization for lethal/deathtouch damage, zero
  toughness, planeswalker loyalty, the legend rule, poison, commander damage,
  player elimination, opposing +1/+1 and -1/-1 counters, and common
  Aura/Equipment/Fortification attachment cleanup
- multiplayer continuation after a player leaves
- conservative Oracle-informed automatic mana payment with exact source logging
- server-extracted explicit activated abilities, including hand-zone Channel abilities and validated nonmana cost selections
- authoritative printed costs: a pilot cannot understate a spell cost, invent an activation cost, or cast from an unauthorized zone
- first-class stack-object countering
- declarative, visibility-safe target plans for spells, abilities, players,
  stack objects, and public-zone cards
- mode-aware legal-action generation that withholds mandatory-target actions
  until every target group and current cost is satisfiable
- target validation on submission and resolution, including partial target
  survival and rules-countering when every selected target becomes illegal
- server-issued alternate/additional cost choices for the reviewed pitch,
  kicker, overload, commander-dependent, and life-X interactions
- top-of-library knowledge and reordering
- seat-private projections
- opaque single-use decision capabilities
- reusable semantic programs for card/ability resolutions
- resumable semantic frames for private library searches and later player
  choices, with deterministic continuation after the choice
- local Oracle text and Scryfall rulings; no card API calls during play
- plain-text and defensive Moxfield deck loading
- a FastAPI/ASGI guest, room, seat, spectator, deck, game, command, public-log,
  and WebSocket adapter
- one bounded, serialized `GameActor` mailbox per active game
- SQLite guest/room/seat/deck/game/idempotency control-plane persistence plus
  Game Record v3 durability before command acknowledgement
- React/TypeScript room and four-player table UI with Moxfield or pasted-list
  import, responsive desktop/mobile battlefield layout, local card art, private
  hand rendering, persistent hover/focus inspection, double-face viewing,
  public graveyard/exile browsers, card-specific legal-action prompts,
  resilient drag-to-play, saved automatic/manual mana and auto-pass/full-control
  modes, visible tapped orientation, generic server-issued choice forms,
  focus-contained dialogs, a durable public-log dialog, read-only spectator
  mode, reconnect, exact-envelope retry, and
  four-isolated-context Playwright coverage
- one-command local startup with browser build/static serving, a visible
  first-run setup state, managed 24-hour Scryfall bulk checks, atomic SQLite
  builds, bounded bulk-archive retention, and deck-prefetched/on-demand images
- generic browser controls for current cost/X, mode/target, private search,
  ordering, trigger, mulligan/cleanup, AP/NAP, legend, attack/block, combat
  damage, exact mana-mode, and storm-copy choices; the engine remains the sole
  validator
- strict protocol 3.0 command envelopes plus hash-checked projection patches
- per-connection ephemeral projection cursors, including multiple-tab and
  reconnect isolation for one seat
- lazy process-restart recovery from Game Record v3 with fresh capabilities,
  durable idempotency, continued commands, and exact replay verification
- a reference client reducer that can be reused by a GUI, WebSocket client, or LLM runner
- bounded same-capability retry packets for invalid model actions, without a full-state resend
- Game Record v3 checkpoints plus command/event/decision journals
- deterministic command replay with per-transition state hashes
- explicit `commander_duel` and `commander_multiplayer` profiles
- server-derived land entry and built-in fetchland search resolution
- modal double-faced land-face selection with face-specific entry text and
  exact optional life payments
- server-generated stable legal action IDs with exact alternatives in the decision audit
- derived turn-grouped reviews with an explicit fidelity gate
- provider-neutral scripted, manual-JSON, and subprocess-JSON pilots
- isolated, persistent per-seat strategic memory and fingerprinted deck profiles
- exact-list/profile/source fingerprint validation with explicit
  commander/archetype fallback warnings
- a fixed-seat MCP/CLI pilot surface that never exposes raw capabilities,
  checkpoints, analyst data, or another seat's hidden objects
- typed Codex pilot submissions with exact plan enums and bounded
  reason/memory fields
- project-scoped GPT-5.6 Sol pilot-agent configuration and a
  `commander-arena` Codex skill
- schema-validated semantic packs with trust and source provenance
- pinned Comprehensive Rules inventory, diff, verification, dependency, and
  mechanic-contract artifacts
- one source-pinned conformance case and inventory-linkage test for every
  numbered rule, with inventory kept separate from semantic passes
- typed, source-spanned Oracle IR with deterministic semantic hashes and
  fail-closed material residuals
- automatic deck-time generic compilation into provisional, arbiter-gated
  semantic programs
- Oracle IR v12 simple self-trigger, unconditional-entry, counter, pump, basic
  creature-token, fixed-mana combat-declaration cost, and exact combat-
  declaration restriction/evasion/battlefield-condition/composition and
  source-controller target-scope templates with reviewed-handler precedence,
  plus typed current-turn cast, death, damage, and prior-player-attack gates
- CR 613 layer/sublayer, timestamp, dependency, and cycle-audit primitives,
  now used for common copy/type/keyword annotations
- CR 616 replacement/prevention priority and affected-player-choice
  primitives
- source-reviewed CR 609 effect foundations with fail-closed condition
  predicates and explicit blockers for universal zone scope, impossible
  instructions, `as though`, tie handling, and damage-source derivation
- source-reviewed CR 608 resolution ordering with executable top-of-stack,
  untargeted permanent, and permanent-spell-copy behavior, while incomplete
  choice, LKI, Aura, mutate, and resolution-trigger families stay blocked
- source-reviewed CR 607 linked-ability taxonomy with exact-incarnation and
  undefined-choice witnesses; generic pair IDs, linked sets/facts, and
  copied, granted, cross-face, and cross-object links remain blocked
- source-reviewed CR 606 loyalty abilities with generic permanent support,
  exact base timing/activation limits, and fail-closed modified or combined
  loyalty costs
- source-reviewed CR 605 mana abilities with corrected target/loyalty
  exclusions, immediate activated-mana resolution, payment-path witnesses,
  and explicit blockers for generic triggered mana abilities
- source-reviewed CR 604 static-ability scope with source-leaves and
  moved-attachment witnesses; generic CDA, attachment, stack, zone-permission,
  and current-information/LKI handling remain blocked
- source-reviewed CR 603 trigger handling with executable pending-to-stack,
  controller-at-trigger-time, intervening-condition, and delayed-object-
  incarnation invariants; complete trigger grammar, two-part APNAP ordering,
  state/reflexive triggers, and the look-back exception matrix remain blocked
- source-reviewed CR 601 casting with immutable revision-pinned proposals,
  shared advertisement/execution cost and target queries, executable
  mana-ability payment-window ordering, transactional rollback and cast-trigger
  witnesses; complete
  announcement ordering, choice/cost grammar, proposal-dependent permissions,
  and opponent-made casting choices remain blocked
- source-reviewed CR 600 section taxonomy linked to its dependent CR 601-609
  contracts without inventing standalone behavior for the heading
- source-reviewed CR 400 zone and object-identity invariants: the seven normal
  zones, owner-zone routing, logical incarnation changes, permanent-spell
  continuation, authorized face-down visibility, and outside-game secrecy
  pass; same-graveyard movement is now a no-op and instant or sorcery cards
  cannot enter the battlefield, while the complete CR 400.7 exception matrix,
  special command-zone objects, sideboards, and whole-zone instruction
  grammar remain blocked
- source-reviewed CR 401 library boundaries: deck cards initialize in their
  owners' libraries, counts are public while identity/order remain
  seat-scoped, look/reorder/shuffle paths preserve hidden information, and
  positive Nth-from-top placement falls back to the bottom of a short library;
  zero-card looks no longer expose the entire library and stale known cards
  cannot be pulled to the top, while simultaneous owner ordering, continuous
  top reveal/look, and reveal-continuity identity remain blocked
- source-reviewed CR 402 hand boundaries: configured starting hands and
  finite maximum sizes are authoritative, excess cards remain in hand until
  cleanup, every hand count is public, and identities remain viewer-scoped;
  hidden-zone moves now publish only an opaque move while privately logging
  the identity, public-to-hand moves remain known, and a player controlling
  another player retains access to both hands; continuous no-maximum and
  arbitrary hand-reveal semantics remain dependency-blocked
- source-reviewed CR 403 battlefield boundaries: the controller-indexed
  presentation lists form one shared multiplayer target domain, controller
  membership is invariant-checked, unqualified targets and ordinary
  destroy/sacrifice/bounce effects are battlefield-scoped, permanent status
  follows battlefield membership, and ordinary reentry creates a new logical
  object; the complete CR 400.7 exception matrix remains blocked
- source-reviewed CR 404 graveyard boundaries: ordinary counter, discard,
  destroy, sacrifice, and completed instant-or-sorcery paths append to the
  owner's public face-up pile, including a rules-countered permanent spell;
  owner/index divergence is invariant-checked and same-graveyard moves do not
  reorder the pile, while simultaneous same-owner ordering choices remain
  explicitly blocked
- source-reviewed CR 405 stack structure: new objects are placed on top,
  complete priority rounds resolve only the top object, direct effects,
  represented static abilities, and represented state actions bypass the
  stack, and LIFO exact replay passes; direct non-top resolution now fails
  before mutation, while stack-first casting, complete simultaneous APNAP
  placement, characteristics, special actions, concession-at-any-time, and
  player-leaves-game ordering remain blocked
- source-reviewed CR 406 exile boundaries: ordinary objects enter an
  owner-indexed public holding area, exiling a card spell atomically removes
  its stack object, and re-exiling creates a new logical incarnation; generic
  face-down creation, look authorization, pile/random selection, return-pile
  provenance, and linked exiled-card sets remain explicitly blocked
- source-reviewed CR 407 ante exclusion: supported Commander profiles have no
  ante zone or ante operation, reject an ante profile and destination before
  mutation, and now validate pinned Commander legality for mainboard,
  commander, companion, and sideboard entries; the optional ante variant
  itself remains explicitly unsupported rather than partially simulated
- source-reviewed CR 408 command-zone objects: all Commander seats expose
  their designated commanders through one public zone, and generic emblems
  now persist as typed noncard, nonpermanent command objects with
  exact-source triggers and replay; non-Commander casual-variant objects and
  arbitrary emblem ability compilation remain explicitly blocked
- source-reviewed CR 500 general turn structure: the ordinary five-phase
  table, full empty-stack priority round, no-priority boundaries, mana
  emptying before the next step, and atomic transition behavior pass with
  exact replay; a pre-populated skipped-step schedule now fails closed before
  turn mutation, while generic duration expiry, simultaneous extra turns,
  additional phases or steps, and skip replacement ordering remain blocked
- source-reviewed CR 501 beginning-phase structure: the ordinary turn table
  contains untap, upkeep, then draw; a turn-one draw skip suppresses only the
  draw action rather than the draw step, and the phase transition exact-
  replays into precombat main; added or skipped phases and steps remain CR 500
  dependencies
- source-reviewed CR 502 untap boundary: ordinary untaps, stun replacement,
  represented one-shot prohibitions, stackless trigger holding, and exact
  replay are characterized; unsupported phasing and global maximum-untap
  choices now stop before mutation, while day/night and complete selection
  grammar remain blocked
- source-reviewed CR 503 upkeep boundary: represented triggers that occur
  during untap and at the beginning of upkeep wait without priority, then
  share one APNAP/controller-order batch before active-player priority;
  complete untap events, additional upkeeps, and after-upkeep casting grammar
  remain blocked
- source-reviewed CR 506 combat-phase boundary: authoritative attacking and
  defending roles, declaration-time player/planeswalker/Battle target context,
  durable combat history, represented removal from combat
  after zone/control/phasing/type changes, and the real second combat-damage
  step required by first/double strike; alternate multiplayer options, generic
  effect-created combatants, restriction snapshots, extra combats, and
  combat-relative timing grammar remain blocked
- source-reviewed CR 507 beginning-of-combat boundary: supported Commander
  profiles establish every active opponent as a defending player without a
  defender-choice task, coexisting permanent and delayed triggers are
  collected before active-player priority, and unsupported single-defender
  multiplayer variants fail closed
- source-reviewed CR 510 combat-damage assignment validation: the server
  derives sources, recipients, and exact power totals, rejects client-supplied
  semantics, collects discretionary announcements in APNAP order, derives
  forced assignments without a pilot task, and rolls each illegal announcement
  back atomically. First/double strike use two real damage steps; normal trample
  validates lethal before spill using marked damage and deathtouch; combat
  lifelink counts only damage dealt. Final combat source-recipient results emit
  normalized `damage.dealt` contexts, and represented damage/death triggers
  share one APNAP/controller-order batch before priority. Trample over
  planeswalkers, banding, the universal CR 120.4 replacement/result pipeline,
  noncombat damage events, and source LKI remain blocked
- source-reviewed CR 508 ordinary attacker declaration: the server offers and
  revalidates only currently eligible creatures and live opponent,
  planeswalker, and Battle destinations, enforces defender, preserves
  vigilance, rejects duplicate or
  phased submissions, and uses a shared finite constraint solver to maximize
  represented attacks-each-combat and typed single/multiple-player goad
  requirements—including duel and all-opponents-goaded cases—
  atomically, skips empty-combat blocker/damage steps, and command-replays the
  declaration. Typed public battlefield conditions cover defender/controller
  permanent existence, another-object exclusion, tapped state, characteristics,
  fixed stats, minimum counts, and relative creature/land counts per multiplayer
  defender. Exact other-attacker and filtered-companion implications, source-
  controller target restrictions, per-defender attacker caps, and exact
  source-specific attack maxima use the same solver and projected domains.
  Goad designations are public, noncopiable, same-player
  redundant, removed by zone changes, and expire at the goading player's next
  represented turn. Whole-line fixed ordinary-mana intrinsic, defending-
  player, player-and-planeswalker, planeswalker-only, and attached-Aura attack
  taxes are projected, locked after attackers tap, and paid atomically through
  manual or automatic mana plans; electing a taxed attack never raises the
  free requirement maximum. Optional, nonmana, variable, alternative,
  modified, and broader conditional costs, attack triggers, entry-attacking,
  eliminated-player duration boundaries, and target reselection remain blocked
- source-reviewed CR 509 ordinary blocker declaration: the server derives
  eligible blockers and defended attackers, rejects phased-out submissions,
  enforces menace's zero-or-two minimum, preserves blocking relationships
  through combat, and command-replays the declaration. Whole-line fixed
  ordinary-mana intrinsic, attached-Aura, and global block taxes are locked and paid
  atomically; costed choices do not compel payment to satisfy more
  requirements. Exact blocks-each-combat, must-be-blocked, lure, and menace
  constraints use the same solver, including impossible/conflicting cases.
  Typed controller/defender battlefield conditions and conditional evasion use
  the same evaluator for projected domains and direct block-pair validation.
  Shared-creature-subtype thresholds count distinct creatures, with Changeling
  contributing once to every creature type.
  Other-blocker and filtered-companion implications, attacking-alone and no-
  other-creature evasion, and source-controller-relative block restrictions
  are recomputed from the current public declaration state.
  Complete requirement grammar, optional/nonmana/variable/modified costs,
  triggers, multi-blocking, and entry-blocking remain blocked
- source-reviewed CR 802.5 multiplayer combat-damage ordering: assigning
  players proceed in APNAP order, later players receive earlier public
  assignments, forced divisions are automatic, and an illegal later division
  preserves the earlier accepted announcement
- source-reviewed CR 511 end-of-combat priority, trigger coexistence, and exact
  removal-from-combat handoff into postcombat main; generic effects lasting
  until end of combat remain explicitly blocked
- source-reviewed CR 512 ending-phase structure with exactly end then cleanup,
  exact replay into the next turn, and cleanup decisions preventing premature
  phase completion; behavior inside those steps remains bounded by CR 513/514
- source-reviewed CR 513 end-step boundary with no turn-based action,
  permanent and delayed trigger collection before priority, exact replay, and
  no retroactive triggers for objects or abilities created later in the step
- source-reviewed CR 514 cleanup sequencing with private simultaneous discard,
  ordinary no-priority advancement, and repeat-cleanup handling after an
  exceptional priority window; universal turn-duration expiration and complete
  state-action/trigger/APNAP interactions remain blocked
- source-reviewed CR 602 activation handling with immutable source/cost/target
  proposals, corrected untap-symbol summoning sickness, generic Crew and Craft
  lowering, and object-scoped once-per-turn restrictions; full cost
  grammar, activation transactions, opponent choices, and acquired-ability
  provenance remain blocked
- trust-aware semantic preflight for files and live Moxfield URLs
- compact cast, land, activation, target, and generic resolution-time search
  templates
- native-v3 pilot runs that can stop, save, resume, and command-replay
- validated aggregate shortcuts for the vertical-slice Soultrader and Gonti's Aether Heart lines

Version 0.7.0 adds trusted deterministic scenarios for the interaction slice
used by the exact review lists: the counterspell suite (including storm and
Pact/Mana Drain delayed effects), modal and mass removal, graveyard disruption,
Channel, Pithing Needle, proliferate, and Soul-Guide Lantern. This is exact
coverage for those declared programs, not a claim of complete Oracle coverage
for either deck.

Version 0.8.0 closes the conservative semantic preflight for the pinned live
Zimone and Dina and Mishra, Eminent One lists: both exact lists pass the
trusted-only gate without a partial or unresolved card. The closure adds
the remaining exact-list costs, permissions, replacement effects, delayed
effects, linked choices, copy/token engines, Saga chapters, Craft, Crew,
restricted mana, extra-turn control, and deterministic characterization
scenarios. It remains exact-list coverage, not full Oracle-corpus coverage.

## Compact projected-client protocol

The engine does not ask any client to perform deterministic bookkeeping or
respond to a priority window in which the implemented action grammar exposes no
meaningful action. A browser, scripted test client, or optional AI adapter
receives the same seat-projected packet with short object references and only
the current capability.

The bundled four-seat Mishra/Zimone benchmark records bootstrap, unchanged
decision, and declaration-delta sizes in generated
`demo/token-benchmark.json`. Card definitions are emitted once per principal.
Routine passes and bookkeeping remain in authoritative history but do not enter
ordinary packets. Detailed rulings are requested only when an interaction is
materially ambiguous. See `LLM_PROTOCOL.md`.

The seed-20260730 regression is reconstructed from a sanitized state recipe in
`tests/fixtures/`; it verifies the corrected action-opportunity boundary and
exact command replay without publishing the original checkpoint. Historical
live and Codex arena records remain private, local artifacts. Any duplicated
four-seat Zimone/Mishra arena is protocol/rules evidence only—never matchup
evidence and never a basis for changing either deck.

## Deliberate rules boundary

This project does **not** claim that arbitrary Magic Oracle prose has been converted into a complete deterministic rules implementation.

The kernel handles general game mechanics and a generic effect DSL. Strict
games use `semantic_policy=trusted_only` and stop or withhold an action when a
material spell or ability is unsupported. A development-only `arbiter` adapter
can characterize a narrowly scoped resolution and register a reusable semantic
program, but that path is not production legality or release evidence. Player
clients cannot submit arbitrary effects.

When a trusted-only browser game reaches an unsupported material resolution,
the durable lifecycle changes to `paused` and the UI reports the rules
boundary. It does not strand the players behind an arbiter-only decision or
describe that state as repeated priority passing.

After a land is played, the engine stabilizes state-based actions and all
represented waiting triggers before returning priority. A targeted enters
trigger such as Sunscorched Desert therefore opens its target choice
immediately in the same main phase; it cannot remain queued while another
spell is cast or while the game advances toward combat.

Game Records pin the semantic registry and policy that created them. Restarting
the current server does not silently retrofit newer card behavior into an old
record because that would break exact replay. If a pre-boundary record already
contains an arbiter-only decision, the browser adapter now converts it to a
durable `browser_rules_boundary` pause and states that no player is passing
priority. Create a new room and game after restarting to test the current
trusted semantic pack.

That boundary is safer and more auditable than silently guessing at card text, while allowing semantic coverage to grow from cards actually encountered in simulations.

The same rule applies to costs. Ordinary printed costs and a conservative set of explicit activated costs are derived by the server. A pilot may choose an advertised ability and the physical cards that pay delegated costs, but it cannot submit an arbitrary cheaper `declared_cost`, invent a sacrifice, or claim that a graveyard card is castable. Alternate costs, restricted mana, and unusual zone permissions must be compiled before use rather than trusted from player input.

## Rules corpus and arbitrary decks

The rules-completeness program uses generic mechanics and a typed Oracle
compiler rather than one code branch per card. `simctl rules sync` now locates
the official Wizards TXT, preserves the raw file only in ignored local cache,
and commits compact CR/glossary/mechanics indexes with exact source hashes.
When supplied `--db`, it also pins the local Oracle and rulings bulk timestamps
and archive hashes.

```bash
python simctl.py rules sync \
  --root . \
  --db data/scryfall-current.sqlite3
python simctl.py rules verify --root .
python simctl.py rules coverage --root .
python simctl.py rules conformance --root .
python simctl.py rules queue --root .
python simctl.py rules next --root . --limit 20
```

The pinned snapshot has a generated conformance inventory with separately
classified executable, blocked, definition-only, and unreviewed records. A
generated inventory test cannot prove rules behavior. See the generated
[`coverage/rules-conformance.md`](coverage/rules-conformance.md) for current
figures and `RULE_CONFORMANCE.md` for promotion, invalidation, and reporting
policy.

The generated machine-readable dependency queue groups every reviewed blocked
behavioral rule and every still-unclassified nonpassing rule into coupled
subsystems. It records rule and subsystem dependencies, current implementation
and test evidence, active profiles, compiler impact, and one explicitly
selected next batch. `rules next` reads that selection; it no longer acts as a
numerical rules walk when the generated queue is present. See
[`docs/RULES_DEPENDENCY_QUEUE.md`](docs/RULES_DEPENDENCY_QUEUE.md).

Deck creation now invokes the typed Oracle compiler automatically. Exact
whole-text templates lower into the generic effect DSL without a printed-name
branch, but generated programs stay provisional and arbiter-gated while any
mechanic dependency is untrusted. Unknown suffixes, costs, triggers,
replacement effects, or static text remain material residuals.

The generic zone kernel now distinguishes a stable physical card identifier
from its logical incarnation. Every ordinary zone change, including a draw or
a cast, advances an authoritative incarnation counter; same-zone moves through
exile or the command zone do as well. CR 400.7a is explicit: a permanent spell
keeps its logical incarnation when it becomes a permanent, while receiving a
new battlefield timestamp. Targets and implemented linked delayed effects
retain the selected incarnation, so a card that leaves and returns is not
silently treated as the old object. Pilot projections never expose the
physical identifier or incarnation counter.

CR 400 review also enforces three generic boundaries before mutation:
same-zone graveyard moves cannot reorder that graveyard, instant and sorcery
cards cannot be moved onto the battlefield, and moving a hidden card outside
the game does not reveal it. Face-down objects in otherwise public zones remain
visible only to their owner or another explicitly authorized viewer. Complete
special-object command-zone rules, the remaining new-object exceptions,
sideboards and wish effects, and generic whole-zone instructions remain
fail-closed or explicitly blocked.

The library kernel keeps the top at the end of one authoritative per-player
list while projecting only a public count and a contiguous, explicitly known
top group. `look_top` rejects negative or malformed counts and treats zero as
an empty look; `reorder_top` validates the exact current known group before
mutation. Moving a card to a positive Nth-from-top position is generic, with CR
401.7's bottom fallback for short libraries, and repositioning within the same
library preserves logical identity. Continuous top-card permissions and the
simultaneous multi-card owner-order choice remain explicit blockers.

Each new zone incarnation also receives a serialized timestamp moment.
Objects entering a destination simultaneously share that moment. Battlefield
objects separately retain when they most recently gained the World supertype,
allowing the CR 704.5k world rule to keep the unique newest World permanent or
move every World permanent when the newest duration is tied. These
authoritative timestamps are also omitted from pilot projections. Full CR
613.7m APNAP relative-timestamp choices remain outside this reviewed slice.

Tokens now reach their first nonbattlefield destination, generate the
appropriate zone-change events, and cease to exist only at the next
state-based-action check. A token that has left the battlefield cannot move
again. Spell and card copies now use serialized noncard objects. A spell copy
outside the stack, or a card copy outside the stack or battlefield, reaches
that invalid destination before CR 704.5e makes it cease. A copied permanent
spell becomes that same object as a token permanent and does not emit a token
creation event. This is a reviewed partial CR 111/400/704/707 slice, not
complete copiable-value, card-copy casting, Prepare, merged-permanent, meld,
sticker, face-down, or linked-ability support.

The same immutable CR 704 snapshot enforces the reviewed maximum-counter
sentence family exemplified by Rasputin Dreamweaver. It derives the counter
kind and numeric maximum from effective Oracle text rather than a card-name
branch, and combines overlapping maximum and opposing +1/+1/-1/-1 removals
without double-removing the same indistinguishable counters.

Battle support is likewise type-driven rather than card-name-driven. A Battle
entering the battlefield initializes defense counters from its derived
copiable defense characteristic; damage removes defense, and the state-action
snapshot distinguishes a zero-defense Battle whose exact-incarnation trigger
is still pending. For the pinned rules snapshot, Sieges choose an opponent as
protector while the spell resolves, may be attacked by every other player,
and route blockers to that protector. Invalid protectors are repaired through
a replayable controller choice.

This is a partial CR 120/210/310/704 implementation. Removing a Siege's last
defense counter queues the intrinsic trigger. Native resolution follows the
exact source incarnation, exiles it, and offers its controller a replayable
choice to cast the transformed face without paying its mana cost or decline.
Tokens cease after exile, and ordinary casts cannot select a transforming
card's back face. Compiled target schemas are exposed when a transformed
instant or sorcery needs targets; unresolved target or cost grammar fails
closed rather than advertising an illegal cast. Complete exile-replacement
ordering remains blocked. Unknown future Battle subtypes and nonspell entries
that require an unrepresented as-enters choice also fail closed. In
particular, the two Control Point previews in the July 28 Oracle corpus
postdate the June 19 pinned rules and are not silently treated as Sieges.

```bash
python simctl.py card compile "Lightning Bolt" \
  --db data/scryfall-current.sqlite3 \
  --output snapshots/lightning-bolt.card-program.json
python simctl.py card explain "Lightning Bolt" \
  --db data/scryfall-current.sqlite3
python simctl.py card audit "Rest in Peace" \
  --db data/scryfall-current.sqlite3
python simctl.py card diff "Lightning Bolt" \
  --against snapshots/lightning-bolt.card-program.json \
  --db data/scryfall-current.sqlite3
python simctl.py card overrides --db data/scryfall-current.sqlite3
python simctl.py card coverage --limit 100 \
  --db data/scryfall-current.sqlite3
python simctl.py card trust-closure "Lightning Bolt" \
  --profile commander_duel --db data/scryfall-current.sqlite3
python simctl.py card runtime-components \
  --profile commander_review --db data/scryfall-current.sqlite3

# Lower-level Oracle IR compatibility diagnostics remain available.
python simctl.py oracle parse "Lightning Bolt" \
  --db data/scryfall-current.sqlite3
python simctl.py oracle explain "Rest in Peace" \
  --db data/scryfall-current.sqlite3
python simctl.py oracle coverage \
  --db data/scryfall-current.sqlite3
```

CardProgram V2 is the canonical deterministic runtime artifact. It combines
generated Oracle IR and reviewed semantic-pack abilities under stable card,
face, and ability identities; records source spans, typed costs/targets/effect
families, residuals, capabilities, trust closure, and exact fingerprints; and
fails closed on stale or inconsistent sources. Semantic pack v3 remains a
compatibility input, not a second rules authority. New Game Record v3 files pin
the complete card-program map and the subset used by every command while
remaining replay-compatible with older v3 records.

The typed semantic-handler migration moved its first executable effect
families into `mtg_commander_sim/semantic_runtime/`. Registered handlers receive only an
immutable seat/order query, produce typed intents, and declare bounded rule
capabilities. The executor reuses canonical engine mutation methods. Draw,
table-wide draw, and monarch designation are the first migrated operations;
ordinary CardProgram stack resolution now reaches those handlers, and draw
intents retain the existing replacement-aware draw sequence. All other
operations remain explicitly on the measured legacy path. This is an
architecture milestone, not a broader rules-completeness claim.

The runtime-component migration moves bounded card-specific core debt into
versioned CardProgram data. Reviewed fixed additional-token replacements now
participate in an immutable nested replacement-event tree with affected-seat
choice, APNAP traversal, rediscovery, containing-event-first ordering, and an
exact replay journal. A focused token-creation owner commits the final batch.
A reviewed zone-destination component uses the same boundary; Dauthi
Voidwalker is source-pinned semantic data rather than an Oracle-ID engine
branch. The fixed subtype anthem remains a layer-7c modifier whose applicability
is evaluated after earlier layers. Effect-generated permanent counters now use
a focused transactional owner with a fixed quantity-replacement component.
Represented combat, semantic, and mana-result damage use one typed transaction
with fixed quantity replacement and fixed prevention components. Final dealt
components now become immutable affected-subject result trees before atomic
mutation. Generic effective-keyword dispatch covers represented Infect,
Wither, Lifelink, and fixed Toxic outcomes. Damage source snapshots preserve
represented keyword LKI across zone and control changes, and canonical typed
life/counter owners validate the whole result batch before mutation. Stable
physical commander designations—not Oracle IDs—own Commander-damage ledgers.
The replacement model is split into deep-immutable model, applicability, typed
operation, ordering, and strict replay modules. Generic compilation now covers
those four keywords plus a closed family of static double-damage and fixed-
prevention wording. Oracle IR v16 also lowers closed finite-shield wording,
dynamic resolved quantities, exact divided allocations, independent per-object
shields, represented immediately-after life/counter results, and static
redirection to a current damageable source. Durable modifier creation and life
effects now have focused runtime owners outside `CommanderEngine`; the effect
runtime has six closed operation families. Simultaneous finite allocation is
seat-scoped and replayable, same-chooser event order is explicit,
unpreventable damage does not consume a shield, and positive prevention
dispatches one aggregate event per effect. Public battlefield, stack, and
face-up command-zone sources can be chosen through a seat-scoped continuation
whose physical identity and LKI are pinned. Replacement choices discovered
during mana payment roll the payment back and resume the exact cast or
activation after the choice. Bounded handlers cover fixed life-gain
multiplication, a whole-result life floor, and transactional CR 615.5
life/permanent-counter aftermath. Complete CR 609.7a source categories and
permanent-spell continuity, broader source-property predicates, general
replacement-capable life gain, remaining aftermath wording, partial or
attached redirection, non-damage transformations, unresolved dynamic Toxic
values, remaining result-replacement families, universal draw/entry
replacement participation, broad CR 614/615/616 closure, layer dependencies,
and state-derived modifiers remain unsupported.

Runtime trust and governance are now explicit. Capability registry v11 consumes
a generated evidence index whose fully qualified tests, current rules,
profiles, and evidence classes are validated in CI. Every trusted capability
requires positive, negative, replay, and killed-mutation evidence regardless of
an author's declaration, plus a resolvable component and dependency checks.
CardPrograms report one trust
basis plus intrinsic, format, match, and dynamic closure; reviewed semantic
packs remain an identified compatibility path rather than being described as
capability-closed. Strict binding includes registered handler/component
dependencies and exact registry/evidence fingerprints.

The complete Commander format-capability inventory is not yet present, so
capability-only strict match readiness fails closed while reviewed declared-pool
compatibility remains available. The dependency scheduler is integrated; the
generated dependency queue, rather than a hand-written branch chronology,
states the next reviewed batch.
Broad rules or Oracle expansion does not bypass these typed boundaries.

This is still not a completeness declaration. Current exact, partial,
unresolved, and material-residual figures are generated in
[`docs/COMPILER_COVERAGE_STATUS.md`](docs/COMPILER_COVERAGE_STATUS.md). Every
material residual must be eliminated or covered by a reviewed, hash-pinned
override before complete Oracle support can be claimed. Genuinely unique cards
may use reviewed overrides; common cards and mechanics compile through reusable
primitives. See `RULES_COMPLETENESS.md` and `ORACLE_IR.md`.

## Quick Python loop

```python
from pathlib import Path

from mtg_commander_sim import CardDatabase, CommanderSession, DeckLoader

root = Path(".")
db = CardDatabase("data/scryfall-20260728-compact.sqlite3")
loader = DeckLoader(db)

mishra = loader.load(
    root / "examples/mishra-eminent-one.txt",
    commander="Mishra, Eminent One",
)
zimone = loader.load(
    root / "examples/zimone-and-dina.txt",
    commander="Zimone and Dina",
)

session = CommanderSession.create(
    db,
    {"A": mishra, "B": zimone, "C": mishra, "D": zimone},
    first_player="A",
    seed=20260728,
    semantics_path="run/semantics.json",
)

while not session.state.game_over:
    packet = session.next_task()
    if packet is None:
        break

    principal = packet["principal"]
    # Route only this packet to the authenticated client assigned to the principal.
    response = your_client_decision(principal, packet)
    result = session.act(principal, response)
    if not result.ok:
        raise RuntimeError(result.summary)
```

Compact player responses:

```json
{"a":"keep"}
{"a":"p","y":"until_my_turn"}
{"a":"l","card":"A37"}
{"a":"c","card":"A12","targets":["S4"],"auto_pay":true}
{"a":"atk","attackers":{"T1":"B","T2":"D"}}
```

The preferred auditable form selects a server-generated action ID and includes
strategy metadata that is stripped before the command reaches the engine:

```json
{
  "action_id":"cast:A12",
  "reason":"Deploy graveyard interaction before the opponent can recur a target.",
  "plan":"HOLD_INTERACTION",
  "confidence":0.84
}
```

## Client-side projection reducer

A client receives one full projected state, then patches. It never needs access to the authoritative game object.

```python
from mtg_commander_sim import ProjectedClientView

view = ProjectedClientView("pilot:A")
view.ingest(full_packet)
view.ingest(delta_packet)

assert view.current_hash == delta_packet["view"]
current_projected_state = view.state
```

A bad base hash causes a resync error instead of silently corrupting client state.

## Command line

Create a persistent four-player game:

```bash
python simctl.py new \
  --db data/scryfall-20260728-compact.sqlite3 \
  --seat A=examples/mishra-eminent-one.txt \
  --seat B=examples/zimone-and-dina.txt \
  --seat C=examples/mishra-eminent-one.txt \
  --seat D=examples/zimone-and-dina.txt \
  --commander 'A=Mishra, Eminent One' \
  --commander 'B=Zimone and Dina' \
  --commander 'C=Mishra, Eminent One' \
  --commander 'D=Zimone and Dina' \
  --first A --seed 20260728 --out run
```

Create a 1v1 directly from two public Moxfield decks:

```bash
python simctl.py duel \
  --db data/scryfall-current.sqlite3 \
  --out run/duel --cache-dir run/deck-cache --refresh-decks \
  --profile commander_duel --trace-level standard \
  https://moxfield.com/decks/g5vtVfRuS0W5KxZuYqZHGQ \
  https://moxfield.com/decks/armNI_ntVUagNNygnUVyxQ
```

The import must declare Moxfield format `commander`, identify one or two
commanders, contain 100 cards, satisfy singleton checks, and stay within the
commander color identity. Successful live responses are cached for reproducible
reruns.

Moxfield metadata is authoritative for commander identity. At the time of this
release, `g5vtVfRuS0W5KxZuYqZHGQ` identifies the Zimone and Dina list and
`armNI_ntVUagNNygnUVyxQ` identifies the Mishra, Eminent One list. This is the
reverse of the labels in the original development brief, so the native fixture
uses the commanders and contents returned by Moxfield.

Preflight semantic coverage before a pilot run:

```bash
python simctl.py semantics preflight \
  https://moxfield.com/decks/g5vtVfRuS0W5KxZuYqZHGQ \
  --db data/scryfall-20260728-compact.sqlite3 \
  --cache-dir run/deck-cache \
  --output run/semantic-preflight-zimone.json
```

Run the seats through any mix of provider adapters:

```bash
python simctl.py pilot-run \
  --db data/scryfall-20260728-compact.sqlite3 \
  --profile commander_duel \
  --deck A=https://moxfield.com/decks/g5vtVfRuS0W5KxZuYqZHGQ \
  --deck B=https://moxfield.com/decks/armNI_ntVUagNNygnUVyxQ \
  --pilot A=manual \
  --pilot B=subprocess:"python my_pilot.py" \
  --output run/native-zimone-vs-mishra \
  --through-turn 8
```

`scripted` is the deterministic fixture provider. `manual` writes a compact
task under the run directory and reads one JSON response from stdin.
`subprocess:<command>` sends JSON on stdin and expects one JSON object on
stdout. A resumed `pilot-run` restores the checkpoint, projection cursors, and
each seat's private pilot memory.

Each save is a Game Record v3 directory rather than a monolithic `game.json`.
Inspect, migrate, verify, and review records with:

```bash
python simctl.py inspect-game run/duel --pretty
python simctl.py replay run/duel --db data/scryfall-current.sqlite3 --verify
python simctl.py report run/duel --db data/scryfall-current.sqlite3

python simctl.py migrate-record run/old/game.json \
  --output run/old-v3 --db data/scryfall-current.sqlite3
```

See `GAME_RECORD.md` for file semantics, trace levels, replay guarantees, and
the review fidelity gate.

See `PILOT_PROVIDERS.md` for provider contracts and isolation guarantees, and
`SEMANTIC_PACKS.md` for pack provenance, trust, preflight, and the deliberately
bounded 0.8.0 exact-list coverage. See `CODEX_ARENA.md` for the persistent four-pilot
workflow.

Create the default four-seat Codex arena:

```bash
python simctl.py arena-create \
  --db data/scryfall-20260728-compact.sqlite3 \
  --deck A=https://moxfield.com/decks/g5vtVfRuS0W5KxZuYqZHGQ \
  --deck B=https://moxfield.com/decks/armNI_ntVUagNNygnUVyxQ \
  --deck C=https://moxfield.com/decks/g5vtVfRuS0W5KxZuYqZHGQ \
  --deck D=https://moxfield.com/decks/armNI_ntVUagNNygnUVyxQ \
  --refresh-decks --output run/codex-arena
```

The Codex arena is an optional client-adapter experiment retained for protocol
characterization. It is not required for gameplay, tests, merge gates, release
gates, or rules decisions. If explicitly testing that adapter, use the generated
`PRIMARY_CODEX_PROMPT.md` and start four persistent pilot sessions with:

```bash
python simctl.py arena-codex-run \
  --db data/scryfall-20260728-compact.sqlite3 \
  --game run/codex-arena \
  --model gpt-5.6-sol \
  --reasoning-effort low \
  --service-tier priority \
  --through-turn 8
```

Use `--through-turn 0` for a natural terminal game. This environment does not
expose GPT-5.5/Instant, so the fast profile records the actual GPT-5.6 Sol/low
identity. A fixed pilot MCP process remains available for manual orchestration:

```bash
python simctl.py pilot-mcp --game-dir run/codex-arena --seat A
```

The primary reads only public routing/fidelity data and scoped arbiter tasks:

```bash
python simctl.py coordinator-tool --game run/codex-arena status
python simctl.py coordinator-tool --game run/codex-arena get-arbiter-task
```

Pause, resume, inspect, or finalize without confusing an accepted-command
prefix with a completed game:

```bash
python simctl.py arena status run/codex-arena --db data/scryfall-current.sqlite3
python simctl.py arena pause run/codex-arena --db data/scryfall-current.sqlite3 \
  --kind fidelity_failure --reason "target exactness requires code work"
python simctl.py arena resume run/codex-arena --db data/scryfall-current.sqlite3
python simctl.py arena abort run/codex-arena --db data/scryfall-current.sqlite3 \
  --reason "operator requested"
python simctl.py arena finalize run/codex-arena --db data/scryfall-current.sqlite3
python simctl.py verify-record run/codex-arena --db data/scryfall-current.sqlite3
```

Read the next scoped task:

```bash
python simctl.py task \
  --db data/scryfall-20260728-compact.sqlite3 \
  --game run --pretty
```

Submit a response:

```bash
python simctl.py act \
  --db data/scryfall-20260728-compact.sqlite3 \
  --game run --principal pilot:A \
  --json '{"a":"keep"}'
```

Read local Oracle text and rulings:

```bash
python simctl.py rules \
  --db data/scryfall-20260728-compact.sqlite3 \
  --game run 'Mishra, Eminent One' 'Gonti’s Aether Heart'
```

## Strict hidden information

Every connection receives only its authenticated principal's projection. A
browser process, scripted client, subprocess, or optional AI client must never
read an authoritative checkpoint or another seat's packet.

For optional multi-client automation, use one fixed-seat context per client
against one `GameService`. Projected packets, server-derived principal identity,
and exact-ref rules lookup preserve protocol-level isolation.

Client instructions are not an operating-system sandbox. The capability,
projection, and transport boundaries enforce game authority; use process or
container isolation when filesystem-level isolation must also be proven.

## Project map

- `mtg_commander_sim/engine.py` — authoritative rules/state kernel
- `mtg_commander_sim/model.py` — serializable state model
- `mtg_commander_sim/permissions.py` — one-use capability authorization
- `mtg_commander_sim/projection.py` — hidden-information projection and packet generation
- `mtg_commander_sim/protocol.py` — protocol version, state hashing, JSON patch generation/application
- `mtg_commander_sim/client.py` — reference projected-state reducer
- `mtg_commander_sim/semantics.py` — reusable effect-program registry
- `mtg_commander_sim/card_programs/` — canonical CardProgram V2 model,
  semantic/generated adapters, audit commands, and runtime validation
- `mtg_commander_sim/semantic_runtime/` — frozen typed effect/runtime-handler
  registries, immutable rules queries, typed intents, and canonical execution
- `mtg_commander_sim/mana.py` — conservative mana source parsing/planning
- `mtg_commander_sim/abilities.py` — explicit Oracle ability/cost extraction and zone authorization
- `mtg_commander_sim/rules/action_proposals.py` — immutable canonical action
  offers and proposal fingerprints
- `mtg_commander_sim/rules/action_catalog.py` — principal-scoped executable
  land, cast, and activation offer composition
- `mtg_commander_sim/rules/casting/` — casting cost/proposal queries and typed
  commit ownership
- `mtg_commander_sim/rules/activation/` — activated-ability query,
  availability, proposal, resolution, and commit ownership
- `mtg_commander_sim/session.py` — deterministic session façade
- `mtg_commander_sim/service.py` — transport-neutral application boundary
- `mtg_commander_sim/pilot.py` — optional automation-client orchestration and metrics
- `mtg_commander_sim/profiles.py` — fingerprinted advisory deck profiles
- `mtg_commander_sim/preflight.py` — trust-aware deck semantic coverage
- `mtg_commander_sim/shortcuts.py` — validated aggregate loop fixtures
- `mtg_commander_sim/state_based_actions.py` — snapshot-based CR 704
  permanent-action and token-cessation evaluation
- `mtg_commander_sim/counter_placement.py` — represented permanent-counter
  proposal, replacement, and commit owner
- `mtg_commander_sim/damage.py` — represented damage proposal,
  quantity replacement/prevention coordinator and final-event publisher
- `mtg_commander_sim/damage_results.py` — immutable CR 120.3 result trees,
  replacement preparation, commit planning, and atomic result mutation
- `mtg_commander_sim/record.py` — Game Record v3 hashing, journals, migration, inspection, and replay
- `mtg_commander_sim/report.py` — derived review and fidelity classification
- `mtg_commander_sim/carddb.py` — local Oracle/rulings database
- `mtg_commander_sim/deck.py` — deck loading and validation
- `schemas/` — versioned client-facing JSON schemas
- `scripts/` — data bootstrap and protocol smoke/benchmark tools
- `tests/` — multiplayer, permission, rules, and token-efficiency regression tests
- `.github/workflows/` — offline merge-gating CI and manual live integration
- `REPOSITORY_HYGIENE.md` — tracked-artifact and history policy
- `SECURITY.md` — private vulnerability reporting and hidden-information scope

Read `ARCHITECTURE.md`, `LLM_PROTOCOL.md`, `PILOT_PROVIDERS.md`,
`SEMANTIC_PACKS.md`, and `CLIENT_INTEGRATION.md` before extending the engine.

No software license has been selected for this public repository. Public
visibility does not itself grant redistribution or relicensing rights.
