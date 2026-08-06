---
title: "MTG Commander Sim"
status: "current"
authoritative_source: "implemented package, server/browser runtime, and generated status reports"
verified: "2026-08-05"
audience: "users and contributors"
maintenance: "hand-maintained"
---

# MTG Commander Sim 0.8.0

MTG Commander Sim is an experimental, deterministic, server-authoritative
Commander platform. Four-player Free-for-All Commander is the primary target;
two-player Commander remains available for focused play and regression tests.

The repository contains a usable local browser client, durable games, exact
command replay, seat-private projections, managed Scryfall card data and an
on-demand image cache. It does **not** yet implement every Comprehensive Rule or
every Oracle interaction. Material unsupported behavior fails closed instead of
being guessed.

The engine is authoritative. Browser, manual, scripted, subprocess and optional
AI clients can select only server-issued actions; they cannot directly change
zones, life, mana, counters, triggers or effects. Ordinary play and testing do
not require an LLM.

For the exact current implementation and coverage boundary, use the generated
[platform status](docs/PLATFORM_IMPLEMENTATION_STATUS.md),
[rules status](docs/RULES_COMPLETENESS_STATUS.md),
[compiler coverage](docs/COMPILER_COVERAGE_STATUS.md), and
[architecture debt](docs/ARCHITECTURE_DEBT_STATUS.md). The
[documentation map](docs/index.md) is the canonical index.

## Run the local app

Install 64-bit CPython 3.12.x and Node.js 22+. Python 3.11 and 3.13+ are not
supported by this development line.

On Windows:

```powershell
.\scripts\bootstrap_windows.ps1
.\.venv\Scripts\python.exe -m server
```

The server prints `http://127.0.0.1:8000` but does not open a browser unless you
explicitly pass `--open`. Open the printed address yourself. Use `Ctrl+C` to
stop; run the same command again to resume durable rooms and games.

The first startup installs browser dependencies, builds the client, checks the
Scryfall bulk-data manifest, downloads Oracle Cards and Rulings when necessary,
and builds `data/scryfall-current.sqlite3`. Later startups check freshness, with
a 24-hour polling interval while the server stays running. A replacement
snapshot is staged atomically so an active game never changes card data beneath
it. Superseded unreferenced bulk files and databases are removed.

Card images are not mirrored wholesale. Deck images are prefetched and other
visible cards are cached on demand under `data/images/`; the browser requests
only local server routes. These third-party cache files are ignored by Git and
are not packaged. See the [content boundary](docs/LEGAL_CONTENT_BOUNDARY.md).

To start without network access when a database already exists:

```powershell
$env:MTG_CARD_DB = "data/scryfall-current.sqlite3"
.\.venv\Scripts\python.exe -m server --offline
```

More startup, recovery and inspection commands are in the
[local operations guide](docs/operations/local-app.md) and
[server/browser reference](SERVER_BROWSER.md).

## Browser workflow

1. Choose a guest display name.
2. Create a two- or four-seat private room, or join with an invite.
3. Submit a Moxfield Commander URL or pasted deck list.
4. Review legality and semantic-preflight warnings, then ready up.
5. Start when every configured seat is occupied and ready.

Guest identity is intentionally lightweight and stored per browser tab. A host
can copy or replace the invite, remove a participant, change the room setup or
create a new room. Players can unready/change decks or leave before start.
Invited spectators receive public state and the durable public log but cannot
submit seat actions.

Published preview cards known to Scryfall but not yet tournament-legal require
explicit confirmation bound to the submitted deck fingerprint. Confirmation
does not override bans, construction errors, missing data or unsupported rules.

At the table:

- Hover or focus a card to inspect large art and projected rules text.
- Select a card to see only its current server-issued actions.
- Drag a playable land or spell toward the battlefield for the same validated
  action path; ambiguous cards open a compact chooser.
- Auto-mana is the default. Manual mana lets you click sources in order and,
  while still reversible, undo a simple mana activation.
- Auto-pass is the default for safe pass-only response windows. Hold every
  priority requires explicit passes. Main-phase advancement remains explicit.
- Public graveyards, exile, the stack, commander damage, tapped state and the
  complete public event log remain visible to every participant.
- The bottom hand dock and right-side panels can be resized; layout preferences
  are stored only in that browser.

In a two-player Commander game, only the starting player skips the draw on that
player's first turn. The other player draws normally. With three or more
players, every player—including the starter—draws on their first turn.

The browser is a projection and command adapter, not a second rules engine. A
label, drag gesture or cached preference never creates legality.

## Current boundaries

