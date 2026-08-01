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

## Corpus compilation

Hand-authored packs remain valid reviewed artifacts, but they are not the
scaling architecture for arbitrary new decks. The rules-completeness pipeline
pins the official CR, Oracle, and rulings snapshots, validates mechanic
contracts, and compiles Oracle text into a typed intermediate representation.
Recognized whole-text templates lower into the same generic DSL and kernel
primitives used by current packs.

Oracle IR v6 includes a shared combat-declaration cost grammar for exact
fixed ordinary-mana intrinsic, attached-Aura, defending-player attack, and global block-tax
sentences. The compiler records a typed static-cost node and the engine uses
the same parser to derive live costs. Complex symbols, appended instructions,
and broader conditional forms retain material residuals and stop fail closed;
this is reusable sentence-family support, not card-name coverage.

The same version includes a shared declaration-restriction grammar. Exact
absolute, not-alone, count, type, supertype, subtype, token, keyword, color,
goad, source-stat, denied-blocker, except-by, attached-evasion, and
can-block-only families compile into typed static nodes and feed the same
finite solver at runtime. Multiple represented restrictions are cumulative.
Conditional, compound-with-unrelated-effects, controller/history-dependent,
temporary, target-specific, and multi-block families retain material residuals
instead of being guessed.

At deck creation, generated programs are added only when their stable
Oracle/face/ability key is not already supplied by a reviewed pack. Reviewed
trigger event handlers also shadow equivalent generated event handlers even
when their author-defined keys differ; this prevents duplicate triggers. A
generated program records source line offsets, Oracle/rulings hashes, compiler
and template IDs, and a semantic hash. It is `provisional` and
`requires_arbiter=true` until every mechanic dependency is trusted. Under
`trusted_only`, it is withheld or stopped rather than executed.

Any material unparsed Oracle span, untrusted mechanic dependency, or source
hash mismatch fails trusted preflight. A card-specific override must record why
generic compilation failed and pin its Oracle/rulings/rule/test provenance.
See `RULES_COMPLETENESS.md`.

## Normalized damage events

The current combat path emits `damage.dealt` only for a positive final dealt
result. Its immutable context correlates the exact source and recipient,
logical source incarnation, controllers, public characteristics, assigned,
dealt, and prevented amounts, combat step, and first-strike-step status.
Programs for “this source” use `damage.dealt.self`; broader programs use
`damage.dealt` with declarative event conditions. Prevented and zero damage do
not dispatch the event.

Represented damage triggers remain pending while post-damage state-based
actions run. Any represented triggers discovered by those actions merge into
the same unstarted APNAP/controller-order batch before priority. This is not a
claim that arbitrary damage Oracle text is compiled: noncombat damage, the
complete CR 120.4 replacement/prevention/result sequence, excess damage, and
trigger-on-trigger placement remain explicit untrusted dependencies.

## Trust

`trusted` means the declared behavior is reviewed and characterized for this
implementation. `provisional` can support development characterization but
cannot make a material interaction eligible as conformance or release evidence.
`unresolved` fails closed in strict mode and requires future implementation.
Development arbitration can help author a reviewed fixture, but it is never
production legality. `intentionally_ignored` is only appropriate when the
omitted ability is demonstrably irrelevant to the recorded operation.

The executor accepts validated DSL operations only. The kernel selects programs
by Oracle/ability keys and runtime events, not printed-name branches. Runtime
placeholders such as `$controller` and `$target.0` are resolved against the
current stack object.

The browser-reported interaction pack follows the same rule. Its reviewed
Oracle-ID programs cover Sunscorched Desert's targeted entry damage and Orcish
Bowmasters' permanent resolution, entry/extra-draw triggers, and Amass Orcs.
`amass` and permanent `add_subtype` are reusable DSL operations: the executor
creates an Army only when necessary, delegates among multiple Armies, adds the
named creature type, and places counters. This is reusable mechanic coverage,
not a printed-name branch or a claim that arbitrary Amass variants are already
compiled.

## Version 0.8.0 exact-list closure

The pinned July 28, 2026 Zimone and Dina and Mishra, Eminent One lists each
preflight at 100 fully playable cards, with no partial or unresolved entries
and no expected arbiter calls. The closure is backed by deterministic
characterization scenarios and exact Oracle/rulings hashes in
`zzz-v080-exact-deck-closure.json`.

The final Mishra families include Daretti's loyalty, exchange, and emblem
return; its emblem effect now creates a typed public command-zone object and
binds the return trigger to that exact source. They also include Demonic
Junker's per-player destroy and Crew 2; both faces of Tithing Blade including
Craft; Transmute Artifact's staged sacrifice/search/payment; and Urza's
Saga's lore progression, granted abilities, restricted chapter-III search,
and final sacrifice. The exact-list pack also covers the remaining Zimone
engines, alternate/additional costs, restricted mana, copy/token engines,
linked choices, replacement effects, and turn-control effects.

This result is intentionally bounded to the two validated deck-list
fingerprints. It does not imply that similarly worded cards outside those
lists, arbitrary Oracle prose, continuous-effect layers, or every Commander
rules interaction are implemented.

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

This was not complete coverage of either 100-card deck at the time of the
0.6.0 release. Version 0.8.0 closes the two pinned exact lists; generated
preflight reports remain the authoritative inventory for any other snapshot.

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

At the 0.6.0 boundary, other activation conditions and complex tutors remained
unresolved rather than guessed. Version 0.8.0 supplies exact-list compilation
for those cards. The primary coordinator still never chooses a private search
result for the player.

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
| Zimone and Dina (`g5vt…`) | 100 | 0 | 0 | 0 | yes |
| Mishra, Eminent One (`armNI…`) | 100 | 0 | 0 | 0 | yes |

Those counts apply only to the validated July 28, 2026 fingerprints. Neither a
scripted turn-eight duel nor a duplicated-list Codex run is deck-quality or
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
