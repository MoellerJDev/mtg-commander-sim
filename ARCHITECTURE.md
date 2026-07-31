# Architecture

## Objective

Host complete four-player Commander games in which independent human or
automated clients act through a central authoritative server while:

- authoritative state remains deterministic and auditable
- private information is limited to the correct seat
- rules interpretation is separate from strategic play
- clients are contacted only at meaningful decisions
- browser, native, scripted, and optional AI clients reuse one command and
  permission model

The key decision is to keep clients untrusted and make the server the sole
state and rules authority.

Current implementation boundary: `CommanderEngine`, strict `GameService`,
capability checks, projection, replay, and protocol 3.0 sit below a working
FastAPI adapter. `GameManager` owns one serialized `GameActor` per active game;
SQLite stores the guest/room/seat/deck/game/idempotency control plane while
Game Record v3 remains authoritative game persistence. A React/TypeScript
client consumes per-connection seat projections over WebSocket. This is a
single-node development vertical slice, not yet the complete choice UI or a
multi-process production deployment.

## Layered design

```text
┌──────────────────────────────────────────────────────────────┐
│ Browser / scripted / manual / subprocess / optional AI clients│
│ one authenticated principal and projected view per connection │
└───────────────┬──────────────────────────────────┬───────────┘
                │ compact action + capability      │
                ▼                                  ▼
┌──────────────────────────────────────────────────────────────┐
│ Transport adapter: in-process / CLI / HTTP / WebSocket       │
│ authenticates principal; never grants state mutation access   │
└───────────────┬──────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────┐
│ GameService + CapabilityManager                              │
│ one-use authorization scoped to decision, role, and actor     │
└───────────────┬──────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────┐
│ Authoritative CommanderEngine                               │
│ zones, turn queue, priority, costs, combat, SBA, choices      │
└───────────┬───────────────────────────────┬──────────────────┘
            │                               │
            ▼                               ▼
┌─────────────────────────────┐  ┌─────────────────────────────┐
│ SemanticRegistry            │  │ Local CardDatabase          │
│ trusted/provisional packs   │  │ Oracle cards + rulings      │
└─────────────────────────────┘  └─────────────────────────────┘
            │
            ▼
┌──────────────────────────────────────────────────────────────┐
│ StateProjector                                               │
│ principal-specific state + definitions + events + decision    │
└───────────────┬──────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────┐
│ Protocol 3.0 / ProjectedClientView / browser reducer         │
│ bootstrap, hash-checked JSON patches, resync boundary         │
└──────────────────────────────────────────────────────────────┘
```

`SequentialPilotRunner` is an optional automation adapter, not a source of rules.
Each `PilotProvider` receives only the packet already projected for its
principal, the current decision, and that principal's private `PilotMemory`.
The runner validates the compact response, records actual provider metadata,
and submits it through `CommanderSession` and `GameService`. Browser, scripted,
manual JSON, subprocess JSON, and future optional AI providers all use this
boundary.

Fingerprint-keyed deck profiles are advisory and loaded once into the matching
seat memory. They never enter `CommanderEngine`, determine legality, or replace
Oracle text. Profile and memory files are resumable pilot state, not
authoritative game state.

## Authoritative state versus projected state

`GameState` is server-only. It includes every physical object, hidden zone, turn queue, delayed trigger, capability, event, and knowledge marker.

A pilot/client sees only a projected view:

- its own hand
- public zones
- cards that seat legally knows
- public stack/combat state
- counts for hidden zones
- the live decision capability for that principal

The projection is not a mutable copy of the game. A client action returns to the service and is validated against authoritative state.

Elimination does not relax this boundary. A departed player's hidden hand,
library order, face-down identities, and private choices remain hidden from
other pilots. Publicly known objects remain visible, while the analyst can
inspect the preserved authoritative objects after the game.

## Roles and permissions

