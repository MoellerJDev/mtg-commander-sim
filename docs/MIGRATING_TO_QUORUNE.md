---
title: "Migrating to Quorune"
status: "current"
authoritative_source: "pyproject.toml, package layout, installed entry points, and durable protocol identifiers"
verified: "2026-08-07"
audience: "users, operators, contributors, and release engineers"
maintenance: "hand-maintained"
concern: "namespace-migration"
---

# Migrating to Quorune

The project repository, Python distribution, import namespace, and installed
commands now use the Quorune name. Game Record v3, replay, protocol, schema,
environment-variable, and browser-storage identifiers remain stable so the
rename does not reinterpret saved games or client state.

## Repository

The repository moved from `MoellerJDev/mtg-commander-sim` to
`MoellerJDev/quorune`. GitHub redirects the old URL, but existing checkouts
should update their remote explicitly:

```powershell
git remote set-url origin https://github.com/MoellerJDev/quorune.git
git fetch origin --prune
```

The maintained local source root is `C:\Code Projects\Quorune`.

## Python distribution and imports

The previous, unpublished distribution name was `mtg-commander-sim`, with the
implementation imported as `mtg_commander_sim`. The distribution and import
namespace are now both `quorune`:

```python
from quorune import CommanderSession, GameConfig
```

Neither distribution name was published on PyPI when the migration was
verified, and this repository has no GitHub Releases. Consequently there is no
transition compatibility package or deprecation window: source checkouts must
update imports directly.

## Commands

Clean wheel installs provide:

```text
quorune
simctl
quorune-server
```

`quorune` and `simctl` invoke the same command-line application.
`quorune-server` starts the local browser/server runtime. The unpublished old
executable names are not installed.

## Saved games and protocol compatibility

This migration does not change legal actions, state mutation, event ordering,
private projections, protocol fields, or authoritative replay hashes. Existing
Game Record v3 data remains on its original schema and engine identity values,
and representative pre-rename records must continue to replay to the same
authoritative hashes.

The old name therefore remains intentionally in stable schema `$id` values,
record/profile identifiers, the runtime identity namespace used by replay,
`MTG_*` environment variables, `X-Commander-Tab`, `commander.tab.*`, and
existing browser storage keys. See [rebrand status](REBRAND_STATUS.md) before
changing any of those compatibility identifiers.
