# MTG Commander Sim 0.8.0

An experimental, deterministic, server-authoritative Commander platform under
active development. Four-player Free-for-All Commander is the primary product
target, with a browser client, durable game runtime, exact replay, and
snapshot-scoped rules enforcement. The current release is a kernel and protocol
foundation, not a complete implementation of Magic's rules or Oracle corpus.

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

See `docs/PLATFORM_IMPLEMENTATION_STATUS.md` for the generated integration,
rules, server, browser, persistence, replay, privacy, and validation ledger.

## Local setup

Create an environment and install the source tree:

```bash
python -m venv .venv
. .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e . -r requirements-dev.txt
```

The repository deliberately does not contain a Scryfall bulk export or SQLite
database. CI builds a small database from the committed public exact-list
fixture:

```bash
python scripts/build_test_database.py build \
  --fixture tests/fixtures/scryfall-exact-lists.json \
  --output data/test-ci.sqlite3
MTG_CARD_DB=data/test-ci.sqlite3 \
  python -m unittest discover -s tests -p "test_*.py" -v
```

In PowerShell, set the variable with
`$env:MTG_CARD_DB = "data/test-ci.sqlite3"` before running the tests. The
compact fixture covers the bundled Zimone and Dina and Mishra, Eminent One
lists; it is not a substitute for the complete Oracle corpus.

For an exact-commit merge candidate, use the reusable gate after committing all
intended changes:

```powershell
py -3.11 scripts/local_merge_gate.py `
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
- protocol v2.1 bootstrap plus hash-checked JSON patches
- a reference client reducer that can be reused by a GUI, WebSocket client, or LLM runner
- bounded same-capability retry packets for invalid model actions, without a full-state resend
- Game Record v3 checkpoints plus command/event/decision journals
- deterministic command replay with per-transition state hashes
- explicit `commander_duel` and `commander_multiplayer` profiles
- server-derived land entry and built-in fetchland search resolution
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
- Oracle IR v2 simple self-trigger, unconditional-entry, counter, pump, and
  basic creature-token templates with reviewed-handler precedence
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
- source-reviewed CR 601 casting with executable mana-ability payment-window
  ordering, transactional rollback and cast-trigger witnesses; complete
  announcement ordering, choice/cost grammar, proposal-dependent permissions,
  and opponent-made casting choices remain blocked
- source-reviewed CR 600 section taxonomy linked to its dependent CR 601-609
  contracts without inventing standalone behavior for the heading
- source-reviewed CR 505 main-phase boundary: empty-stack pass completion,
  active-player priority, ordinary sorcery-speed casting, and stackless
  authoritative land plays use exact precombat/postcombat predicates; extra
  and skipped combats, ordinal main phases, Archenemy, Attractions, and
  complete simultaneous Saga handling remain blocked
- source-reviewed CR 504 draw-step ordering: the stackless turn-based draw or
  trusted replacement completes before state-based actions, one combined
  semantic/delayed trigger-order batch, and active-player priority; complete
  draw-replacement and draw-prevention semantics remain untrusted
- source-reviewed CR 506 combat-phase boundary: authoritative attacking and
  defending roles, durable combat history, and represented removal from
  combat after zone, control, phasing, or type changes; alternate multiplayer
  options, generic effect-created combatants, restriction snapshots, extra
  combats, and combat-relative timing grammar remain blocked
- source-reviewed CR 507 beginning-of-combat boundary: supported Commander
  profiles establish every active opponent as a defending player without a
  defender-choice task, coexisting permanent and delayed triggers are
  collected before active-player priority, and unsupported single-defender
  multiplayer variants fail closed
- source-reviewed CR 510 combat-damage assignment validation: the server
  derives sources, recipients, and exact power totals, rejects client-supplied
  semantics, and rolls illegal assignments back atomically; complex keyword
  and simultaneous-event dependencies remain blocked
- source-reviewed CR 508 ordinary attacker declaration: the server offers and
  revalidates only currently eligible creatures and live opponent/Battle
  destinations, preserves vigilance, rejects duplicate or phased submissions
  atomically, skips empty-combat blocker/damage steps, and command-replays the
  declaration; restrictions, requirements, costs, planeswalkers, attack
  triggers, entry-attacking, and target reselection remain blocked
- source-reviewed CR 509 ordinary blocker declaration: the server derives
  eligible blockers and defended attackers, rejects phased-out submissions,
  preserves blocking relationships through combat, and command-replays the
  declaration; requirements, costs, triggers, and entry-blocking remain blocked
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
- source-reviewed CR 602 activation handling with corrected untap-symbol
  summoning sickness and object-scoped once-per-turn restrictions; full cost
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
Zimone and Dina and Mishra, Eminent One lists: both exact 100-card lists report
100 fully playable cards and no partial or unresolved cards. The closure adds
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

For the bundled four-seat Mishra/Zimone benchmark:

| Packet | Compact characters | Approximate input tokens |
|---|---:|---:|
| Initial A-seat bootstrap | 6,197 | 1,549 |
| Same live decision, unchanged state | 1,076 | 269 |
| A mulligan declaration delta | 435 | 108 |

Card definitions are emitted once per principal. Routine passes and bookkeeping remain in authoritative history but do not enter ordinary packets. Detailed rulings are requested only when an interaction is materially ambiguous.

See `demo/token-benchmark.json` and `LLM_PROTOCOL.md`.

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
```

The pinned snapshot currently has 3,300 stable conformance cases and 3,300
generated source-linkage tests. They currently report 0 executable semantic
passes: 3,299 cases remain unreviewed and CR 310.11b is reviewed but blocked.
A generated inventory test cannot prove rules behavior. See
`RULE_CONFORMANCE.md` for the promotion, invalidation, and reporting policy.

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
python simctl.py oracle parse "Lightning Bolt" \
  --db data/scryfall-current.sqlite3
python simctl.py oracle explain "Rest in Peace" \
  --db data/scryfall-current.sqlite3
python simctl.py oracle coverage \
  --db data/scryfall-current.sqlite3
```

This is still not a completeness declaration. The measured compact snapshot
has 38,373 Oracle IDs: 2,957 exact, 15,691 partially lowerable, and 19,725
unresolved under current dependency gates. All 69,664 material residuals must
be eliminated or covered by reviewed, hash-pinned overrides before complete
Oracle support can be claimed. Genuinely unique cards may use reviewed
overrides; common cards and mechanics compile through reusable primitives.
See `RULES_COMPLETENESS.md` and `ORACLE_IR.md`.

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
- `mtg_commander_sim/mana.py` — conservative mana source parsing/planning
- `mtg_commander_sim/abilities.py` — explicit Oracle ability/cost extraction and zone authorization
- `mtg_commander_sim/session.py` — ChatGPT/Codex-friendly façade
- `mtg_commander_sim/service.py` — transport-neutral application boundary
- `mtg_commander_sim/pilot.py` — LLM callback orchestration and token metrics
- `mtg_commander_sim/profiles.py` — fingerprinted advisory deck profiles
- `mtg_commander_sim/preflight.py` — trust-aware deck semantic coverage
- `mtg_commander_sim/shortcuts.py` — validated aggregate loop fixtures
- `mtg_commander_sim/state_based_actions.py` — snapshot-based CR 704
  permanent-action and token-cessation evaluation
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

No software license has been selected for this public repository. Possession
of the source does not grant redistribution or relicensing rights.
