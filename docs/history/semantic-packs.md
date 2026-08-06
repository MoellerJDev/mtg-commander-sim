---
title: "Semantic packs"
status: "current"
authoritative_source: "CardProgram V2 adapter, semantic pack schema, loader, and tracked packs"
verified: "2026-08-05"
audience: "rules and semantic-pack contributors"
maintenance: "hand-maintained"
---

# Semantic packs

Semantic packs are reviewed compatibility inputs for card behavior that is not
yet fully produced by generic Oracle compilation. The loader converts them into
canonical CardProgram V2 objects and the same typed runtime boundaries used by
generated programs. Packs do not replace Game Record v3, grant a client mutation
authority or make an LLM a rules source.

Current generic/card coverage and trust basis is generated in
[`docs/COMPILER_COVERAGE_STATUS.md`](docs/COMPILER_COVERAGE_STATUS.md). This
reference intentionally contains no exact-list counts or version-era status
ledger.

## Identity and schema

Each program identifies:

- Oracle ID, face and stable ability key;
- active zone and trigger/event identity;
- semantic schema and program version;
- typed targets, choices, costs, effects and destinations;
- capability and runtime-component requirements;
- source Oracle and rulings hashes;
- characterization tests, authoring provenance and review status;
- trust level and explicit blockers.

Programs are grouped by Oracle ID. Conflicting source hashes or face identities
fail loading. Deterministic CardProgram, semantic-registry and trust
fingerprints are stored with a game. The semantic-key map is a derived runtime
and historical-record index; saved registries reject a mismatch between views.

Pack schema v3 remains a supported compatibility input. Loading a reviewed pack
normally produces trust basis `legacy_reviewed`, or `mixed` when it composes
with capability-closed generated abilities. Review alone never upgrades the
program to capability-closed.

## Relationship to generic compilation

Hand-authored packs are not the scaling architecture for arbitrary decks. The
Oracle compiler recognizes closed whole-text and ability-clause grammars,
emits source-spanned typed nodes, preserves every unmatched material span as a
residual, and declares the required capabilities. Generated and reviewed nodes
then share CardProgram validation and runtime execution.

At creation time, a reviewed program can shadow an equivalent generated ability
for the same source identity so the engine does not create duplicate triggers or
effects. The shadowing decision is deterministic and fingerprinted. It does not
hide unrelated residual text.

When substantially similar reviewed descriptors recur, add a generic compiler
production and runtime component instead of a third card-specific pack.

## Runtime boundary

The executor accepts only validated, versioned operations and registered typed
components. Runtime placeholders such as `$controller` and `$target.0` resolve
against authoritative stack/source context. A component receives immutable
rules facts and emits a typed result or intent; it has no arbitrary callback,
card-name dispatch or unrestricted `GameState` access.

Replacement, continuous, trigger, damage, draw, life, counter, attachment and
other families participate only through their canonical coordinators and
mutation owners. A source-pinned witness proves that exact reviewed descriptor,
not universal support for similar-looking Oracle text.

Semantic choices suspend through versioned replay-pinned continuations. Private
candidates project only to the chooser, while public journals retain the
minimum replay/audit identity permitted by the rules.

## Trust

Pack-level `trusted` means the declared compatibility behavior was reviewed and
characterized. CardProgram capability closure is the stronger product gate.
`provisional` is development-only, `unresolved` fails strict preflight, and
`intentionally_ignored` is valid only for text proven immaterial to the selected
operation and profile.

Trusted-only play fails when any materially reachable ability has:

- unparsed Oracle text;
- an untrusted or missing capability;
- a source hash mismatch;
- an unsupported target, cost, timing, layer or replacement dependency;
- a failed interaction, replay, privacy or mutation gate.

Development arbitration may help characterize a future pack. It is not
production legality and cannot silently mutate an active game.

## Preflight

Run preflight against the current managed snapshot:

```powershell
.\.venv\Scripts\python.exe simctl.py semantics preflight `
  <deck-file-or-public-moxfield-url> `
  --db data/scryfall-current.sqlite3 `
  --cache-dir run/deck-cache `
  --output run/preflight.json
```

The report separates fully playable, partial and unresolved cards; identifies
material residual categories and trust dependencies; pins loaded pack hashes;
and states whether the selected operation profile can proceed. A deck label or
commander-name fallback is not exact-list profiling.

## Add or replace coverage

1. Read the exact pinned Oracle text, official rulings and relevant rules.
2. Prefer extending a reusable compiler grammar and typed rules family.
3. If an override is irreducible, document why and use the narrow extension
   boundary.
4. Add deterministic positive, negative, interaction, multiplayer, rollback,
   replay, privacy and mutation evidence as applicable.
5. Record fresh source hashes, capability dependencies and the lowest honest
   trust level.
6. Run preflight and focused tests, then regenerate final corpus reports once.
7. Remove obsolete pack behavior after generic compilation becomes the sole
   owner.

Never mark a whole card trusted when a material activated, triggered, static,
replacement or alternate-zone ability remains unresolved.
