# Oracle IR coverage

- Compiler: `oracle-ir-v9`
- Oracle IDs: 38,484
- Faces: 41,701
- Exact: 2,959 (7.6889%)
- Partially lowerable: 16,042
- Unresolved: 19,483
- Material residuals: 69,890
- Current snapshot complete: false

`exact` includes textless cards. Recognized templates with untrusted mechanic
dependencies remain partial. See `oracle-coverage.json` for counts by residual
kind and template.

This compiler revision additionally lowers three exact Oracle occurrences: a
source-specific attack maximum, a defending-player shared-subtype blocking
condition, and a planeswalker-only fixed-mana attack tax. The declaration-
restriction residual count is 163 and the declaration-cost residual count is
11; recognized nodes remain partial while their broader CR 508/509 mechanic
contracts are untrusted.
