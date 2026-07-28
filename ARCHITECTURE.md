# Architecture

## Objective

Run repeatable four-player Commander games in which independent LLM pilots maximize their own chance to win while:

- authoritative state remains deterministic and auditable
- private information is limited to the correct seat
- rules interpretation is separate from strategic play
- model calls occur only at meaningful decisions
- a future native/web MTG client can reuse the same command and permission model

The key decision is to stop treating one ChatGPT context as the player, judge, state store, and client simultaneously.

## Layered design

```text
┌──────────────────────────────────────────────────────────────┐
│ Pilot contexts A / B / C / D             Rules arbiter      │
│ strategic choices only                    semantics only      │
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
│ cached generic effect DSL   │  │ Oracle cards + rulings      │
└─────────────────────────────┘  └─────────────────────────────┘
            │
            ▼
┌──────────────────────────────────────────────────────────────┐
│ StateProjector                                               │
│ principal-specific state + definitions + events + decision    │
└───────────────┬──────────────────────────────────────────────┘
                ▼
┌──────────────────────────────────────────────────────────────┐
│ Protocol 2.1 / ProjectedClientView                           │
│ bootstrap, hash-checked JSON patches, resync boundary         │
└──────────────────────────────────────────────────────────────┘
```

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

## Roles and permissions

| Principal | Default visibility | May decide | Direct state mutation |
|---|---|---|---|
| `pilot:A`–`pilot:F` | own private zones, known cards, public state | legal actions/choices for that seat | never |
| `arbiter` | public state plus resolving-object context | generic effect program, rule-counter/fizzle | only through resolution capability |
| `analyst` | complete read-only state | none | never |
| `spectator` | public state | none | never |
| server/admin process | persistence and lifecycle | administrative operations | not through pilot API |

A capability token is:

- opaque
- one use
- tied to one game decision
- tied to one authenticated principal
- limited to named actions
- invalidated when the decision closes

A player cannot forge `draw`, `damage`, `move`, `create_token`, or other effects. It can only choose a permitted game action such as cast, activate, attack, block, pass, make a delegated choice, or concede.

The same least-authority rule applies to action costs. Priority packets advertise stable explicit ability IDs and objective cost requirements. A pilot may select the physical creature to sacrifice or card to discard when the Oracle cost delegates that choice, but it cannot provide arbitrary cost effects, understate a printed mana cost, or authorize a cast from another zone. Uncompiled alternate costs and zone permissions fail closed until the rules/cost layer registers them.

Capabilities are **decision authorization**, not login credentials. A future server must authenticate the connection first, derive the principal, and then validate the capability.

## Decision lifecycle

1. The kernel reaches a point requiring external judgment.
2. It creates a `DecisionGroup` and one capability for each required actor.
3. Each principal receives its own projected packet.
4. Responses arrive sequentially or as a multi-actor group, depending on the rule.
5. Principal, token, decision ID, action, and actor scope are validated.
6. The command is committed transactionally.
7. Deterministic transitions run until the next genuine decision.

If a model action is illegal, the transaction rolls back and the capability remains live. `SequentialPilotRunner` may retry a bounded number of times with a compact rejection message rather than resending a full state or silently repairing the move.

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

Before issuing a priority capability, the kernel checks the implemented action grammar. If the seat has no castable-by-timing card, land play, or nonmana activated ability, the priority pass is deterministic and no model is called.

This can be disabled for debugging or when a future client adds special actions not yet represented by the kernel.

Yield policies allow a pilot to skip additional windows until:

- its own turn
- a public change
- a known response becomes possible

The yield is invalidated conservatively by stack changes, visible zone changes, and relevant private draws.

## Rules arbitration and semantic programs

The engine should not infer arbitrary card behavior from prose during a state transition.

When the top stack object lacks registered semantics:

1. the kernel creates an `arbiter.resolve` capability
2. the arbiter receives public state, the resolving object, targets, modes, X, and local card text
3. the arbiter returns generic DSL effects or a rule-fizzle/counter decision
4. stable semantics may be registered under an Oracle/ability key
5. future occurrences resolve without another rules call

Generic operations include draw, move, sacrifice, destroy, exile, bounce, discard, tap/untap, damage, counter, search, mill, token creation, copy, attachment, control change, delayed trigger scheduling, and player choice delegation.

Runtime placeholders such as `$controller`, `$source`, `$stack`, and `$target.0` prevent semantics from hard-coding physical game object IDs.

## Protocol and client-state updates

Protocol 2.1 separates durable projected state from delivery metadata.

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

## Durable Game Record v3

Durable state and audit history are intentionally separate:

```text
initial-checkpoint.json.gz ── accepted commands ──> checkpoint.json
                                  │
                                  ├── commands.jsonl  (replay truth)
                                  ├── decisions.jsonl (strategy/model audit)
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

Review is derived rather than authoritative. Its fidelity gate prevents a
rules-incomplete smoke run from silently becoming deck-performance evidence.

## Token minimization

### Bootstrap once, patch thereafter

The bundled benchmark measures approximately:

- 1,786 tokens for the initial four-player A-seat projection
- 247 tokens for an unchanged repeated live decision
- 108 tokens after A declares a mulligan

### Stable short references

Actions use `A37`, `T4`, or `S2` instead of repeating names and descriptions. References remain stable for the physical game object throughout the game.

### Definitions only once

Newly visible Oracle cards are emitted under `defs` once per principal. State objects thereafter carry only `cid` and short visible fields.

### Filtered events

Untaps, pass bookkeeping, and mana clearing remain in server history but are normally omitted. Pilots see only new, visible, strategically relevant events.

### Deterministic automation

The kernel handles shuffling, drawing, turn-based actions, state-based actions, ordinary mana payment, empty priority, turn progression, and registered semantics without a model call.

### Separate strategy and rules contexts

Pilots do not spend tokens restating card behavior. The arbiter does not receive unrelated private hands. Analysts receive complete data only after or outside live strategic decisions.

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
| player supplied arbitrary effects | only arbiter resolution capabilities accept DSL effects |
| mulligans chased ideal sevens | exact free-mulligan procedure plus configurable functional-hand guard |
| pilot asserted every land was tapped | engine derives entry state from Oracle conditions and live opponent/board state |
| fetchland cost/effect unresolved | sacrifice-this-land cost plus legal private search choices and built-in search/shuffle resolution |
| giant save mixed state, events, and credentials | Game Record v3 checkpoint and replay/audit journals; raw capabilities never persist |

## Remaining scope

The architecture is suitable for a serious project, but complete Magic coverage is incremental. Major future modules include:

- continuous-effect layers and dependencies
- replacement/prevention ordering
- complete alternate/additional cost grammar and restricted-mana predicates
- all special actions and zone-based casting permissions
- copy, face-down, linked-ability, and characteristic edge cases
- first/double-strike damage substeps and complete assignment validation
- multiplayer shortcut and deterministic loop negotiation
- generated semantic coverage for the full Oracle corpus
- durable database persistence, authentication, and WebSocket delivery

These modules fit behind the current `CommanderEngine`/`GameService` boundary. They do not require granting pilots broader permissions or replacing the command protocol.