The platform already has the durable multiplayer, projection, replay,
capability, compiler and typed rules-subsystem foundations needed for continued
rules work. Coverage is intentionally incremental. Unsupported replacement,
continuous-effect, cost, copying, combat and unusual zone-permission variants
remain explicit residuals until their whole reusable family is implemented and
certified.

Do not infer broad card or matchup support from a witness test, duplicated-deck
fixture or partial game. CardPrograms become trusted only through capability
closure and positive, negative, replay, mutation and dependency evidence. Live
product play stops on material unresolved semantics.

The pinned rules corpus and Scryfall snapshot are local build inputs. Generated
reports—not prose counts in this file—are the authority for current rule,
mechanic, compiler and card coverage.

## Development setup

The Windows bootstrap performs the normal editable installation. The equivalent
manual setup is:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e . -r requirements-dev.txt
npm ci --prefix web
npm run generate:types --prefix web
npm run typecheck --prefix web
npm run build --prefix web
```

Build the compact deterministic test database:

```powershell
.\.venv\Scripts\python.exe scripts\build_test_database.py build `
  --fixture tests/fixtures/scryfall-exact-lists.json `
  --fixture tests/fixtures/browser-lifecycle-cards.json `
  --fixture tests/fixtures/damage-result-cards.json `
  --output data/test-ci.sqlite3
$env:MTG_CARD_DB = "data/test-ci.sqlite3"
```

When local feedback is needed, run only the exact new or adjacent impacted
tests. Inspect the deterministic change-impact plan without executing its broad
gate:

```powershell
.\.venv\Scripts\python.exe scripts\quick_gate.py --dry-run
```

Pull-request CI is the ordinary exact-head certification authority. It runs
Python shards, generated/architecture checks, packaging, Windows compatibility
and isolated headless browser tests. Push coherent work and use the CI window
for independent development rather than duplicating broad suites locally. Do
not open or navigate a visible browser from automation. Broader local gates are
reserved for an explicit request or diagnosis of a release-critical/CI-only
persistence, replay, privacy or packaging failure. See the
[CI pipeline guide](docs/development/ci-pipeline.md).

Game records, databases, bulk downloads, image/deck caches, provider memory,
capabilities and local test output belong only in ignored paths. Never commit a
live checkpoint or private projection. Repository and fixture rules are in
[CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).

## Command-line tools

The browser is the normal manual interface. `simctl.py` also exposes deterministic
creation, task, action, replay, reporting, rules, corpus and coverage commands.

Create a duel directly from two Moxfield URLs:

```powershell
.\.venv\Scripts\python.exe simctl.py duel `
  --db data/scryfall-current.sqlite3 `
  --out run/duel --cache-dir run/deck-cache --refresh-decks `
  --profile commander_duel --trace-level standard `
  https://moxfield.com/decks/g5vtVfRuS0W5KxZuYqZHGQ `
  https://moxfield.com/decks/armNI_ntVUagNNygnUVyxQ
```

Inspect and verify a Game Record v3 directory:

```powershell
.\.venv\Scripts\python.exe simctl.py inspect-game run/duel --pretty
.\.venv\Scripts\python.exe simctl.py replay run/duel `
  --db data/scryfall-current.sqlite3 --verify
.\.venv\Scripts\python.exe simctl.py report run/duel `
  --db data/scryfall-current.sqlite3
```

Provider-specific automation is optional. Its isolation, structured-response and
recording contracts are documented in [PILOT_PROVIDERS.md](PILOT_PROVIDERS.md)
and [CODEX_ARENA.md](CODEX_ARENA.md). Rules semantics and provenance are covered
by [SEMANTIC_PACKS.md](SEMANTIC_PACKS.md) and [GAME_RECORD.md](GAME_RECORD.md).

## Architecture at a glance

The main dependency direction is:

```text
browser / scripts / optional pilots
                |
       server and GameService
                |
 projection -> session -> CommanderEngine
                         /       |        \
              typed proposals  rules   mutation owners
                         \       |        /
                     Game Record v3
```

- `mtg_commander_sim/` contains the transport-neutral authoritative runtime.
- `server/` owns HTTP/WebSocket identity, rooms, persistence and app startup.
- `web/` is the React projected-state client.
- `rules/`, `mechanics/` and `platform/` contain pinned sources and policy.
- `coverage/` and generated status documents report measured support.
- `tests/` contains deterministic rules, replay, privacy, multiplayer and
  protocol assurance.

Read the concise [architecture overview](ARCHITECTURE.md) and its linked modular
documents before changing rules ownership. Contribution and repository policy
is in [AGENTS.md](AGENTS.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

No software license has been selected. Public visibility does not grant
redistribution or relicensing rights.
