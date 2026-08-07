---
title: "Quorune rebrand and compatibility status"
status: "current"
authoritative_source: "repository metadata, pyproject.toml, protocol identifiers, and maintained product surfaces"
verified: "2026-08-07"
audience: "users, maintainers, release engineers, and coding agents"
maintenance: "hand-maintained"
concern: "rebrand-status"
---

# Quorune rebrand and compatibility status

This document separates the current Quorune identity from identifiers retained
for an intentional migration or durable replay/protocol compatibility. It is
the inventory authority for the rebrand; it is not permission to rename a
persisted identifier casually.

## Current public identity

| Surface | Current value |
| --- | --- |
| Product | Quorune |
| Tagline | Authoritative rules. Private state. Exact replay. |
| Repository | `MoellerJDev/quorune` |
| Previous repository | `MoellerJDev/mtg-commander-sim` (GitHub redirect only) |
| GitHub About | Deterministic, server-authoritative multiplayer card-game platform with enforced legal actions, private player state, persistence, and exact replay. |
| Topics | `card-game`, `deterministic`, `exact-replay`, `fastapi`, `game-engine`, `multiplayer`, `python`, `react`, `rules-engine`, `server-authoritative`, `websocket` |
| Browser and API title | Quorune / Quorune Server |
| Package author and maintainer | `MoellerJDev` |
| Current distribution | `mtg-commander-sim` pending the namespace migration |
| Current import namespace | `mtg_commander_sim` pending the namespace migration |
| Current installed commands | `mtg-commander-sim`, `simctl`, and `commander-server` |
| Target installed commands | `quorune`, `simctl`, and `quorune-server` |

Current compatibility work primarily targets the third-party Magic: The
Gathering Commander format. Those rules and format names remain where they
identify actual compatibility; they are not the Quorune product brand.

## Inventory classification

| Classification | Treatment in the public-identity slice |
| --- | --- |
| `first_party_current_brand` | Changed to Quorune in current product, browser, server, documentation, metadata, and network identification. |
| `public_distribution_identifier` | Retained for the separately certified Python migration. |
| `public_command` | `simctl` is the neutral current command; old installed aliases remain until the migration. |
| `public_product_positioning` | Describes the server-authoritative platform; optional AI and scripted clients are not the product. |
| `optional_client` | Presented as the Quorune Pilot Harness while compatibility paths remain temporarily. |
| `third_party_compatibility_reference` | Magic: The Gathering, Commander, Oracle, Comprehensive Rules, Scryfall, and Moxfield remain when technically accurate. |
| `rules_or_format_identifier` | Format profiles, Commander rule IDs, card fields, and rules terminology remain stable. |
| `historical_audit_reference` | Existing tags, changelog history, commits, ADR evidence, records, and old external links are not rewritten. |
| `generated_artifact` | Regenerated from its authoritative source after source changes. |
| `compatibility_alias` | Retained only where changing it could break installs, clients, saved state, protocol consumers, or exact replay. |
| `unrelated` | Ordinary uses such as a rules description of a commander card are unchanged. |

## Deliberately retained identifiers

The following old identifiers remain by design and must not be treated as
missed search-and-replace results:

- the `mtg-commander-sim` distribution, `mtg_commander_sim` package directory,
  and old executable aliases, until the Python namespace migration;
- `MTG_*` environment variables used by automation and existing local setups,
  pending a compatibility-aware environment migration;
- `$id` values under `https://mtg-commander-sim.local/`, because they identify
  existing versioned schemas rather than a network origin;
- Game Record v3 values such as `mtg-commander-game`, engine-generated replay
  identity prefixes, format-profile values, and capability IDs;
- the `X-Commander-Tab` header, `commander.tab.*` subprotocol, and existing
  browser storage keys, which are client compatibility identifiers;
- `.agents/skills/commander-arena`, `.codex/agents/mtg-pilot-*.toml`,
  `arena-*` commands, and recorded pilot thread labels until optional-client
  path migration is certified;
- historical release, changelog, ADR, record, and audit references that must
  continue to describe the artifact that actually existed.

`CommanderEngine` remains the internal domain facade. A future rename to
`RulesKernel` is optional architectural work, not part of the brand migration,
and must retain a compatibility alias if undertaken.

## Migration and validation state

1. Repository and publication reconnaissance is complete. The repository is
   public, `main` is the default branch, and repository administration is
   available to the maintainer.
2. GitHub and the public product surfaces use Quorune. Generated protocol,
   platform, architecture, and repository reports are refreshed by their
   authoritative generators.
3. Neither the old distribution name nor `quorune` was present on PyPI when
   checked on the verification date. The repository has version tags but no
   GitHub Release publication. Therefore the namespace migration does not need
   a previously published PyPI compatibility package.
4. The exact next task is the independently certified Python distribution,
   import namespace, optional-client path, and command migration. Saved Game
   Record v3 data and protocol/replay identifiers remain compatible throughout.

Focused local validation covers changed Python compilation, JSON and YAML
parsing, documentation and repository policy, generated freshness, browser
type checking/build, and diff hygiene. Exact-head public CI remains the
behavioral, replay, privacy, packaging, Windows, and browser certification
authority.