| Principal | Default visibility | May decide | Direct state mutation |
|---|---|---|---|
| `pilot:A`–`pilot:F` | own private zones, known cards, public state | legal actions/choices for that seat | never |
| `arbiter` | development-only public resolving context | characterize unsupported semantics | only through a scoped development capability; prohibited as production rules authority |
| `analyst` | complete read-only state | none | never |
| `spectator` | public state | none | never |
| server/admin process | persistence and lifecycle | administrative operations | not through pilot API |

Optional automation adapters may retain one isolated context per seat, but they
have no privileged action or state interface. Production strict rooms require
trusted compiled semantics and do not consult an arbiter or model for legality.

A capability token is:

- opaque
- one use
- tied to one game decision
- tied to one authenticated principal
- limited to named actions
- invalidated when the decision closes

A player cannot forge `draw`, `damage`, `move`, `create_token`, or other effects. It can only choose a permitted game action such as cast, activate, attack, block, pass, make a delegated choice, or concede.

The same least-authority rule applies to action costs. Priority packets advertise stable explicit ability IDs and objective cost requirements. A pilot may select the physical creature to sacrifice or card to discard when the Oracle cost delegates that choice, but it cannot provide arbitrary cost effects, understate a printed mana cost, or authorize a cast from another zone. Uncompiled alternate costs and zone permissions fail closed until the rules/cost layer registers them.

Capabilities are **decision authorization**, not login credentials. The server
first authenticates an expiring guest session, derives the principal from its
room seat, and only then validates the decision capability.

## Decision lifecycle

1. The kernel reaches a point requiring external judgment.
2. It creates a `DecisionGroup` and one capability for each required actor.
3. Each principal receives its own projected packet.
4. Responses arrive sequentially or as a multi-actor group, depending on the rule.
5. Principal, token, decision ID, action, and actor scope are validated.
6. The command is committed transactionally.
7. Deterministic transitions run until the next genuine decision.

If a client action is illegal, the transaction rolls back and the capability
remains live. An automation adapter may retry a bounded number of times with a
compact rejection message rather than resending a full state or silently
repairing the move.

Connections remain alive concurrently, but game decisions commit sequentially
because Magic grants one principal (or one ordered decision group) authority at
a time. The network gateway derives the principal from the authenticated room
seat and routes commands through the same `GameService` transaction boundary.

### Multiplayer mulligans

Mulligan declarations are issued in starting-player/turn order. Once every eligible player has declared, all players who chose to mulligan redraw seven. Counted bottom choices are private and collected as one multi-actor decision before being applied. A player who keeps is removed from future rounds.

The `realistic_mulligan_guard` is a simulation policy, not a Magic rule. It prevents an LLM from repeatedly hunting for a perfect seven after the free mulligan unless it states why the smaller hand is strategically preferable.

## Four-player turn and priority model

- normal turns follow the live turn order
- extra turns use a most-recent-created-first queue
- active player receives priority first where the rules provide priority
- passing advances to each remaining player in turn order
- all-pass resolves the top stack object or ends the step/phase
- players who leave are removed from priority, combat, choices, and future turns
- a game continues until one active player remains or another win condition applies

### Call suppression

Before issuing a priority capability, the kernel computes a versioned canonical
meaningful-action signature from currently payable land, cast, commander,
nonmana ability, interaction, combat, and player-choice alternatives. A
pass-only window is deterministic and no model is called.

A yield is only an optimization. It cannot authorize skipping a changed
signature. Yields are re-evaluated after every draw and phase/step transition
and expire on:

- the seat becoming active or reaching either of its main phases
- private hand additions/removals
- untap or land-play allowance changes
- newly payable casts, abilities, targets, attacks, blocks, or choices
- stack or relevant public battlefield changes
- the explicit stop condition

`until_public_change` is primarily a nonactive response optimization.
`until_my_turn` ends no later than that seat's next untap. An active player's
upkeep/draw yield never covers its next main phase.

Every priority state enters the authoritative opportunity journal with its
signature hash and one disposition: pilot task, safe yield, pass-only
auto-pass, ordered plan, or incorrect suppression. A nonzero
`suppressed_meaningful_windows` fails fidelity and caps classification at
`rules_test`.

## Versioned rules and Oracle compilation

