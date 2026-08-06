---
title: "MTG Commander Sim"
status: "current"
authoritative_source: "product entry point, supported profile, and local startup workflow"
verified: "2026-08-06"
audience: "new users and contributors"
maintenance: "hand-maintained"
concern: "project-overview"
---

# MTG Commander Sim

MTG Commander Sim is a deterministic, server-authoritative multiplayer
Commander platform. It combines typed rules execution, capability-scoped
commands, seat-private projections, exact command replay, a local browser
client, and a pinned local card-data snapshot.

The project is experimental. Four-player Free-for-All Commander is the primary
supported profile; the documented duel profile supports narrower testing and
local play. The engine does not implement every Comprehensive Rule or Oracle
interaction, and the local server is not a production deployment. Unsupported
material behavior fails trusted preflight or stops before mutation. Read the
generated [platform](docs/PLATFORM_IMPLEMENTATION_STATUS.md),
[rules](docs/RULES_COMPLETENESS_STATUS.md), and
[compiler](docs/COMPILER_COVERAGE_STATUS.md) status for the current claim
boundary.

## Five-minute local start

The supported runtime is CPython 3.12.x. From PowerShell at the repository root:

```powershell
.\scripts\bootstrap_windows.ps1
.\.venv\Scripts\python.exe -m server
```

The command prepares the browser, checks or builds the managed Scryfall SQLite
snapshot, serves HTTP and WebSocket endpoints, and prints the local URL. It does
not open or focus a browser; open the printed URL yourself. The first card-data
download can take longer than the normal start. Stop cleanly with `Ctrl+C`.

For offline startup, troubleshooting, environment variables, and safe recovery,
see [local application operations](docs/operations/local-app.md). The
[browser product guide](docs/product/browser.md) describes rooms, table
interaction, and current user-facing limitations.

## Architecture summary

Clients render principal-scoped projections and submit server-issued action IDs.
The transport derives identity, one serialized actor owns each game, and
`CommanderEngine` plus typed rules subsystems remain the only game-state
authority. Pinned Oracle data compiles to source-spanned CardPrograms whose
capabilities must close over registered rules owners. Accepted commands are
persisted before acknowledgement and replay against exact before/after hashes.

Start with the [architecture portal](ARCHITECTURE.md), then use the
[documentation map](docs/index.md) to find subsystem, protocol, replay,
operations, extension, and decision records.

## Content and license boundary

The repository does not ship Scryfall bulk exports, a complete Oracle archive,
Comprehensive Rules prose, card scans, official frames, or Wizards branding.
Local card data and images are rebuildable, ignored runtime content. Commander
Arena is independent and is not endorsed by Wizards of the Coast or Scryfall.
See the [legal and third-party content boundary](docs/LEGAL_CONTENT_BOUNDARY.md)
before distributing or deploying the application.

The project's original software and documentation are licensed under the
[Apache License 2.0](LICENSE). That license does not grant rights to third-party
Magic card art, official frames, Oracle archives, Comprehensive Rules prose,
trademarks, or other provider and rights-holder content.

## Project guides

- [Browser product](docs/product/browser.md)
- [Local operations](docs/operations/local-app.md)
- [Protocol reference](docs/reference/protocol.md)
- [Architecture](ARCHITECTURE.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Generated status](docs/PLATFORM_IMPLEMENTATION_STATUS.md)
- [Documentation map](docs/index.md)
