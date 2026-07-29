# Semantic packs

Semantic packs compile reviewed Oracle behavior into the engine's generic
effect DSL. They extend `SemanticRegistry`; they do not replace the Game Record
or grant pilots state-mutation authority.

## Program identity

Each JSON program records:

- Oracle ID and stable semantic key
- face or ability identifier
- active zone and trigger/event identity
- semantic schema and program version
- target/choice schema where required
- generic effects and destination
- coverage labels and characterization tests
- source Oracle and rulings hashes
- authoring provenance and review status
- trust level

The source hashes pin the Scryfall snapshot used for review. An empty rulings
list still has the deterministic SHA-256 hash of its serialized empty array.
Pack files are included as package data in the wheel.

## Trust

`trusted` means the declared behavior is reviewed and characterized for this
implementation. `provisional` can support a native pilot test but cannot make a
material interaction eligible as matchup evidence. `unresolved` requires the
arbiter or a future compiler. `intentionally_ignored` is only appropriate when
the omitted ability is demonstrably irrelevant to the recorded operation.

The executor accepts validated DSL operations only. The kernel selects programs
by Oracle/ability keys and runtime events, not printed-name branches. Runtime
placeholders such as `$controller` and `$target.0` are resolved against the
current stack object.

## Version 0.7.0 interaction slice

Target schemas are declarative plans rather than card-name conditionals. They
support modal groups, public zones, players and stack objects, target counts,
distinctness, state/type/color/mana-value filters, controller and owner
relationships, source exclusion, and resolution-time conditions. Mandatory
groups with insufficient candidates remove the cast or activation from the
ordinary legal alternatives.

The interaction pack pins current local Oracle and rulings hashes and has
deterministic positive and negative scenarios for:

- An Offer You Can't Refuse, Mana Drain, Swan Song, Force of Negation, Pact of
  Negation, Flusterstorm, Red Elemental Blast, and Pyroblast
- Assassin's Trophy, Abrade, Chaos Warp, Feed the Swarm, Tear Asunder, Force of
  Vigor, Toxic Deluge, Vandalblast, and Deadly Rollick
- Boseiju, Who Endures; Otawara, Soaring City; Cankerbloom; Soul-Guide
  Lantern; and Pithing Needle

These programs preserve their different target timing, modes, destinations,
delayed payments/mana, storm copies, kicker/overload/pitch costs, life-X, and
token results. They are not interchangeable templates.

## Version 0.6.0 vertical slice

The bundled packs characterize:

- Zimone and Dina permanent, activation, optional land placement, eight-land
  repetition, and second-card-drawn target
- Lotus Cobra permanent and controller-selected landfall mana
- Field of the Dead's seven-distinct-land-name threshold
- Warren Soultrader permanent and Treasure-producing activation
- provisional Gravecrawler graveyard permission and the tested aggregate loop
- Zulaport Cutthroat's role in the tested aggregate loop
- Mishra, Eminent One and its beginning-of-combat Warform choice
- 4/4 hasty Warform characteristic override and delayed end-step sacrifice
- provisional Ichor Wellspring coverage
- provisional Gonti's Aether Heart permanent plus trusted artifact-entry energy
- trusted Red Elemental Blast and provisional Pyroblast target/resolution
- provisional generic hidden-library searches for Entomb, Three Visits,
  Nature's Lore, Fabricate, Goblin Engineer's entry trigger, Survival of the
  Fittest, Elvish Reclaimer, and Wight of the Reliquary

This is not complete coverage of either 100-card deck. In particular, the
preflight reports retain unresolved costs, activated abilities, triggers, and
replacement effects rather than silently treating them as vanilla. The
generated reports under `run/semantic-preflight-*.json` are the authoritative
inventory for this snapshot.

Version 0.6.0 improves legal-action and continuation exactness without claiming broad Oracle
coverage:

- mandatory activated costs must be currently payable before an action is
  advertised
- Boseiju Channel is withheld without enough independent mana
- tapped-source and tap-symbol availability are exact for Sensei's Divining Top
- Mox Opal validates the public three-artifact Metalcraft condition before it
  can pay another action
- fully parenthesized basic-land reminder abilities are normalized
- `Sacrifice a land` is a compiled delegated mandatory cost
- a resolving program can suspend on a seat-private search, persist its
  versioned semantic frame, then resume exactly after the choice
- restrictive and optional hidden-zone searches support legal fail-to-find
- destination, reveal, shuffle, typed-land entry, and shockland life choices
  are server-controlled

Ordered plans may name a future private search choice without knowing its
physical object reference. The server resolves that name only after the scoped
choice exists. Execution stops on a response, stack/cost/target change, hidden
draw, new unsupplied choice, combat, semantic uncertainty, or fidelity failure.

Other activation conditions and complex tutors remain unresolved rather than
guessed. Green Sun's Zenith, Finale of Devastation, Chord of Calling, Protean
Hulk, Diabolic Intent, Reshape, Transmute Artifact, Whir of Invention, Arcum
Dagsson, Inventors' Fair, Urza's Saga, Repurposing Bay, and Spellseeker still
require additional cost/selection/linked-effect compilation. The primary
coordinator never chooses a private search result for the player.

## Preflight

```bash
python simctl.py semantics preflight <deck-file-or-public-moxfield-url> \
  --db data/scryfall-20260728-compact.sqlite3 \
  --cache-dir run/deck-cache \
  --output run/preflight.json
```

The report includes total, fully playable, partial, and unresolved card counts;
unresolved cast costs, activated abilities, triggered abilities, and
replacement effects; expected arbiter calls; loaded pack hashes; and whether
`deck_review_eligible` is possible.

Preflight is deliberately conservative. Generic built-ins cover ordinary mana,
basic/typed lands, bond lands, fetch search/shuffle, shockland entry choice, and
the currently compiled land conditions. A card is not promoted merely because
some of its text resembles a supported family.

For the July 28, 2026 decks, the current reports are:

| Live deck | Fully playable | Partial | Unresolved | Expected arbiter calls | Review eligible possible |
|---|---:|---:|---:|---:|---|
| Zimone and Dina (`g5vt…`) | 42 | 2 | 56 | 58 | no |
| Mishra, Eminent One (`armNI…`) | 44 | 3 | 53 | 56 | no |

Those counts are a safety result, not a defect hidden by a fixture. Neither the
scripted turn-eight duel nor the duplicated-list Codex run is deck-quality or
matchup evidence.

## Adding coverage

1. Read the exact local Oracle card and applicable rulings.
2. Add or extend generic DSL support without card-name branches in
   `CommanderEngine`.
3. Add a deterministic scenario exercising choices, targets, timing, costs,
   triggers, and replay.
4. Author the program with fresh source hashes, provenance, tests, and the
   lowest honest trust level.
5. Run preflight and the complete suite.
6. Regenerate and replay any fixture whose semantic fingerprint changed.

Do not mark a whole card trusted when only its spell-to-battlefield transition
is implemented and an activated, triggered, or replacement ability remains
materially unresolved.
