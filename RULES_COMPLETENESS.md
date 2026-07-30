# Rules completeness program

## Goal and current status

The long-term goal is deterministic enforcement of the pinned Magic
Comprehensive Rules and Oracle corpus for any supported deck, without writing
one engine branch per card.

This branch establishes the versioned corpus, typed Oracle IR, mechanic
contracts, and generic CR 400/613/616/704 primitives. It does not yet claim
complete rules or Oracle coverage. The current June 19, 2026 CR / July 28,
2026 compact Oracle snapshot deliberately reports:

- 3,300 unique numbered rules indexed
- 156 rules sections indexed
- 733 glossary entries indexed
- 425 CR section, keyword-action, and keyword-ability mechanics discovered
- 12 mechanics under versioned partial contracts and 413 unclassified
- 0 rules or mechanics promoted to trusted by the new registry
- 38,373 Oracle IDs and 41,582 faces scanned
- 2,957 exact (primarily textless), 15,691 partially lowerable, and 19,725
  unresolved Oracle IDs
- 69,664 material residuals, including untrusted dependencies
- `current_snapshot_complete = false`

Existing reviewed engine behavior and semantic packs remain available, but the
new corpus does not retroactively label them trusted until contracts, rule
references, and conformance tests are linked.

Oracle IR v2 additionally structures exact whole-line forms for simple self
enters/dies/leaves triggers, unconditional enters-tapped replacements, fixed
self pumps and keyword grants, one-counter instructions, and basic creature
token creation. These remain provisional wherever a dependency contract is
partial.

## New decks: generic compilation, not one branch per card

Most cards should be supported by reusable machinery:

```text
Pinned CR + Oracle + rulings
              │
              ▼
      versioned mechanics contracts
              │
              ▼
        typed Oracle semantic IR
              │
              ▼
  generic costs / targets / effects / layers
              │
              ▼
       authoritative legal actions
```

A new deck load now:

1. Resolve its current Oracle IDs and faces from the pinned local database.
2. Parses each ability into typed nodes such as costs, targets, triggers,
   replacement effects, continuous effects, searches, copies, and durations.
3. Links recognized nodes to mechanic dependency identifiers and source spans.
4. Keeps generated programs provisional and arbiter-gated until every
   dependency is trusted.
5. Rejects trusted execution if any material Oracle span remains unparsed or
   depends on an untrusted contract.
6. Caches generated programs by Oracle/rulings/compiler/semantic hashes.

That makes common wording and mechanics reusable across thousands of cards.
For example, one correct flying, Ward, Cycling, landfall, target-plan, or
zone-change implementation can serve every compatible Oracle template.

Some cards are genuine exceptions. A card-specific override is allowed only
when generic compilation cannot express it. The override must pin the Oracle
ID, Oracle hash, rulings hash, compiler failure category, rule references,
review status, and deterministic tests. Card-name conditions do not belong in
the turn, stack, cost, target, combat, or zone kernels.

## Pinned source snapshot

`simctl rules sync` locates the TXT link through the official Magic Rules page,
downloads it only from an allowlisted Wizards HTTPS host, and saves the
original under ignored `local/rules/`.

Tracked derived files contain no rules prose:

- `rules/manifest.json`
- `rules/rule-index.json`
- `rules/glossary-index.json`
- `rules/mechanic-index.json`
- `rules/dependency-graph.json`
- `mechanics/registry.json`
- `coverage/rules-coverage.json`
- `coverage/mechanics-coverage.json`
- `coverage/rules-delta.json`
- `coverage/oracle-coverage.json`
- `coverage/oracle-coverage-commander.json`

The manifest pins:

- effective date and official URLs
- raw CR SHA-256 and byte size
- parser/schema versions
- hashes of every derived index
- Oracle and rulings bulk timestamps, archive SHA-256 values, filenames, and
  record counts when a local Scryfall database is supplied

An existing Game Record continues to pin its own engine and semantic registry.
A later rules download cannot silently alter old command replay.

## Commands

Sync the official rules and pin the local Scryfall snapshot:

```bash
python simctl.py rules sync \
  --root . \
  --db data/scryfall-current.sqlite3
```

Inspect and verify:

```bash
python simctl.py rules inventory --root .
python simctl.py rules coverage --root .
python simctl.py rules next --root . --limit 20
python simctl.py rules verify --root .
python simctl.py rules report --root . --output local/rules-report.md
```

Compare a current corpus to an older checked-out/exported root:

```bash
python simctl.py rules diff \
  --root . \
  --against ../previous-rules-snapshot
```

The diff identifies added, removed, changed, and hash-identical renumbered
rules, writes JSON/Markdown artifacts, and blocks completeness until the delta
is reviewed.

The older in-game lookup remains available:

```bash
python simctl.py rules \
  --db data/scryfall-current.sqlite3 \
  --game run/example \
    "Sensei's Divining Top"
```

Compile and explain arbitrary Oracle cards:

