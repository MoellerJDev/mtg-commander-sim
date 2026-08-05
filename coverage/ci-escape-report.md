---
title: "CI escape report"
status: "generated"
authoritative_source: "platform/ci-escape-source.json"
verified: "c5dfdb70a2466b76b283f1d774c61947d3a8868f58ba4f5e6d201e55cefd2472"
audience: "maintainers and contributors"
maintenance: "generated"
---

# CI escape report

This report classifies observed deterministic failures that escaped the local quick gate. Null measurements are unavailable and are never estimated.

## Summary

- Escapes: 8
- Deterministic escapes: 5
- Current missing impact edges: 0
- Known flaky tests: 0
- Average pushes per merged PR: None
- Exact-head pass rate: 1.0
- Average observed critical path: 840.5 seconds
- Average Slot B inactive time: None

## Escapes

| ID | Run | Category | Impact edge | Resolution |
|---|---:|---|---|---|
| `ci-20260804-01` | [30916877307](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30916877307) | `missing_affected_test` | `added` | The fixture was made portable and the compiler family remains explicitly routed to compiler-cardprogram and generated validation. |
| `ci-20260804-02` | [30918937537](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30918937537) | `generated_artifact_drift` | `added` | Platform and coverage sources now select their exact generated freshness checks through the path policy. |
| `ci-20260804-03` | [30930608139](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30930608139) | `source_correctness` | `added` | Protection, compiler, damage, and continuous-effect paths now select every affected functional shard through explicit rules. |
| `ci-20260804-04` | [30931679921](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30931679921) | `source_correctness` | `added` | The exact protection consumers are covered by both replacement and damage shards in the machine-readable policy. |
| `ci-20260804-05` | [30940720886](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30940720886) | `browser_integration` | `not_applicable` | The production auto-pass race was fixed and the public full-browser gate remains authoritative for headless journeys. |
| `ci-20260804-06` | [30952062448](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30952062448) | `flaky_test` | `not_applicable` | The journey now accepts either a form-backed choice or an authoritative immediate-action revision while preserving forced form submission when needed. |
| `ci-20260805-07` | [30974377805](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30974377805) | `flaky_test` | `not_applicable` | The journeys now wait for authoritative projected results across persisted transitions and retain bounded whole-test budgets; both focused witnesses pass headlessly against the CI compact database. |
| `ci-20260805-08` | [30982463835](https://github.com/MoellerJDev/mtg-commander-sim/actions/runs/30982463835) | `flaky_test` | `not_applicable` | One shared coordinator now advances only the currently authorized server pass until a strategic decision, seat-qualified opportunity, or projected result is reached; the two witnesses pass together in one headless worker against the CI compact database. |

## Measurement limitations

- Average pushes per merged PR: GitHub retained workflow runs are not equivalent to pushes, so push counts remain null rather than estimated.
- Slot B inactive time: GitHub Actions does not observe local worktree activity, so this value remains null rather than estimated.
