# Rules completeness program

## Goal and current status

The long-term goal is deterministic enforcement of the pinned Magic
Comprehensive Rules and Oracle corpus for any supported deck, without writing
one engine branch per card.

This branch establishes the versioned corpus and coverage foundation. It does
not yet claim complete rules or Oracle coverage. The current June 19, 2026
snapshot deliberately reports:

- 3,300 unique numbered rules indexed
- 156 rules sections indexed
- 733 glossary entries indexed
- 425 CR section, keyword-action, and keyword-ability mechanics discovered
- 0 rules or mechanics promoted to trusted by the new registry
- `current_snapshot_complete = false`

Existing reviewed engine behavior and semantic packs remain available, but the
new corpus does not retroactively label them trusted until contracts, rule
references, and conformance tests are linked.

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

A new deck load will eventually:

1. Resolve its current Oracle IDs and faces from the pinned local database.
2. Parse each ability into typed nodes such as costs, targets, triggers,
   replacement effects, continuous effects, searches, copies, and durations.
3. Link every node to implemented mechanics contracts and CR rule IDs.
4. Reject trusted play if any material Oracle span remains unparsed or depends
   on an untrusted contract.
5. Cache the resulting semantic program by Oracle/rulings/compiler hashes.

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

## Planned implementation slices

The remaining work proceeds by dependency and blocked-card impact:

1. Strict server-issued action/choice schemas.
2. Object identity, zones, last-known information, faces, and copies.
3. Casting, costs, restricted mana, and cost modification ordering.
4. Targeting, modes, distributions, resolution, and linked choices.
5. Trigger detection/order and state-based actions.
6. Continuous effects, layers, dependencies, text changes, and CDA handling.
7. Replacement/prevention ordering and self-replacement.
8. Complete combat assignment and damage.
9. Specialized layouts, player designations, Commander, and multiplayer.
10. Typed Oracle IR coverage, differential tests, seeded fuzzing, and mutation
    gates across the complete pinned snapshot.

Until those gates pass, reports must describe exact implemented slices rather
than “complete Magic support.”
