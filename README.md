# MTG Commander Sim 0.8.0

An experimental, persistent, four-player-first Commander simulation kernel
designed for LLM pilots, rules arbitration, auditable testing, and a future
graphical/network client. The current release is a research/development
baseline, not a complete implementation of Magic's rules or Oracle corpus.

This is a structural rewrite of the earlier two-player duel lab. The server-side game kernel is now separate from:

- per-seat strategic pilots
- card-text/rules arbitration
- hidden-information projections
- client transport and authentication
- reporting and deck-performance analysis

The engine is authoritative. Pilots choose legal actions through short-lived capabilities; they never write zones, life, mana, triggers, or effects directly.

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
- automatic core state-based actions, including lethal damage, zero toughness, the legend rule, poison, commander damage, and player elimination
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
- typed, source-spanned Oracle IR with deterministic semantic hashes and
  fail-closed material residuals
- automatic deck-time generic compilation into provisional, arbiter-gated
  semantic programs
- CR 613 layer/sublayer, timestamp, dependency, and cycle-audit primitives,
  now used for common copy/type/keyword annotations
- CR 616 replacement/prevention priority and affected-player-choice
  primitives
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

## Why this runs faster with an LLM

The engine does not call a model for deterministic bookkeeping or a priority window in which the implemented action grammar exposes no action. When a call is necessary, the pilot receives a seat-projected packet with short object references and only the current capability.

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

The kernel handles general game mechanics and a generic effect DSL. When an uncompiled spell or ability resolves, a separate `arbiter` receives a narrowly scoped resolution capability. The arbiter may resolve that object once or register a reusable semantic program. Player pilots cannot submit arbitrary effects.

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
```

Deck creation now invokes the typed Oracle compiler automatically. Exact
whole-text templates lower into the generic effect DSL without a printed-name
branch, but generated programs stay provisional and arbiter-gated while any
mechanic dependency is untrusted. Unknown suffixes, costs, triggers,
replacement effects, or static text remain material residuals.

```bash
python simctl.py oracle parse "Lightning Bolt" \
  --db data/scryfall-current.sqlite3
python simctl.py oracle explain "Rest in Peace" \
  --db data/scryfall-current.sqlite3
python simctl.py oracle coverage \
  --db data/scryfall-current.sqlite3
```

This is still not a completeness declaration. The measured compact snapshot
has 38,362 Oracle IDs: 2,957 exact, 13,684 partially lowerable, and 21,721
unresolved under current dependency gates. All 69,823 material residuals must
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
    # Route only this packet to the model/context assigned to the principal.
    response = your_llm_call(principal, packet)
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

Run the primary Codex task in GPT-5.6 Sol with Ultra reasoning, then use the
generated `PRIMARY_CODEX_PROMPT.md`. Start four persistent fast pilot sessions
and drive the requested prefix with:

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

A single ChatGPT conversation can obey seat projections, but it cannot literally forget a hand shown while it was previously acting as another player.

For strict live isolation, use four persistent pilot contexts plus the neutral
primary coordinator against one `GameService`. Each pilot process fixes its
seat at startup. The primary is the arbiter rather than a fifth strategic
pilot. Projected packets, per-seat memory files, server-injected provider
identity, and exact-ref rules lookup prevent protocol-level leakage.

Custom-agent instructions are not an operating-system sandbox when a parent
Codex session overrides them with `danger-full-access`. The MCP/CLI façade is
the enforced game-state boundary; use a dedicated read-only permission profile
and empty pilot workspace when filesystem-level isolation must also be proven.

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

No software license has been selected for this private repository. Possession
of the source does not grant redistribution or relicensing rights.
