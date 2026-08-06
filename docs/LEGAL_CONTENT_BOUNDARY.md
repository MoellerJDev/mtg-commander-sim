---
title: "Legal and third-party content boundary"
status: "current"
authoritative_source: "repository policy and runtime content adapter"
verified: "2026-08-06"
audience: "maintainers, deployers, and contributors"
maintenance: "hand-maintained"
---

# Legal and third-party content boundary

This document records product-engineering constraints. It is not legal advice
and does not authorize a public or commercial deployment.

Commander Arena is an independent project and is not endorsed by or affiliated
with Wizards of the Coast. Magic: The Gathering card names, rules text, card
imagery, frames, symbols, and related game content belong to their respective
rights holders. Scryfall supplies the card-data and image references used by
the optional local content adapter; Scryfall does not provide or endorse this
application.

## Repository and package boundary

The project's original software and documentation are licensed under
Apache-2.0. That software license does not grant rights to third-party Magic
card art, official frames, Oracle archives, Comprehensive Rules prose,
trademarks, or other provider and rights-holder content.

The source repository and built Python/browser packages must not contain:

- Scryfall bulk archives or complete database exports;
- downloaded card scans, artwork, official frames, set symbols, or Wizards
  branding;
- an embedded full Comprehensive Rules document;
- user-provided artwork or private deck/game data.

Tracked fixtures may contain the smallest public metadata needed for
deterministic tests. Local SQLite databases, compressed exports, retained
record snapshots, and image files live only in ignored runtime paths.

## Runtime content adapter

The local server retrieves the Scryfall bulk manifest with an identified user
agent, imports Oracle fields and rulings into SQLite, and stores only the image
URLs present in that snapshot. It follows Scryfall's published recommendation
to use bulk data rather than repetitive per-card API lookups.

Images are optional presentation data:

- only HTTPS `cards.scryfall.io` sources are accepted;
- deck images are prefetched with bounded concurrency and other visible images
  are cached on demand;
- complete scans are displayed without crop overlays that obscure attribution
  or copyright information;
- projected text remains the functional fallback, so official imagery is not
  required for gameplay;
- the cache is rebuildable, untracked, and excluded from release artifacts;
- the browser cannot request an arbitrary upstream URL or enumerate the bulk
  database.

Scryfall's current API-access guidance is available at
<https://scryfall.com/docs/faqs/i-m-having-trouble-accessing-the-scryfall-api-or-i-m-blocked-17>.
Provider and rights-holder terms can change; a deployment operator must review
the current Scryfall terms, Wizards policies, and applicable law rather than
assuming this engineering boundary grants content rights.

## Visual identity

The application uses its own name, colors, typography, layout, controls, and
generic UI surfaces. It does not recreate an official Magic client or render a
new imitation card frame. When a provider scan is unavailable or disabled, the
same server-projected name, mana cost, type, and rules text are presented in an
independent text-forward tile.

## Pre-public-deployment gate

Before any public beta, separately review and record decisions for:

- project name and trademarks;
- Oracle and Comprehensive Rules text use;
- card-image display, caching, retention, and takedown;
- Scryfall API/data terms and attribution;
- the current Wizards fan-content policy;
- account privacy and retention;
- user uploads, abuse handling, and takedown contact;
- monetization or sponsorship.

Public deployment and monetization remain out of scope until that review is
explicitly completed.
