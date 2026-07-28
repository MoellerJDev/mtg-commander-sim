# MTG Commander Sim 0.3.0

A persistent, four-player-first Commander simulation kernel designed for LLM pilots, rules arbitration, matchup testing, and a future graphical/network client.

This is a structural rewrite of the earlier two-player duel lab. The server-side game kernel is now separate from:

- per-seat strategic pilots
- card-text/rules arbitration
- hidden-information projections
- client transport and authentication
- reporting and deck-performance analysis

The engine is authoritative. Pilots choose legal actions through short-lived capabilities; they never write zones, life, mana, triggers, or effects directly.

## Local setup

The complete bundle can run directly from its source tree. To install the prebuilt command-line package without any network access:

```bash
python -m venv .venv
. .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --no-index dist/mtg_commander_sim-0.3.0-py3-none-any.whl
```

For editable development, use `python -m pip install -e . --no-build-isolation` in an environment that already has setuptools 68 or newer. Running `python simctl.py`, `make test`, and `make demo` from the repository does not require installation.

The complete bundle already contains `data/scryfall-20260728-compact.sqlite3`. With the source-only bundle, place the separately supplied `scryfall-20260728-compact.sqlite3.gz` under `data/` and run:

```bash
python scripts/bootstrap_data.py
make test
make demo
```

The local database was built from Scryfall's July 28, 2026 Oracle-card and ruling bulk files. No card-data network call is required during play.

To discover Scryfall's current timestamped Oracle and rulings exports and
atomically rebuild the local database before a game:

```bash
python scripts/bootstrap_data.py \
  --refresh-from-scryfall \
  --output data/scryfall-current.sqlite3
```

This follows `GET https://api.scryfall.com/bulk-data` at runtime and streams the
advertised `.jsonl.gz` files. Network access remains outside the game engine.

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
- conservative yield policies for longer periods with no intended response
- attacks split among multiple defenders and defender-by-defender blocking
- extra-turn scheduling in most-recent-created-first order
- native upkeep/end-step delayed triggers
- automatic core state-based actions, including lethal damage, zero toughness, the legend rule, poison, commander damage, and player elimination
- multiplayer continuation after a player leaves
- conservative Oracle-informed automatic mana payment with exact source logging
- server-extracted explicit activated abilities, including hand-zone Channel abilities and validated nonmana cost selections
- authoritative printed costs: a pilot cannot understate a spell cost, invent an activation cost, or cast from an unauthorized zone
- first-class stack-object countering
- top-of-library knowledge and reordering
- seat-private projections
- opaque single-use decision capabilities
- reusable semantic programs for card/ability resolutions
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

## Why this runs faster with an LLM

The engine does not call a model for deterministic bookkeeping or a priority window in which the implemented action grammar exposes no action. When a call is necessary, the pilot receives a seat-projected packet with short object references and only the current capability.

For the bundled four-seat Mishra/Zimone benchmark:

| Packet | Compact characters | Approximate input tokens |
|---|---:|---:|
| Initial A-seat bootstrap | 7,146 | 1,786 |
| Same live decision, unchanged state | 990 | 247 |
| A mulligan declaration delta | 435 | 108 |

Card definitions are emitted once per principal. Routine passes and bookkeeping remain in authoritative history but do not enter ordinary packets. Detailed rulings are requested only when an interaction is materially ambiguous.

See `demo/token-benchmark.json` and `LLM_PROTOCOL.md`.

## Deliberate rules boundary

This project does **not** claim that arbitrary Magic Oracle prose has been converted into a complete deterministic rules implementation.

The kernel handles general game mechanics and a generic effect DSL. When an uncompiled spell or ability resolves, a separate `arbiter` receives a narrowly scoped resolution capability. The arbiter may resolve that object once or register a reusable semantic program. Player pilots cannot submit arbitrary effects.

That boundary is safer and more auditable than silently guessing at card text, while allowing semantic coverage to grow from cards actually encountered in simulations.

The same rule applies to costs. Ordinary printed costs and a conservative set of explicit activated costs are derived by the server. A pilot may choose an advertised ability and the physical cards that pay delegated costs, but it cannot submit an arbitrary cheaper `declared_cost`, invent a sacrifice, or claim that a graveyard card is castable. Alternate costs, restricted mana, and unusual zone permissions must be compiled before use rather than trusted from player input.

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
  "plan":["cast lantern","hold up interaction"],
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

For strict isolation, use four pilot contexts plus one arbiter context against one `GameService`. Each connection authenticates as `pilot:A`, `pilot:B`, `pilot:C`, `pilot:D`, or `arbiter`. No engine or permission refactor is required for a GUI or network service; only a transport adapter is added around `GameService`.

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
- `mtg_commander_sim/record.py` — Game Record v3 hashing, journals, migration, inspection, and replay
- `mtg_commander_sim/report.py` — derived review and fidelity classification
- `mtg_commander_sim/carddb.py` — local Oracle/rulings database
- `mtg_commander_sim/deck.py` — deck loading and validation
- `schemas/` — versioned client-facing JSON schemas
- `scripts/` — data bootstrap and protocol smoke/benchmark tools
- `tests/` — multiplayer, permission, rules, and token-efficiency regression tests

Read `ARCHITECTURE.md`, `LLM_PROTOCOL.md`, and `CLIENT_INTEGRATION.md` before extending the engine.
