# Commander-legal Oracle IR coverage

- Compiler: `oracle-ir-v10`
- Commander-legal Oracle IDs in this local snapshot: 31,623
- Faces: 32,431
- Exact: 338 (1.0688%)
- Partially lowerable: 14,642
- Unresolved: 16,643
- Material residuals: 61,213
- Current snapshot complete: false

The low exact count is expected: recognized cards remain partial until their
mechanic dependencies are trusted. This report is a corpus gate, not an
estimate of how often cards appear in Commander decks.

This compiler revision additionally lowers 36 Commander-legal exact-template
`you become the monarch` occurrences and four public monarch/poison
declaration templates. The Commander-legal declaration-restriction residual
count is 145 and the declaration-cost residual count is 10; no mechanic trust
or corpus-completeness promotion is claimed.
