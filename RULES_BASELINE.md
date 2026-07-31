# Rules baseline

The kernel is aligned to the Magic Comprehensive Rules effective June 19, 2026 and the local Scryfall bulk files dated July 28, 2026.

Implemented rule families include:

- 103.5 — London mulligan declarations in turn order and redraw procedure
- 103.5c — first multiplayer mulligan free
- 103.8c — first player draws in ordinary multiplayer
- 117 — timing, priority, successive passes, and stabilization before priority
- 603.7 — native delayed triggered abilities for implemented event windows
- 704 — core state-based actions
- 800.4 — players leaving multiplayer games
- 802 — attacking multiple players and defender-order blocking
- 903 — Commander life, command-zone, tax, and commander-damage foundations

The conformance ledger additionally source-reviews the CR 400–408 zone
families, CR 500–514 turn/combat/ending families, and selected CR 120, 210,
310, 600–609, 614–616, and 704 families. A reviewed family may contain passing,
definition-only, and explicitly blocked records; review is not a completeness
claim. Current generated totals are 557 reviewed out of 3,300 rules and 49
partial out of 425 mechanics.

The Comprehensive Rules remain authoritative. `ARCHITECTURE.md` documents the
implemented subset. Trusted-only product play fails closed on uncompiled
material semantics rather than guessing; the neutral arbiter path is retained
only as a development adapter and is never an AI rules authority.
