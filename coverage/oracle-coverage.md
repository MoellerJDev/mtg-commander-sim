# Oracle IR coverage

- Compiler: `oracle-ir-v10`
- Oracle IDs: 38,484
- Faces: 41,701
- Exact: 2,959 (7.6889%)
- Partially lowerable: 16,068
- Unresolved: 19,457
- Material residuals: 69,890
- Current snapshot complete: false

`exact` includes textless cards. Recognized templates with untrusted mechanic
dependencies remain partial. See `oracle-coverage.json` for counts by residual
kind and template.

This compiler revision additionally lowers 36 exact-template `you become the
monarch` occurrences and four public monarch/poison declaration templates. The
declaration-restriction residual count is 160 and the declaration-cost
residual count is 11; recognized nodes remain partial while their broader
mechanic dependencies are untrusted.