Rules completeness is a separate, fail-closed pipeline above the existing
kernel:

```text
Official CR TXT ─┐
Oracle bulk ─────┼─> snapshot hashes -> mechanics contracts -> typed Oracle IR
Rulings bulk ────┘                                      │
                                                        ▼
                                       generic engine primitives + DSL
```

`rules_corpus.py` discovers the official TXT only through allowlisted Wizards
HTTPS endpoints, parses numbered IDs/sections/glossary locally, and writes
compact derived indexes. The raw document remains ignored. The manifest pins
the CR, Oracle, and rulings inputs, while coverage remains false until reviewed
contracts and tests establish behavioral trust.

`rule_conformance.py` derives one stable case from every indexed rule ID. Its
generated unittest surface checks only source linkage. Semantic status is a
separate reviewed field: passing requires an implementation component, real
test IDs, declared scenarios, and complete scenario coverage. Regeneration
preserves review only for an unchanged source and rule-text hash, so a rules
update cannot inherit stale conformance. Missing or duplicate cases fail
corpus verification.

The Oracle compiler preserves source spans and emits typed ability, cost,
target, trigger, replacement, and effect nodes. Oracle IR v2 lowers simple
self enters/dies/leaves triggers, unconditional enters-tapped text, fixed
self/target effects, and basic creature-token creation. Generated handlers
remain provisional, and reviewed trigger handlers shadow equivalent generated
events. A material residual prevents trusted preflight. Card-specific
overrides are a reviewed escape hatch for irreducible exceptions, not a
substitute for generic mechanics or a printed-name branch in
`CommanderEngine`.

CR 704 stabilization derives a public permanent snapshot before mutating
anything. `state_based_actions.py` classifies non-destruction graveyard moves,
destruction, unattachment, opposing-counter removal, and token cessation; the
engine applies the batch and rechecks before granting priority. Aura legality
reuses the declarative target domain without applying targeting-only shroud or
hexproof, while protection remains an attachment restriction. Unsupported
enchant quality grammar stays unresolved. The contract is partial until every
CR 704.5/704.6 variant and simultaneous loss/replacement interaction is
covered.

`CardInstance.object_id` is stable physical identity for a card container or
represented noncard object. `object_kind` distinguishes cards, tokens, spell
copies, card copies, and emblems. Its serialized
`zone_change_counter` identifies the current logical incarnation under CR
400.7. The canonical move path advances that counter for cross-zone moves and
same-zone exile/command moves, clears state that cannot survive, and preserves
only implemented entry continuations such as an as-enters choice. A permanent
spell keeps its incarnation as it becomes a permanent under CR 400.7a, while
still receiving a new battlefield timestamp. Target
snapshots compare the selected incarnation at resolution. Implemented linked
delayed moves carry an expected incarnation, preventing the same physical card
from leaving and returning to satisfy the old link. These authoritative values
are omitted from seat projections.

`CardInstance.zone_timestamp` records the serialized moment at which its
current zone incarnation began; a simultaneous destination batch shares one
moment. `world_supertype_timestamp` separately records when a battlefield
object most recently gained World, since losing and regaining that supertype
changes its CR 704.5k duration without changing zones. The fixed-point state
check synchronizes those values before taking its immutable snapshot. The
unique newest World permanent survives; a tie for newest moves every World
permanent simultaneously. The global sequence and both object timestamps are
authoritative replay state but remain absent from seat projections.

A token leaving the battlefield first exists in the destination long enough
for the move and its triggers to be observed. The next shared SBA snapshot
causes it to cease without a second zone-change event, and CR 111.8 prevents a
later move. Spell and card copies likewise have serialized noncard
representations. A spell copy outside the stack and a card copy outside the
stack or battlefield cease in the shared CR 704.5e snapshot. A permanent-spell
copy becomes the same object as a token permanent on resolution; it is not a
newly created token.

