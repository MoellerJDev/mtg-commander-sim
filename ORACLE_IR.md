# Typed Oracle IR

## Purpose

The Oracle compiler is the scaling path for decks that were not known when
the engine was written. It turns every pinned Oracle face into source-spanned
typed nodes. Common wording lowers to reusable effect operations; it does not
create a new engine branch for each printed card.

The compiler is conservative:

- a template must match the whole material ability
- costs and effects are represented separately
- every node records face, line, character offsets, template, mechanics,
  targets, and residual IDs
- every card records Oracle, compiler, and semantic hashes
- any unparsed material text is a residual
- a lowerable node is not exact until all mechanic dependencies are trusted

## Status meanings

- `exact`: every material span is compiled and every dependency supplied to
  the compiler is trusted
- `partial`: at least one node is lowerable, but a material residual or
  untrusted dependency remains
- `unresolved`: no material node can currently be lowered safely

Textless cards can be exact without a semantic program. A recognized Flying
line is currently partial because its contract still lists layer/copy
blockers. A simple Lightning Bolt template is lowerable, but remains partial
until damage and targeting dependencies are trusted.

## Runtime behavior

`CommanderSession.create` scans unique cards in all loaded decks. Lowerable
spell, activated-ability, and simple self-trigger nodes are registered under
stable keys alongside hand-authored semantics. Existing reviewed programs win
on key collision or equivalent trigger event ownership.

Generated spell, activated-ability, and simple self-trigger programs are
currently:

- `trust_level = provisional`
- `requires_arbiter = true`
- pinned to Oracle and rulings hashes
- annotated with compiler, template, source span, semantic hash, and
  dependency status

Reviewed event handlers shadow equivalent generated triggers. This prevents a
reviewed card from triggering twice merely because its reviewed ability key
uses a different author-defined name. Simple unconditional "enters tapped"
text is applied by the authoritative zone-move path rather than by a pilot or
generated effect.

Thus an unfamiliar deck can be parsed and partially compiled automatically,
but an unreviewed match cannot silently execute guessed rules. A
`trusted_only` arena stops or withholds the action; an arbitration-enabled run
routes it to the neutral arbiter.

## Commands

```bash
simctl oracle parse "Lightning Bolt" --db data/scryfall-current.sqlite3
simctl oracle explain "Rest in Peace" --db data/scryfall-current.sqlite3
simctl oracle residuals --db data/scryfall-current.sqlite3
simctl oracle coverage --db data/scryfall-current.sqlite3
simctl oracle coverage --commander-legal-only \
  --db data/scryfall-current.sqlite3
```

Coverage output measures the complete pinned corpus. Tracked examples omit
Oracle prose and retain identity, source span, reason, blocker, and text hash.

## Card-specific exceptions

Some cards have linked abilities, unusual copy rules, or intentionally unique
instructions that a general grammar cannot safely express. Those may use a
reviewed semantic override. The override must pin:

- Oracle ID and face/ability
- Oracle and rulings hashes
- compiler residual/failure category
- CR/mechanic dependencies
- reviewer and implementation version
- deterministic positive, negative, interaction, and replay tests

This is compiled data for an exception, not permission to add a printed-name
condition to the turn, cost, target, layer, replacement, zone, or combat
kernel.
