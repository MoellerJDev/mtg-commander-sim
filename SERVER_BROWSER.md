# Server and browser vertical slice

Version 0.8.0 includes an executable, responsive two- or four-player browser slice with
card-centric play/cast/activate interaction and generic forms for the rules engine's
current server-issued choice schemas. One
Python process builds and serves the browser, manages the local Scryfall data
snapshot, and serves locally cached card images. It is a single-node
development deployment, not a claim of complete Magic rules, future-schema
coverage, production-scale operations, or complete accessibility.

## Run locally — one command

After installing the Python project, start everything with:

```powershell
python -m pip install -e . -r requirements-dev.txt
python -m server
```

The launcher installs `web/` dependencies if needed, performs a production
browser build when sources are newer than `web/dist`, starts the API and
WebSocket server, serves the browser from the same origin, and opens
`http://127.0.0.1:8000`. There is no second Vite terminal in the normal local
workflow. Use `--no-open`, `--no-build-browser`, or `--offline` when needed.

If `MTG_CARD_DB` is not set, the first run shows a setup screen while the
server discovers the current Scryfall Oracle Cards and Rulings JSONL archives,
downloads them into `data/bulk/`, and builds
`data/scryfall-current.sqlite3`. The server checks the bulk manifest every 24
hours. A successful build removes superseded managed archives and retains only
the current Oracle/rulings pair. An update discovered while the server is live
is built as one pending database and activated at the next restart; the open
database remains pinned for existing Game Records. Activation moves the old
SQLite file into `data/card-snapshots/` only when a saved Game Record references
its fingerprint. Unreferenced snapshots are deleted, and lazy game recovery
selects the exact retained database named by that record.

The same manifest check runs before the game runtime becomes ready on every
startup. A stale existing database is updated and activated before deck import
is exposed. A network failure falls back to that existing database with a
visible warning rather than making the application unusable.

If the first-run network request fails, the setup page keeps the error visible
and offers a local retry. If an update check fails after a database exists, the
server remains usable with a warning and the pinned database.

On Windows, a second Commander Arena process can keep the active SQLite file
open while a pending update is being activated. When a usable current database
already exists, startup now serves it in an `update_ready` state and reports
the lock instead of failing the application lifespan. Stop every other local
server with `Ctrl+C`, then restart once to activate the staged database. If no
current database exists, activation still fails closed rather than pretending
card data is ready.

Choose a display name to create an expiring guest session. A host creates a
1v1 `commander_duel` or four-seat `commander_multiplayer` room and shares its
invite code. Each browser tab receives a distinct HttpOnly guest binding even
when incognito windows share one cookie jar. Other players join distinct seats,
then each seat submits either a public Moxfield URL or a pasted Commander list.
Each player receives a visible private ready summary after validation.
Before game start, a player can use **Change deck / Unready** to clear only
their own submitted list and return to validation. The host's raw invite code
remains available through readying and page reloads for that browser session.
If it is unavailable, the host can generate a replacement; rotation immediately
invalidates the previous code. The owner can remove a nonowner seat or atomically
close and replace an unstarted room; a nonowner can leave and release their
seat. Only the room owner can start after every configured seat is occupied and
ready.

## Playing from the table

The right-side card viewer follows pointer hover and keyboard focus across every
visible card in a hand, command zone, battlefield, public zone, or the stack. It
shows large locally cached art plus the full projected name, cost, type line,
and Oracle text. A face switcher reads both visible faces of a double-faced
card. Narrow layouts replace the persistent viewer with an explicit enlarged
card dialog so it does not squeeze the battlefield.

Graveyard and exile counts on every player board open a searchable-by-eye card
grid and inspector for that complete public zone. An opponent's hand remains a
count, and libraries remain hidden except for information the projection says
that seat legally knows. The browser never reads the run directory or a raw
checkpoint to populate these views.

The action tray remains an accessibility and recovery fallback and uses card
names instead of generic verbs: for example, **Play Watery Grave**, **Cast Sol
Ring — {1}**, and **Sensei's Divining Top — Draw a card, then put Sensei's
Divining Top on top of its owner's library**. Cards in the hand, command zone,
owned public zones, and battlefield are highlighted when a linked action is
legal. Click a highlighted card to select it and reveal only that card's current
actions. Drag a playable land or spell onto your battlefield for the fast path.
If the destination is ambiguous, such as a modal double-faced spell/land, the
browser asks which server-issued action to execute.