Emblems use a separate serialized noncard object kind. Generic creation puts
the object in its owner's public command-zone presentation, records only the
abilities supplied by the creating effect as characteristics, and makes the
receiving player both owner and controller. The projected display label is UI
metadata rather than an emblem name characteristic. Represented emblem
triggers retain the exact command-object source, while legacy Daretti
checkpoints that stored only a count remain readable. Arbitrary emblem ability
compilation and non-Commander casual-variant command objects remain blocked.

## Rules arbitration and semantic programs

The engine must not infer arbitrary card behavior from prose during a state
transition. Strict production games execute only trusted compiled semantics.

### Exact target plans

Version 0.7.0 compiles target requirements into declarative plans before an
action is exposed. A plan contains one or more structural groups with public
candidate sets, minimum/maximum counts, distinctness and cross-group
constraints, controller/owner relationships, zone and characteristic filters,
and optional mode-specific schemas. Candidate sets remain compact; the engine
does not enumerate every target tuple.

The same plan is validated when the command is submitted and again when the
object resolves. Legal surviving targets resolve independently. If every
selected target is illegal, the spell or ability is countered by the rules;
this is recorded separately from an effect that counters it. Trigger targets
are chosen as the trigger is put on the stack, before response priority.
Hidden zones are never accepted by this public target-query path, and face-down
objects contribute only characteristics visible to the querying seat.

Legal-action telemetry records candidates generated, actions removed for
missing targets or failed modal targets, rejected submissions, targets that
became illegal, rules/effect counters, and stack-interaction windows. Any
advertised mandatory-target action lacking legal targets fails
`legal_action_exposure` and the record fidelity gate.

Version 0.8.0 extends the same data-driven boundary through the two pinned
100-card review lists. The resulting exact-list preflight is 100/100 for both
lists, including linked choices, alternate costs, restricted mana, replacement
and delayed effects, copy/token engines, and the remaining exact Mishra
artifact families. This is a closed reviewed slice behind `CommanderEngine`,
not a claim that arbitrary Oracle text or the complete layer system is solved.

In development mode only, when the top stack object lacks registered semantics:

1. the kernel creates an `arbiter.resolve` capability
2. the arbiter receives public state, the resolving object, targets, modes, X, and local card text
3. the arbiter returns generic DSL effects or a rule-fizzle/counter decision
4. stable semantics may be registered under an Oracle/ability key
5. future occurrences may be characterized after review

This development path never counts as a production rule decision, conformance
evidence, or release evidence. Under `semantic_policy=trusted_only`, the engine
fails closed before an unsupported material behavior can mutate state.

Generic operations include draw, move, sacrifice, destroy, exile, bounce, discard, tap/untap, damage, counter, search, mill, token creation, copy, attachment, control change, delayed trigger scheduling, and player choice delegation.

Runtime placeholders such as `$controller`, `$source`, `$stack`, and `$target.0` prevent semantics from hard-coding physical game object IDs.

Version 0.6.0 makes `search` a resumable semantic operation. Resolution stores
a versioned `semantic_frame` on the stack object (program/version, instruction
pointer, controller, locals, and pending choice). The searching seat alone
receives filtered private candidates. After its scoped choice, the engine
validates the frame, performs reveal/destination/shuffle/entry handling, and
continues at the next instruction. Public events do not reveal a nonrevealed
card moved to hand. Restrictive or optional hidden-zone searches permit
fail-to-find; an unrestricted mandatory search does not.

### Pack trust and provenance

Version 0.6.0 loads semantic packs as data. A program identifies its Oracle ID,
ability/face, active zone, event, schema version, coverage, tests, source Oracle
hash, source-rulings hash, authoring provenance, review status, and trust level:

- `trusted`: reviewed behavior with deterministic characterization coverage
- `provisional`: usable for a pilot test but not trusted matchup evidence
- `unresolved`: known to require arbitration or further compilation
- `intentionally_ignored`: proven irrelevant in the scoped context

Only validated generic operations execute. Card-specific behavior is selected
by registry key; `CommanderEngine` does not branch on printed card names.
Preflight evaluates every deck entry conservatively and keeps review eligibility
false when relevant coverage is partial or unresolved.

