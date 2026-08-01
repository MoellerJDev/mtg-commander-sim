---
title: "Oracle IR coverage snapshot"
status: "historical"
authoritative_source: "archived coverage/oracle-coverage.json snapshot"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "compiler contributors researching prior compiler output"
maintenance: "hand-maintained"
---

# Oracle IR coverage

- Compiler: `oracle-ir-v11`
- Oracle IDs: 38,484
- Faces: 41,701
- Exact: 2,959 (7.6889%)
- Partially lowerable: 16,092
- Unresolved: 19,433
- Material residuals: 69,890
- Current snapshot complete: false

`exact` includes textless cards. Recognized templates with untrusted mechanic
dependencies remain partial. See `oracle-coverage.json` for counts by residual
kind and template.

This compiler revision adds eight current-turn declaration occurrences across
six generic templates: creature/noncreature spells cast, controlled creature
deaths, opponents dealt damage, prior direct-player attacks, and opponents
that cast a spell. Generic leading-name self-reference normalization also
classifies additional declaration text fail closed. The declaration-
restriction residual count is 170 and the declaration-cost residual count is
11; recognized nodes remain partial while their broader mechanic dependencies
are untrusted.
