# Server and browser vertical slice

Version 0.8.0 includes the first executable four-player browser slice. It is a
single-node development deployment, not a claim of complete Magic rules,
production-scale operations, or a finished choice UI.

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

The end-to-end test opens four isolated Chromium contexts, creates four guest
sessions, atomically fills seats A–D, uploads the two duplicated exact-list
fixtures, starts the game, verifies four private seven-card hands, submits all
four keep decisions through server capabilities, and reloads seat A. It expects
eight cards after reconnect because the first player draws on turn one in the
implemented multiplayer Commander profile. The duplicated pod is protocol
evidence only, never matchup evidence.

The first browser slice renders ordinary legal-action buttons. Generic forms
for every target, mode, cost, search, ordering, replacement, trigger, and combat
choice remain the next UI slice; unsupported choices still fail closed at the
server.