```bash
python simctl.py oracle parse "Lightning Bolt" \
  --db data/scryfall-current.sqlite3
python simctl.py oracle explain "Rest in Peace" \
  --db data/scryfall-current.sqlite3
python simctl.py oracle residuals \
  --db data/scryfall-current.sqlite3
python simctl.py oracle coverage \
  --db data/scryfall-current.sqlite3 \
  --output coverage/oracle-coverage.json
```

Coverage artifacts omit Oracle prose and store identity, source span, reason,
blockers, and residual text hashes.

## Implemented generic foundations

`continuous_effects.py` implements CR 613 layer/sublayer ordering,
characteristic-defining-first/timestamp/dependency ordering, audited
dependency cycles, applicability/duration predicates, and typed copy, control,
text, type, color, ability, and power/toughness operations. The engine uses it
for copy overrides, bestow type changes, added types/subtypes, and temporary
keyword grants. Other legacy static-ability paths have not all been migrated,
so the contract remains partial.

`replacement_effects.py` implements the CR 616 priority classes, affected
player choice, optional decline, rechecking, and one application per
effect/event for typed events. It is not yet connected to every zone, draw,
damage, and enters event producer, so its contract also remains partial.

The zone kernel implements a stable physical card identity plus a serialized
logical-incarnation counter and zone-entry timestamp moment. Ordinary
cross-zone moves, draws, casts, and same-zone exile/command moves create new
incarnations; objects moved simultaneously to one destination share a
timestamp moment. Target snapshots and implemented linked delayed moves
require the recorded incarnation. State that cannot survive CR 400.7 is
cleared, while a permanent spell retains its logical incarnation under CR
400.7a and implemented stack-to-battlefield continuations such as as-enters
choices are explicit. The contract remains partial because the full CR 400.7
exception matrix, merged/melded and face-down objects, stickers, all legacy
physical-reference links, and complete CR 613.7m relative timestamp choices
have not yet migrated to typed policies.

`state_based_actions.py` implements an order-invariant CR 704 permanent
snapshot and distinguishes non-destruction graveyard moves, destruction,
unattachment, opposing +1/+1 and -1/-1 counter removal, and token or copy
cessation. The engine integrates that batch into its fixed-point loop, reuses
declarative attachment predicates, and preserves pre-batch last-known
information for simultaneous moves. Tokens and invalid-zone copies first reach
their destination, then cease during the next SBA check without a second
zone-change event. Spell copies, card copies, and tokens are distinct typed
objects; copied permanent spells become the same represented object as token
permanents without a token-creation event. A separate serialized World-since
timestamp supports CR 704.5k: the unique newest World permanent survives,
while a newest-duration tie moves every World permanent simultaneously.
Player loss, poison, empty draw, commander damage, planeswalker loyalty, and
the legend rule remain integrated in `CommanderEngine`. The contracts remain
partial: complete copiable values, card-copy casting/playing, Prepare,
specialized copy interactions, maximum-counter wording outside the reviewed
numeric self-restriction family, Sagas, dungeons, space sculptor, battles,
Roles, speed, complete enchant-quality grammar, regeneration, and simultaneous
loss-event replacement still block trust.

The Oracle compiler currently recognizes whole-sentence templates for simple
draw, life, damage, destroy, exile, return, counter, mill, tap/untap, scry,
power/toughness modification, printed keyword lists, and intrinsic mana
abilities. It never drops an unrecognized suffix; mutation tests verify that
added material text creates a residual.

## Trust gates

A rules or mechanic entry may move to `trusted` only after:

- a concise reviewed summary and behavioral classification
- an implementation component
- explicit dependency and applicability records
- a versioned mechanic contract
- positive, negative, interaction, multiplayer, and replay tests as applicable
- matching CR, Oracle, rulings, compiler, and implementation hashes

Any changed source hash invalidates the affected trust chain. Unknown
coverage, unparsed material Oracle text, an unresolved cost/target/layer
construct, or a surviving critical mutation blocks evidence-mode
completeness.

## Remaining implementation slices

The remaining work proceeds by dependency and blocked-card impact:

1. Strict server-issued action/choice schemas.
2. Complete object-identity continuation policies, last-known information,
   faces, merged objects, and linked abilities.
3. Casting, costs, restricted mana, and cost modification ordering.
4. Targeting, modes, distributions, resolution, and linked choices.
5. Complete trigger detection/order and the remaining state-based actions.
6. Migrate all continuous effects to the new evaluator, including CDA
   discovery, face-down/merged objects, players/game rules, and APNAP
   timestamps.
7. Connect replacement/prevention ordering to every replaceable event,
   including nested events and simultaneous APNAP choices.
8. Complete combat assignment and damage.
9. Specialized layouts, player designations, Commander, and multiplayer.
10. Typed Oracle IR coverage, differential tests, seeded fuzzing, and mutation
    gates across the complete pinned snapshot.

Until those gates pass, reports must describe exact implemented slices rather
than “complete Magic support.”
