# Commander-legal Oracle IR coverage

- Compiler: `oracle-ir-v11`
- Commander-legal Oracle IDs in this local snapshot: 31,623
- Faces: 32,431
- Exact: 338 (1.0688%)
- Partially lowerable: 14,663
- Unresolved: 16,622
- Material residuals: 61,213
- Current snapshot complete: false

The low exact count is expected: recognized cards remain partial until their
mechanic dependencies are trusted. This report is a corpus gate, not an
estimate of how often cards appear in Commander decks.

This compiler revision adds the same eight Commander-legal current-turn
declaration occurrences across six generic templates. Generic leading-name
self-reference normalization also classifies additional declaration text fail
closed. The Commander-legal declaration-restriction residual count is 153 and
the declaration-cost residual count is 10; no mechanic trust or corpus-
completeness promotion is claimed.
