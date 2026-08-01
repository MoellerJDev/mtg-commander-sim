# Commander-legal Oracle IR coverage

- Compiler: `oracle-ir-v9`
- Commander-legal Oracle IDs in this local snapshot: 31,623
- Faces: 32,431
- Exact: 338 (1.0688%)
- Partially lowerable: 14,616
- Unresolved: 16,669
- Material residuals: 61,213
- Current snapshot complete: false

The low exact count is expected: recognized cards remain partial until their
mechanic dependencies are trusted. This report is a corpus gate, not an
estimate of how often cards appear in Commander decks.

This compiler revision additionally lowers three Commander-legal Oracle
occurrences: a source-specific attack maximum, a defending-player shared-
subtype blocking condition, and a planeswalker-only fixed-mana attack tax. The
Commander-legal declaration-restriction residual count is 148 and the
declaration-cost residual count is 10; no mechanic trust or corpus-
completeness promotion is claimed.
