# Oracle IR coverage

- Compiler: `oracle-ir-v8`
- Oracle IDs: 38,484
- Faces: 41,701
- Exact: 2,959 (7.6889%)
- Partially lowerable: 16,039
- Unresolved: 19,486
- Material residuals: 69,890
- Current snapshot complete: false

`exact` includes textless cards. Recognized templates with untrusted mechanic
dependencies remain partial. See `oracle-coverage.json` for counts by residual
kind and template.

This compiler revision lowers 20 exact declaration-composition, attacking-
alone, source-controller target, and per-player attack-cap occurrences. The
declaration-restriction residual count is 165; recognized nodes remain partial
while CR 508/509 mechanic contracts are untrusted.
