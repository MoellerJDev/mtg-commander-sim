---
title: "CardProgram V2"
status: "current"
authoritative_source: "mtg_commander_sim/card_programs, mtg_commander_sim/semantics.py, and schemas/card-program-v2.schema.json"
verified: "2026-08-03"
audience: "compiler, rules, replay, and semantic-pack contributors"
maintenance: "hand-maintained"
---

# CardProgram V2

`CardProgram` schema version 2 is the canonical deterministic card artifact.
It groups every executable ability for one Oracle ID with card and face
identity, Oracle/rulings hashes, source spans, compiler and semantic hashes,
residuals, provenance, exact capability dependencies, an explicit trust basis,
applicable closure layers, and one artifact fingerprint.

Each stable ability ID projects the runtime ability into explicit fields for
active zones, timing permissions, costs, modes, targets, choices, effect
nodes, triggers, static effects, replacements, prevention, continuous effects,
linked identities, durations, delayed effects, copy behavior, and zone
permissions. An empty field means that artifact does not declare the family;
it is not evidence that the family is universally implemented.

The existing `SemanticProgram` class is the executable ability object inside
CardProgram V2. Semantic pack v3 files are compatibility inputs. The registry
groups them by Oracle ID and retains the old semantic-key map only as a derived
index for engine callers and historical records. Saved `semantics.json`
snapshots contain both views and fail loading if they disagree.

Generated Oracle IR produces the same CardProgram shape. Reviewed pack
abilities supersede generated abilities only on the same semantic key.
Unpinned provisional abilities may be represented for development, but their
missing hashes become explicit trust blockers. Conflicting nonempty hashes,
ambiguous faces, stale source data, material residuals, or fingerprint drift
fail closed.

## Trust boundary

- `capability_closed`, `legacy_reviewed`, `mixed`, `provisional`, `unresolved`,
  and `non_rules_governed` are distinct bases. A reviewed pack is never silently
  promoted to capability-closed.
- Intrinsic, format, match, and dynamic closure are computed separately. The
  currently incomplete format-capability inventory blocks capability-only
  strict matches without blocking the explicit reviewed compatibility mode.
- Compiler output remains provisional when material residuals or dependencies
  are unresolved.
- Broad mechanic aggregate status neither grants nor revokes a smaller exact
  closure; unmigrated nodes keep the conservative broad-contract gate.
- New Game Record v3 manifests pin every CardProgram fingerprint and trust
  closure plus capability-evidence, semantic-handler, and runtime-component
  fingerprints. Commands pin the programs and compact runtime bindings actually
  used. Replay validates these when present and remains compatible with older
  v3 records.
- A compiler semantic correction changes both compiler version and artifact
  fingerprint. Historical v3 snapshots deserialize their pinned CardProgram
  rather than being silently recompiled as current output; a mismatched
  manifest or command fingerprint fails explicitly.
- Runtime accepts registered operations only. Oracle prose is not parsed
  during a state transition.
- Oracle IR v22 gives simple self enter/dies/leaves triggers three independent
  closure dimensions: normalized zone-event detection, ordinary APNAP trigger
  placement, and the result operation. Session registration promotes only
  exact trigger programs for which every declared capability is trusted. A
  fixed life trigger can therefore execute without an arbiter, while an exact
  ETB draw trigger remains provisional on the blocked draw-event capability.

## Execution ownership

`mtg_commander_sim/card_programs/` owns pure schema validation, deterministic
serialization, adapters, inspection, and source/identity checks. It owns no
`GameState` and cannot mutate a game. `SemanticRegistry` owns the canonical
groups and semantic-key index. The Phase 4 typed runtime maps migrated effect
operations to registered handlers with immutable rules queries and typed
intents. Phase 5 runtime components expose active static/replacement abilities
through family-specific immutable contexts; continuous sources are collected
through a narrow read-only state protocol and emit typed layer effects.
`CommanderEngine` remains the mutation owner; unmigrated operations stay on
the measured legacy dispatcher.

## Inspection

```bash
python simctl.py card compile "Lightning Bolt" --db data/scryfall-current.sqlite3
python simctl.py card explain "Mishra, Eminent One" --db data/scryfall-current.sqlite3
python simctl.py card audit "Mishra, Eminent One" --db data/scryfall-current.sqlite3
python simctl.py card diff "Mishra, Eminent One" \
  --against snapshots/mishra.card-program.json \
  --db data/scryfall-current.sqlite3
python simctl.py card overrides --db data/scryfall-current.sqlite3
python simctl.py card coverage --limit 100 --db data/scryfall-current.sqlite3
python simctl.py card trust-closure "Lightning Bolt" --profile commander_duel \
  --db data/scryfall-current.sqlite3
python simctl.py card runtime-components --profile commander_review \
  --db data/scryfall-current.sqlite3
```

`card explain` reports faces, abilities, typed nodes, source spans,
capabilities, tests, residuals, blockers, and runtime handler mapping. `audit`
checks deterministic round-trip and source linkage. `diff` reports exact
artifact paths instead of comparing prose.

For migrated nodes, `explain` and `audit` also report the stable handler ID,
handler schema version, and capability dependencies. This mapping is derived
from the frozen runtime registry and is not a second serialized authority.

See [ADR 0005](../adr/0005-card-program-v2.md), the
[normalized zone-trigger decision](../adr/0019-normalized-zone-trigger-discovery.md),
[semantic-node guide](../extension/semantic-node.md), the
[typed-handler boundary](semantic-handlers.md), the
[trust-closure boundary](trust-closure.md), the
[runtime-component boundary](runtime-components.md), the
[override guide](../extension/card-override.md), and generated
[compiler status](../COMPILER_COVERAGE_STATUS.md).