Casting defaults to **Auto-mana**, which asks the authoritative engine to use a
valid routine payment. Select **Manual mana** to highlight untapped permanents
with currently legal mana abilities. Click those sources in the desired
activation order; a source with multiple modes presents exact choices such as
**Add {U}** or **Add {B}** and adds only the selected bundle. Floating mana is
shown on the player's board. Then choose or drag the spell again. The engine
uses the floated pool first, validates the complete payment, and may finish a
routine unpaid remainder. This mode controls activation order; it is not yet a
general restricted-mana or arbitrary cost-allocation editor.

Land-face entry choices come from that face's Oracle text. **Play Agadeem, the
Undercrypt** therefore offers **Pay 3 life to enter untapped**, charges exactly
3 if selected, enters as the land face, and requests the back-face image.
Dropping, selecting, or activating never bypasses timing, priority, cost,
target, semantic, or fidelity checks: every gesture resolves to the same
capability-scoped action ID as the action tray. The client contains no parallel
legality rules.

While the server performs its startup card-data check, existing room pages
back off polling from 750 ms to at most once every five seconds and resume
automatically. Room APIs may briefly return `503`; that is expected readiness
gating, but a high-volume tight retry loop is not.

Future-dated preview cards whose snapshot legality is `not_legal` use a
two-step validation response. The first response returns the owner-only card
names, release dates, and an exact confirmation fingerprint. The second request
must return that fingerprint before the list is saved. Banned, unknown, or
already-released illegal cards are not confirmable. Other seats see only the
public fact and count of a preview override, never the implicated private deck
entries.

Runtime files default to ignored `local/server/`. Override that root with
`MTG_SERVER_DATA`, the card database with `MTG_CARD_DB`, allowed browser origins
with comma-separated `MTG_ALLOWED_ORIGINS`, and production cookie security with
`MTG_SECURE_COOKIES=1` behind HTTPS. `MTG_DATA_ROOT`, `MTG_BULK_DIR`,
`MTG_IMAGE_CACHE`, `MTG_WEB_DIST`, `MTG_AUTO_UPDATE_CARDS`, and
`MTG_CARD_UPDATE_SECONDS` control the managed local paths and update behavior;
`MTG_CARD_SNAPSHOT_DIR` overrides retained record-pinned databases.

The browser served by `python -m server` is automatically accepted as the exact
same origin (normally `http://127.0.0.1:8000`) for WebSocket upgrades.
`MTG_ALLOWED_ORIGINS` is for additional origins such as a separate development
frontend; it does not need to repeat the server's own origin.

## Card data and images

Rules text, characteristics, aliases, legality, image references, and rulings
are indexed in SQLite. No bulk file is sent to the browser, and no Scryfall API
request occurs inside the rules engine or a running game transition.

The importer stores the chosen Oracle-card image references in a `card_images`
table. After a deck validates, the server prefetches the unique normal-size
images in that submitted list with bounded concurrency. The browser itself asks
only for local routes such as `/api/v1/cards/20283c4a/image?size=normal` when a
projected card is actually rendered. The cache downloads that Scryfall CDN
image once, writes it atomically below `data/images/`, and serves the local copy
thereafter. Commanders, private hand cards, public permanents, stack objects,
and visible tokens therefore load as a small working set; hidden hands and
libraries never enter another seat's DOM or image request list. Custom tokens
without a pinned Scryfall image use the text fallback.

The client displays complete scans without crop overlays, and it remains fully
usable through projected card text when art is unavailable. Cached image bytes
are runtime content, not repository or package assets. See
`docs/LEGAL_CONTENT_BOUNDARY.md` before deploying beyond local development.

## Implemented surface

