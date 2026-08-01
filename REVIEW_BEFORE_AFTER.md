---
title: "Review output before and after 0.4.0"
status: "historical"
authoritative_source: "0.4 review fixture"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "maintainers researching the decision-opportunity regression"
maintenance: "hand-maintained"
---

# Review output before and after 0.4.0

The migrated v2 fixture remains useful as a negative example. It lacks native
payloads, historical legal-action catalogs, and reliable provider-call
evidence. Its review therefore says reasons and alternatives are incomplete and
keeps provider invocations unknown.

Before, a compact event could only establish:

```text
Turn 2
- B played B99.
- B cast B51.
```

The native 0.4.0 fixture renders the structured record without inferring
unrecorded intent:

```text
Turn 1 — A
- A played Flooded Strand untapped.
- A activated Flooded Strand (ab1).
- A searched for Breeding Pool; it entered tapped.
- Plan: FIX_COLORS
- Reason: Use the fetchland while its resolution-time typed-land search is available.

Turn 2 — B
- B played Island untapped.
- B cast Sensei's Divining Top from hand for {U}, using Island for {U}.
- Plan: DEVELOP_ENGINE
- Reason: Deploy an affordable engine piece from the complete legal-action catalog.
```

The exact generated examples are:

- `run/migrated-live-duel/review.md`
- `run/native-zimone-vs-mishra/review.md`

The native review also reports replay status, semantic trust, actual provider
invocations, unavailable token measurements as `null`, fetch/search selections,
land-entry conflicts, and byte totals using the definitions in
`GAME_RECORD.md`. It does not turn an unfinished scripted pilot test into
matchup evidence.
