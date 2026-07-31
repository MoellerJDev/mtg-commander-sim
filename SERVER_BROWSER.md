# Server and browser vertical slice

Version 0.8.0 includes an executable four-player browser slice with generic
forms for the rules engine's current server-issued choice schemas. It is a
single-node development deployment, not a claim of complete Magic rules,
future-schema coverage, production-scale operations, or finished accessibility
and visual design.

## Run locally

Build the compact pinned database, install both dependency sets, then start the
API and Vite development server in separate terminals:

```powershell
python scripts/build_test_database.py build `
  --fixture tests/fixtures/scryfall-exact-lists.json `
  --output data/test-ci.sqlite3
python -m pip install -e . -r requirements-dev.txt
Set-Location web
npm ci
Set-Location ..
$env:MTG_CARD_DB = "data/test-ci.sqlite3"
python -m server --host 127.0.0.1 --port 8000
```

```powershell
Set-Location web
npm run dev
```

Open `http://127.0.0.1:5173`. A host creates a room and shares its invite
code. The other three browser contexts join distinct seats, then each seat
submits either a public Moxfield URL or a pasted Commander list. Only the room
owner can start after all four seats are occupied and ready.

Runtime files default to ignored `local/server/`. Override that root with
`MTG_SERVER_DATA`, the card database with `MTG_CARD_DB`, allowed browser origins
with comma-separated `MTG_ALLOWED_ORIGINS`, and production cookie security with
`MTG_SECURE_COOKIES=1` behind HTTPS.

## Implemented surface

| Route | Purpose |
|---|---|
| `POST /api/v1/guests` | Issue an expiring guest session and CSRF token |
| `GET /api/v1/me` | Restore the authenticated guest |
| `POST /api/v1/rooms` | Create an invite-only four-seat room |
| `POST /api/v1/rooms/join` | Atomically claim one unoccupied seat |
| `GET /api/v1/rooms/{room_id}` | Read public lobby readiness |
| `PUT /api/v1/rooms/{room_id}/deck` | Resolve, validate, fingerprint, and preflight a deck |
| `POST /api/v1/rooms/{room_id}/start` | Start one multiplayer Commander game |
| `GET /api/v1/games/{game_id}/state` | Request the caller's seat projection |
| `POST /api/v1/games/{game_id}/commands` | Submit a strict protocol 3.0 command |
| `WS /api/v1/games/{game_id}/stream` | Receive full and delta seat projections |

The command body contains protocol, game, client command, decision, action,
capability, expected view revision, and delegated choices. It cannot contain a
principal, seat, arbitrary effect, controller, or server-derived payment. The
server derives `pilot:A`–`pilot:D` from the authenticated room seat.

## Correctness and durability

- `GameManager` owns exactly one `GameActor` for each active in-process game.
- Every observation, command, poll, and connection-cursor cleanup crosses that
  actor's bounded mailbox.
- Accepted mutations are saved as Game Record v3 before acknowledgement.
- An ambiguous persistence error fails the actor closed; recovery creates a new
  actor from durable state.
- Idempotency is keyed by game, authenticated principal, and client command ID.
  Reusing the ID with the identical request returns the original receipt;
  changing the request is a conflict.
- SQLite stores only hashes of guest tokens and invite codes. Game Record and
  SQLite journals never persist raw decision capabilities.
- Every WebSocket has its own ephemeral projection cursor. Multiple tabs for
  one seat cannot corrupt each other's delta base, and network cursors are not
  included in durable Game Record state.
- Reconnect always starts with a full hash-verified projection, then resumes
  deltas.
- A process restart lazily recreates a game actor from its checksummed Game
  Record, issues fresh opaque capabilities for the surviving decision, and
  preserves durable idempotency receipts. The application-level recovery test
  submits before and after restart and verifies exact command replay.

SQLite holds guest, room, seat, deck, game-index, and idempotency control-plane
records. Authoritative game truth remains the existing checksummed Game Record
v3 directory. PostgreSQL, multi-process actor ownership, background expiry,
rate limiting, spectators, accounts, and deployment containers remain later
operations work.

## Browser verification

```powershell
Set-Location web
npm run generate:types
npm run typecheck
npm run build
npx playwright install chromium
npm run e2e
```

The end-to-end suite opens four isolated Chromium contexts per scenario,
creates four guest sessions, atomically fills seats A–D, uploads the two
duplicated exact-list fixtures, and starts a game. One scenario submits all four
keep decisions, records the exact projected hand count and decision, reloads
seat A, and requires the full reconnect projection to match those values. A
second scenario takes a post-free mulligan, selects a private card to bottom
through the generic form, proves that the other three DOMs never receive that
seat-scoped control, and submits the resulting six-card keep. The duplicated
pod is protocol evidence only, never matchup evidence.

## Generic decision forms

Each projected legal action may contain a JSON-only `form` version. The same
Python adapter that builds that form defines the only choice-field names the
application service accepts. The browser renders the form, but the engine still
revalidates cardinality, targets, modes, costs, payability, and rules effects.
The current form vocabulary covers:

- required and optional single references, multi-reference selection, and
  ordering;
- booleans, bounded integers/X, names, enums, and legal-seat choices;
- alternate/additional cost variants and their variant-scoped fields;
- modal, grouped, and multi-target selection;
- private search/fetch choices and as-enters life payment;
- mulligan bottoms, cleanup discards, trigger order, AP/NAP and legend choices;
- attacker-to-defender and blocker-to-attacker assignment;
- server-derived combat-damage source power and legal targets; and
- per-copy storm target retention or retargeting.

Private candidates enter a form only through that authenticated seat's
projection. Simultaneous decisions still produce independent seat packets and
capabilities. A browser cannot name another principal or submit a field absent
from the selected server action. Unknown future schemas remain unavailable or
fail closed until both the adapter and UI support them; the client never guesses
rules behavior.

Production accounts, multi-process ownership, rate limiting, containers,
spectators, accessibility hardening, and richer retry/resume presentation remain
later server/browser work.
