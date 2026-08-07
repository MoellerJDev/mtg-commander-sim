---
title: "Quorune security policy"
status: "current"
authoritative_source: "implemented security controls and disclosure policy"
verified: "2026-08-07"
audience: "users, contributors, and security reporters"
maintenance: "hand-maintained"
---

# Quorune security policy

## Reporting

Report vulnerabilities privately through the repository's GitHub Security
Advisory interface. Do not open a public issue containing a capability,
checkpoint, opposing hand, library order, pilot memory, provider credential, or
reproduction record with hidden information.

Include the affected commit, impact, minimal reproduction, and whether any
private game artifact was exposed. Rotate any real credential or bearer
capability before sharing a sanitized report.

## Security-sensitive boundaries

The following are treated as security defects:

- bypassing fixed-seat capability or principal checks
- exposing another seat's hidden zones, memory, packets, or choices
- exposing authoritative checkpoints through a pilot tool
- allowing pilots or a parent coordinator to mutate state outside legal actions
- accepting forged provider, model, thread, or seat identity
- persisting live capabilities in tracked fixtures
- path traversal from a seat-scoped tool into analyst or run artifacts
- accepting a browser-supplied principal, seat, payment, or effect operation
- acknowledging a state-changing command before durable Game Record save
- persisting raw guest tokens, invite codes, or decision capabilities
- sharing a delta cursor between independent network connections
- allowing a nonowner to stop or resume a game
- allowing browser resume to clear a rules, fidelity, abort, or corruption pause
- allowing a spectator to receive a decision capability, claim seat authority,
  or submit a copied seat capability
- exposing private event details, hidden events, checkpoint contents, or
  analyst artifacts through the public game log

Custom-agent instructions are not an operating-system sandbox. The fixed-seat
tool and projection layers enforce the application boundary; use an isolated,
read-only workspace when filesystem isolation must also be demonstrated.

## Browser/server boundary

The first network slice uses 256-bit random guest bearer tokens in HTTP-only,
SameSite=Strict cookies. A non-secret, per-tab selector chooses a distinct
HttpOnly cookie for each top-level browser tab, so Chrome incognito windows may
share a cookie jar without sharing a seat. The same selector travels as a
WebSocket subprotocol, while the bearer itself remains out of JavaScript and
URLs. Unsafe cookie-authenticated requests also require a double-submit CSRF
token. Browser WebSockets accept the request's exact HTTP(S) origin or an
explicitly configured development/deployment origin; unrelated origins remain
rejected.
SQLite stores SHA-256 hashes of guest tokens and room invite codes, never their
raw values. The host browser retains its raw invite only in session storage so
it survives readying and reload without becoming server-side plaintext; closing
that browser session may require an owner-only replacement. Replacing an invite
atomically invalidates the old hash. Room membership selects the one pilot
principal available to a seated guest or the capability-free `spectator`
principal for a watch-only guest. The command endpoint independently requires
a seat, so request content cannot promote a spectator. Decision capabilities
remain separate short-lived grants and are never login credentials.

Legacy clients without a tab selector may continue using the base guest cookie.
When a valid selector is present, authentication never falls back to that shared
cookie; an unregistered tab must create its own guest session. This fail-closed
rule prevents the last incognito login from silently taking over every tab.
The current room ID and any owner invite display are likewise kept in tab-scoped
session storage rather than shared local storage.

Set `MTG_SECURE_COOKIES=1` behind HTTPS. Restrict `MTG_ALLOWED_ORIGINS` to the
deployed browser origin. Game members may inspect only whitelisted lifecycle
metadata. Spectators receive the same public/control-plane subset without
owner controls. The public-log endpoint returns a fixed compact event shape
after spectator visibility filtering and never returns raw event details; the
room owner alone may durably stop/resume an
`administrative_stop`. Those endpoints never expose the backing record path or
accept a client-selected principal. The current development server does not yet
provide production accounts, password recovery, platform-wide administration,
rate limiting, reverse proxy hardening, secret rotation, multi-process actor
leases, or an independent security assessment; it should not be exposed
directly to the public Internet.

The browser never receives the bulk Scryfall export or an unrestricted card
database query. Projected cards reference a short Oracle identifier, and the
same-origin image endpoint resolves it against local SQLite metadata. Cache
misses may fetch only HTTPS URLs on `cards.scryfall.io`; arbitrary image hosts,
oversized responses, and non-image content are rejected. Manual bulk refresh
is restricted to the local machine.

Preview legality confirmation is bound to the exact deck-list fingerprint and
structured warning set. Room members may see that a preview override exists
and how many issues it contains, but only the deck owner receives implicated
card names. The override cannot authorize a banned card, arbitrary URL, missing
database object, or unsupported semantic operation.

## Supported version

Only the current development line receives security fixes. The repository is
public, but the project remains experimental and has not undergone an
independent security audit.