The current vertical slice includes trusted execution for Zimone and Dina's
activation/second-draw trigger, Lotus Cobra landfall, Field of the Dead's
threshold, Warren Soultrader's activation, Mishra's Warform and delayed
sacrifice, Gonti's Aether Heart energy triggers, and Red Elemental Blast.
Several supporting cards are deliberately provisional. The preflight artifacts,
not this summary, are the definitive coverage inventory.

The generic tutor pack adds provisional reusable templates for Entomb, Three
Visits, Nature's Lore, Fabricate, Goblin Engineer's entry trigger, Survival of
the Fittest, Elvish Reclaimer, and Wight of the Reliquary. More complex tutors
remain explicit unresolved stubs. Provisional coverage permits a protocol
pilot test but never matchup evidence.

### Deterministic shortcuts

`shortcuts.py` accepts a named, demonstrated sequence of existing legal-action
IDs, an explicit repeat count/stop condition, and opponent priority responses.
It validates the required objects, zones, resources, and exact sequence before
applying an aggregate. The event records the loop signature, demonstrated
iteration, count, resource/life/zone delta, semantic versions, and responses.
The current implementations are intentionally limited to the tested
Soultrader/Gravecrawler/Zulaport line and Mishra/Gonti's Aether Heart energy
line; this is not a general shortcut-negotiation implementation.

## Protocol and client-state updates

Protocol 3.0 separates durable projected state from delivery metadata and adds
strict client command identity plus expected-view revision checks.

A full packet contains:

- `state`: the complete permitted projection
- `view`: a canonical content hash
- `decision`: current one-use capability
- newly visible card definitions
- important visible events

A delta packet contains:

- `base`: expected previous view hash
- `patch`: RFC-6902-compatible `add`, `remove`, and `replace` operations
- `view`: resulting hash
- repeated live decision or explicit `null`
- new definitions/events

`ProjectedClientView` is the reference reducer. If `base` does not match, the client requests a full packet. This prevents silent state drift and gives a native/web client a stable integration point without access to kernel internals.

## Network runtime and persistence

The `server` package is an adapter and may import the engine package; the
engine package is architecture-tested not to import FastAPI, Starlette,
Uvicorn, or `server`. Its request lifecycle is:

```text
guest cookie / bearer token
        │
        ▼
SQLite room seat ── derives pilot:A-D
        │
        ▼
strict CommandEnvelope ── expected revision + idempotency key
        │
        ▼
GameManager ── exactly one bounded GameActor mailbox per game
        │
        ▼
GameService ── capability/action/choice validation and rollback
        │
        ▼
Game Record v3 save ── SQLite idempotency commit ── receipt
```

Persistence failure in the ambiguous post-mutation window never returns a
success receipt. The actor fails closed and must be recreated from durable
state. A repeated identical `(game, principal, client_command_id)` returns the
stored receipt; the same key with different request content is rejected.

Projection cursors are scoped by connection rather than only by seat. This
allows reconnects and multiple tabs to receive independent deltas without
changing the authoritative seat capability. Network cursors are ephemeral and
excluded from Game Record persistence. A reconnect's full projection starts a
new delivery stream, so its packet number may restart at one; clients replace
the visible event tail from that full packet and enforce monotonic packet
numbers only for subsequent deltas.

The current SQLite ownership model is single-process. A multi-process or
horizontal deployment requires an external ownership/lease design before a
second process may host the same game.

## Durable Game Record v3

Durable state and audit history are intentionally separate:

```text
initial-checkpoint.json.gz ── accepted commands ──> checkpoint.json
                                  │
                                  ├── commands.jsonl  (replay truth)
                                  ├── decisions.jsonl (strategy/model audit)
                                  ├── opportunities.jsonl (priority coverage)
                                  └── events.jsonl    (normalized trace)
                                                        │
                                                        └── review.json / review.md
```

The authoritative hash excludes event presentation and capability credentials.
Every accepted external command stores before/after hashes and exact normalized
payload. Rejected attempts never enter the command journal. Loading a checkpoint
reissues capabilities for unanswered actors, so a disk artifact cannot be used
as a bearer credential.