| Route | Purpose |
|---|---|
| `GET /api/v1/system` | Read public server/card-data/image-cache readiness |
| `POST /api/v1/system/refresh` | Retry managed setup from the local machine |
| `GET /api/v1/cards/{oracle_prefix}/image` | Fetch/cache one Scryfall card face locally |
| `POST /api/v1/guests` | Issue an expiring guest session and CSRF token |
| `GET /api/v1/me` | Restore the authenticated guest |
| `POST /api/v1/rooms` | Create an invite-only two- or four-seat room |
| `POST /api/v1/rooms/join` | Atomically claim one unoccupied seat |
| `GET /api/v1/rooms/{room_id}` | Read public lobby readiness |
| `POST /api/v1/rooms/{room_id}/invite` | Owner-only replacement of the room invite |
| `POST /api/v1/rooms/{room_id}/replace` | Atomically close and replace an owner's unstarted room |
| `DELETE /api/v1/rooms/{room_id}/seats/{seat}` | Owner-only removal of a nonowner player |
| `DELETE /api/v1/rooms/{room_id}/membership` | Leave an unstarted room and release the caller's seat |
| `PUT /api/v1/rooms/{room_id}/deck` | Resolve, validate, fingerprint, and preflight a deck |
| `DELETE /api/v1/rooms/{room_id}/deck` | Clear the caller's own unstarted deck/readiness |
| `POST /api/v1/rooms/{room_id}/start` | Start one multiplayer Commander game |
| `GET /api/v1/games/{game_id}` | Inspect safe lifecycle and journal counters for a seated member |
| `GET /api/v1/games/{game_id}/state` | Request the caller's seat projection |
| `POST /api/v1/games/{game_id}/stop` | Owner-only durable administrative stop |
| `POST /api/v1/games/{game_id}/resume` | Owner-only resume of an administrative stop |
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
- Stop, resume, inspect, commands, and projections all cross the same actor
  mailbox. A stop writes Game Record status `paused` with an
  `administrative_stop` reason before it is acknowledged; a resume restores the
  same pending decision boundary. New commands fail with `game_paused` while
  stopped, but a retry of an already recorded command still returns its exact
  idempotent receipt.
- Browser resume is deliberately narrower than record-level rules arbitration:
  it can resume only `administrative_stop`. It cannot clear a semantic,
  fidelity, corruption, abort, or completed-game boundary.

SQLite holds guest, room, seat, deck, game-index, and idempotency control-plane
records. Authoritative game truth remains the existing checksummed Game Record
v3 directory. PostgreSQL, multi-process actor ownership, background expiry,
rate limiting, spectators, accounts, and deployment containers remain later
operations work.

## Stop, resume, and inspect

Every seated player can open **Inspect match**. The response contains only
control-plane and public record metadata: lifecycle status, state revision,
turn/phase, pending principal labels, and command/decision/event counts. It
does not contain a record path, checkpoint, hand, library order, capability,
or analyst artifact.

Only the room owner receives the stop/resume controls. **Stop match** is a
resumable administrative pause, not a concession, abort, rules override, or
game action. The reason is public to the table. The server saves the exact
accepted-command prefix before responding and broadcasts the lifecycle update
on the existing seat-scoped stream. All rendered actions are disabled while
paused, and the application layer also rejects direct command submissions.

Refreshing a browser or restarting the server while stopped reloads the
checksummed paused record. The owner can then resume from the preserved
decision; other seats cannot invoke either lifecycle mutation. The current
slice does not provide a permanent delete/abort button, platform-wide admin
console, scheduled expiry, or multi-process game ownership.

## Browser verification

```powershell
Set-Location web
npm run generate:types
npm run typecheck
npm run build
npx playwright install chromium
npm run e2e
```

The end-to-end suite includes four tabs sharing one Chromium cookie jar,
creates four isolated tab-bound guest sessions, atomically fills seats A–D, uploads the two
duplicated exact-list fixtures, and starts a game. One scenario submits all four
keep decisions, proves owner-only stop controls, propagates a durable paused
status to all four contexts, disables the current decision, reloads a nonowner
while paused, resumes, aborts one command request, retries the byte-equivalent
command envelope with the same idempotency ID, records the exact projected hand
  count and decision, then requires a later full reconnect projection to match
  those values. It verifies that hover inspection follows each seat's private
  hand, public-zone controls start from the projected counts, and the 390-pixel
  layout exposes an enlarged touch-friendly card viewer without horizontal overflow. A
1v1 scenario replaces a room, removes and rejoins seat B, starts the
`commander_duel` profile, and verifies both private projections. A separate
scenario takes a post-free mulligan, exercises Escape/focus restoration,
selects a private card to bottom through the generic form, proves that the other
three DOMs never receive that seat-scoped control, and submits the resulting
six-card keep. The duplicated pod is protocol evidence only, never matchup
evidence.

## Generic decision forms

Each projected legal action may contain a JSON-only `form` version. The same
Python adapter that builds that form defines the only choice-field names the
application service accepts. The browser renders the form, but the engine still
revalidates cardinality, targets, modes, costs, payability, and rules effects.
The current form vocabulary covers:

- required and optional single references, multi-reference selection, and
  ordering;
- booleans, bounded integers/X, names, enums, and legal-seat choices;
- exact server-issued mana bundles for multi-mode mana abilities;
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
spectators, screen-reader audits across every future choice schema, cache size
quotas, and production deployment remain later server/browser work.
