---
title: "CardProgram V2"
status: "current"
authoritative_source: "mtg_commander_sim/card_programs, mtg_commander_sim/semantics.py, and schemas/card-program-v2.schema.json"
verified: "2026-08-05"
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
  fixed life trigger and a closed fixed draw trigger can therefore execute
  without an arbiter. A draw trigger remains provisional when its count,
  choice legality, replacement wording, or any sibling effect is unresolved.
- Oracle IR v23 adds closed fixed-query static anthem and controlled-creature
  until-end-of-turn productions. CardPrograms declare the static or resolution
  continuous capability actually required; syntactic matches remain partial
  when targets, combat qualifications, stateful quantities, or other mechanic
  dependencies are not trusted.
- Oracle IR v25 makes a closed simple-object Enchant keyword declare
  `attachment.aura.simple_object`. Trust therefore requires the same targeting,
  entry, live-legality, replay, and mutation evidence used by the runtime;
  merely recognizing `Enchant` never makes a complex Aura exact.
- Oracle IR v27 makes closed fixed mandatory/optional draw nodes, fixed
  prohibitions, unconditional controller doubling, and `Dredge N` declare
  `zone.draw.library_to_hand`. Capability closure therefore depends on the
  same replacement, privacy, replay, multiplayer, and killed-mutation evidence
  as the canonical draw owner rather than on syntax alone.
- Oracle IR v28 makes runtime-handler equivalence a canonical semantic
  comparison rather than a hand-selected field comparison. The full typed
  object query and modifier must match before reviewed semantics can suppress
  a generated handler. Its closed CR 205.3m subtype grammar intentionally
  demotes prior false positives instead of preserving a misleading trust
  count.
- Oracle IR v29 makes executable Enchant and protection meaning part of the
  canonical runtime-handler descriptor. Display `add_rules_text` is not an
  executable granted ability; grants use typed activated/triggered fragments
  that participate in layer 6, discovery, source identity, trust binding, and
  replay fingerprints.
- Exact generated spell and activated-effect programs are executable only when
  their source-pinned semantic key is unique on the card. This lets a closed,
  capability-verified effect use the ordinary runtime without an arbiter while
  keeping cards with multiple effect clauses that currently share one key
  provisional. The compiler must introduce a stable finer-grained ability
  identity before those ambiguous programs can be promoted; registration never
  chooses one by iteration order.
- Fixed positive-integer damage clauses use one typed compiler template across
  spell, triggered, and activated contexts. Its closed recipient grammar is
  limited to any target, creature, creature or planeswalker, player, opponent,
  player or planeswalker, opponent or planeswalker, and each opponent. Dynamic,
  divided, conditional, mass, rider-bearing, and open-ended target restrictions
  remain source-spanned residuals rather than approximate executable effects.
- Oracle IR v34 applies the same capability-shaped promotion rule to closed
  fixed-count draw effects in spell and activated contexts. Controller,
  target-player, target-opponent, optional, and each-player payloads must match
  the strict typed shape and depend on `zone.draw.library_to_hand`; arbitrary
  CR 121 labels no longer grant that capability. Whole-key uniqueness prevents
  promotion of only the draw half of a compound spell or ability.

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
python simctl.py card pieces "Lightning Bolt"
```

`card explain` reports faces, abilities, typed nodes, source spans,
capabilities, tests, residuals, blockers, and runtime handler mapping. `audit`
checks deterministic round-trip and source linkage. `diff` reports exact
artifact paths instead of comparing prose.

`card pieces` reads the pinned reusable-piece index and reports how each
material ability relates to compiler templates, capabilities, mechanics, and
residual grammar boundaries. It is an inspection join, not an additional
CardProgram or trust authority.

For migrated nodes, `explain` and `audit` also report the stable handler ID,
handler schema version, and capability dependencies. This mapping is derived
from the frozen runtime registry and is not a second serialized authority.

See [ADR 0005](../adr/0005-card-program-v2.md), the
[normalized zone-trigger decision](../adr/0019-normalized-zone-trigger-discovery.md),
the [continuous-effect decision](../adr/0020-continuous-effect-duration-and-applicability.md),
[semantic-node guide](../extension/semantic-node.md), the
[typed-handler boundary](semantic-handlers.md), the
[trust-closure boundary](trust-closure.md), the
[runtime-component boundary](runtime-components.md), the
[reusable-piece inventory](reusable-rules-pieces.md), the
[override guide](../extension/card-override.md), and generated
[compiler status](../COMPILER_COVERAGE_STATUS.md).