The manifest pins engine, semantic registry, Scryfall metadata, decks, seed, and
the explicit Commander profile. Replay fails closed on a version/fingerprint or
transition hash mismatch. V2 migrations use a separately named snapshot-only
mode because their command payloads cannot be reconstructed.

Record lifecycle is explicit (`created`, `in_progress`, `paused`, `complete`,
`aborted`, `corrupt`). Saves replace journals/checkpoint atomically and write
the manifest last. A paused record verifies the accepted-command prefix and
retains its structured stop reason; prefix verification is not a terminal-game
claim. Provider counters and Codex thread/identity summaries are rebuilt from
durable decision and command rows, never incremented by convention.

Review is derived rather than authoritative. Its fidelity gate prevents a
rules-incomplete smoke run from silently becoming deck-performance evidence.

## Protocol and bandwidth efficiency

### Bootstrap once, patch thereafter

The refreshed bundled benchmark measures approximately:

- 1,549 tokens for the initial four-player A-seat projection
- 269 tokens for an unchanged repeated live decision
- 108 tokens after A declares a mulligan

### Stable short references

Actions use `A37`, `T4`, or `S2` instead of repeating names and descriptions. References remain stable for the physical game object throughout the game.

### Definitions only once

Newly visible Oracle cards are emitted under `defs` once per principal. State objects thereafter carry only `cid` and short visible fields.

### Filtered events

Untaps, pass bookkeeping, and mana clearing remain in server history but are normally omitted. Pilots see only new, visible, strategically relevant events.

### Deterministic automation

The kernel handles shuffling, drawing, turn-based actions, the implemented
snapshot-based state actions, ordinary mana payment, empty priority, turn
progression, and registered semantics without a model call.

### Separate client strategy and rules authority

Clients do not restate card behavior. The server derives legality from pinned
rules and semantic data. Analysts receive complete data only after or outside
live strategic decisions.

## Resolved failures from the duel prototype

| Earlier problem | New treatment |
|---|---|
| Extra turn recorded but not scheduled | dedicated LIFO extra-turn queue |
| Pact/Mishra delayed effects remembered manually | serializable step-triggered delayed actions |
| lethal damage/zero toughness/legend rule manual | automatic stabilization loop and delegated legend choice |
| conditional mana reported as unrestricted | conservative Oracle parser; conditional modes excluded from auto-pay |
| bad phase name advanced through future turns | `advance_until` validates target and fails closed |
| counterspell required manual stack correction | stable stack refs plus first-class counter operation |
| opponent sacrifice choice made by wrong actor | scoped AP/NAP delegated-choice capability |
| duel-only attacks | defender selected per attacker; blockers collected by defending player |
| top-of-library state unsupported | known-card metadata plus look/reorder operations |
| bond lands treated as duel lands | live opponent-count entry behavior |
| one context saw every hand | seat projections; strict mode uses isolated pilot contexts |
| repeated full state exhausted context | bootstrap + JSON patches + definitions cache + yields |
| every empty priority window called the model | known-empty windows auto-pass |
| beginning-step yield covered the active player's main phase | signature-based yield invalidation plus mandatory active/main/draw stops |
| review blamed a pilot that was never asked | engine-side opportunity journal attributes delivery, generator, semantics, and yield failures separately |
| unpayable Channel ability advertised | current mandatory-cost and mana-source payability gates |
| one stateless model call per action | four immutable seat-to-thread routes with reusable projected memory |
| player supplied arbitrary effects | only arbiter resolution capabilities accept DSL effects |
| mulligans chased ideal sevens | exact free-mulligan procedure plus configurable functional-hand guard |
| pilot asserted every land was tapped | engine derives entry state from Oracle conditions and live opponent/board state |
| fetchland cost/effect unresolved | sacrifice-this-land cost plus legal private search choices and built-in search/shuffle resolution |
| giant save mixed state, events, and credentials | Game Record v3 checkpoint and replay/audit journals; raw capabilities never persist |

## Generic rules compilation

