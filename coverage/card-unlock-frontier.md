---
title: "Commander card-unlock frontier"
status: "generated"
authoritative_source: "coverage/card-unlock-frontier.json.gz"
verified: "5cf9c019cf0f85c4fd0598057e4be5790a5141237e0ab488a253b7d7c515a05d"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Commander card-unlock frontier

This generated report ranks minimum known compiler and rules blockers for the pinned Commander-legal card snapshot. It is not a claim of complete Comprehensive Rules coverage.

## Snapshot

- Cards considered: 31,623
- Oracle states: `{"exact":2206,"partial":13260,"unresolved":16157}`
- CardProgram states: `{"residual":29417,"trusted":2206}`
- Hard construction failures: 0
- Frontier fingerprint: `5cf9c019cf0f85c4fd0598057e4be5790a5141237e0ab488a253b7d7c515a05d`

## Highest-leverage single families

| Family | Occurrences | Cards | Sole-blocker cards | Exact abilities | Readiness | Risk |
|---|---:|---:|---:|---:|---|---|
| `continuous_layer:continuous-effect-layers-and-dependencies` | 9,578 | 7,720 | 3,311 | 9,578 | missing_lowering | very_high |
| `mechanic_dependency:cr-611-continuous-effects` | 567 | 520 | 187 | 346 | partial | high |
| `mechanic_dependency:cr-614-replacement-effects` | 531 | 531 | 165 | 531 | partial | high |
| `mechanic_dependency:cr-509-declare-blockers-step` | 421 | 416 | 138 | 385 | partial | high |
| `effect_clause:deal-damage` | 1,007 | 976 | 115 | 253 | missing_lowering | high |
| `effect_clause:return` | 740 | 713 | 113 | 254 | missing_lowering | high |
| `mechanic_dependency:cr-111-tokens` | 325 | 320 | 111 | 325 | partial | high |
| `effect_clause:destroy-target` | 588 | 555 | 97 | 254 | missing_lowering | high |
| `effect_clause:exile` | 1,039 | 990 | 93 | 455 | missing_lowering | high |
| `activated_effect:deal-damage` | 514 | 485 | 87 | 172 | missing_lowering | high |
| `mechanic_dependency:cr-115-targets` | 365 | 347 | 85 | 162 | missing_contract | high |
| `activated_effect:return` | 450 | 449 | 80 | 168 | missing_lowering | high |
| `activated_effect:tap-state` | 322 | 311 | 75 | 166 | missing_lowering | high |
| `effect_clause:tap-state` | 387 | 378 | 71 | 147 | missing_lowering | high |
| `activated_effect:unparsed-regenerate-this-creature` | 149 | 148 | 70 | 129 | missing_lowering | high |
| `effect_clause:unparsed-target-creature-gets` | 217 | 214 | 68 | 141 | missing_lowering | high |
| `activated_effect:unparsed-this-creature-gets` | 132 | 127 | 64 | 86 | missing_lowering | high |
| `activated_effect:put-counter` | 393 | 382 | 58 | 175 | missing_lowering | high |
| `effect_clause:look-reveal` | 574 | 569 | 57 | 109 | missing_lowering | high |
| `activated_effect:create-token` | 475 | 464 | 55 | 196 | missing_lowering | high |
| `activated_effect:search` | 236 | 233 | 52 | 69 | missing_lowering | high |
| `activated_effect:unparsed-target-creature-gains` | 98 | 94 | 49 | 81 | missing_lowering | high |
| `effect_clause:create-token` | 723 | 706 | 44 | 159 | missing_lowering | high |
| `effect_clause:sacrifice` | 387 | 383 | 42 | 133 | missing_lowering | high |
| `effect_clause:draw` | 599 | 591 | 42 | 127 | missing_lowering | high |

## Highest-leverage bounded bundles

| Families | Exact cards | Exact abilities | Residuals |
|---|---:|---:|---:|
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-509-declare-blockers-step` | 3,724 | 10,309 | 10,309 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-614-replacement-effects` | 3,716 | 10,455 | 10,455 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, mechanic_dependency:cr-509-declare-blockers-step` | 3,689 | 10,494 | 10,494 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-111-tokens` | 3,678 | 10,249 | 10,249 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, mechanic_dependency:cr-115-targets` | 3,665 | 10,173 | 10,173 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, mechanic_dependency:cr-111-tokens` | 3,649 | 10,288 | 10,288 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, mechanic_dependency:cr-111-tokens` | 3,647 | 10,434 | 10,434 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:deal-damage` | 3,644 | 10,177 | 10,177 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:return` | 3,643 | 10,178 | 10,178 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:destroy-target` | 3,626 | 10,178 | 10,178 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, effect_clause:exile` | 3,623 | 10,379 | 10,379 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:tap-state` | 3,622 | 10,090 | 10,129 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:return` | 3,621 | 10,092 | 10,134 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:unparsed-regenerate-this-creature` | 3,619 | 10,053 | 10,069 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:deal-damage` | 3,618 | 10,096 | 10,145 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, effect_clause:deal-damage` | 3,617 | 10,216 | 10,216 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-509-declare-blockers-step, effect_clause:return` | 3,616 | 10,217 | 10,217 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, effect_clause:return` | 3,613 | 10,363 | 10,363 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-614-replacement-effects, effect_clause:deal-damage` | 3,613 | 10,362 | 10,362 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-611-continuous-effects, activated_effect:create-token` | 3,602 | 10,120 | 10,193 |

## Hard construction failures

- None in the pinned Commander-legal snapshot.

## Boundary

This is a minimum-known-blocker frontier for the pinned Commander-legal snapshot. It does not prove complete Comprehensive Rules behavior.
The JSON artifact contains every card, every represented material ability, canonical blocker sets, dependency categories, and the bounded one/two/three-family evaluation.