Deck loading now compiles each unique pinned Oracle card into typed,
source-spanned IR before the engine is created. Reviewed semantic packs keep
priority on stable key collision. Newly lowerable programs record Oracle,
rulings, compiler, template, source-span, and semantic hashes, but remain
provisional and require the arbiter until all mechanic dependencies are
trusted. Material residuals are never discarded.

The new rules primitives sit below both generated and hand-authored semantics:

- `continuous_effects.py` orders CR 613 layers, sublayers, CDAs, timestamps,
  dependencies, and cycles. The engine already routes common copy/type/
  subtype/temporary-keyword annotations through it.
- `replacement_effects.py` orders CR 616 replacement/prevention priority
  classes, affected-player choices, optional declines, and repeated
  applicability for typed events.
- `state_based_actions.py` evaluates the deterministic permanent subset of CR
  704 plus token and represented spell/card-copy cessation from one immutable
  snapshot. The engine applies the resulting batch, captures last-known
  information before mutation, and repeats until stable. The reviewed subset
  includes CR 704.5e, the CR 704.5k world rule, CR 704.5r numeric
  maximum-counter abilities, CR 704.5v/w/x Battle checks, and serialized
  World-since timestamps.
- `CommanderEngine` derives Battle defense and protector behavior from the
  effective type line, subtype, and copied defense characteristic. Siege
  entry choices occur during resolution, attack/block routing uses the live
  protector, damage removes defense counters, and pending source triggers are
  matched to the exact logical incarnation. The intrinsic defeated trigger
  exiles that exact incarnation and uses a seat-scoped continuation for the
  optional transformed cast. Compiled target schemas are projected while
  unresolved mandatory target grammar fails closed.
- `CardInstance.object_kind` and the copy-object helpers represent stack spell
  copies and card copies without pretending they are cards. The reviewed
  partial CR 707 path preserves supported stack choices, treats spell copies
  as spell targets, and converts a resolving permanent-spell copy into the
  same token object.
- The emblem object kind and `CommanderEngine.create_emblem` represent public
  noncard, nonpermanent CR 408 command objects. Daretti's reviewed effect
  binds its trigger to the exact emblem source and command-replays, without
  implying generic emblem or casual-variant coverage.

All of these contracts remain partial. Legacy static abilities have not all moved
into the layer evaluator, not every zone/draw/damage/enters producer routes
through the replacement engine, and the state-action evaluator does not yet
cover Sagas, dungeons, Roles, speed, maximum-counter wording outside the
reviewed self-restriction family, or complete simultaneous loss replacement.
Battle support still lacks complete replacement ordering for the defeated
trigger's exile, transformed cast grammar beyond compiled cost/target schemas,
combat-removal interactions after type/control changes, and future subtype
predicates. CR 707 remains partial for complete
copiable values, card-copy casting/playing, Prepare, face-down and linked
interactions, and the full copied-choice/cost matrix. CR 400 object identity
also remains partial until its complete exception matrix and specialized
object forms use typed continuation policies. The serialized timestamp
moments are not yet consumed by every continuous-effect source, and complete
CR 613.7m APNAP relative ordering remains blocked. Coverage and contracts
describe those integration gaps explicitly.

## Remaining scope

The architecture is suitable for a serious project, but complete Magic coverage is incremental. Major future modules include:

- complete migration to continuous-effect layers, dependency discovery,
  player/game-rule effects, and APNAP timestamps
- replacement/prevention integration for every replaceable and nested event
- complete alternate/additional cost grammar and restricted-mana predicates
- all special actions and zone-based casting permissions
- copy, face-down, linked-ability, and characteristic edge cases
- first/double-strike damage substeps and complete assignment validation
- multiplayer shortcut and deterministic loop negotiation
- elimination or reviewed override of every material full-corpus Oracle
  residual
- single-writer game actors, durable database persistence, authentication, and
  WebSocket delivery
- browser rooms, seats, reconnect, spectators, generic decisions, and
  accessibility

These modules fit behind the current `CommanderEngine`/`GameService` boundary.
They do not require granting clients broader permissions, replacing the command
protocol, or introducing an AI rules authority.
