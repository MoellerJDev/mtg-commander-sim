---
title: "Commander card-unlock frontier"
status: "generated"
authoritative_source: "coverage/card-unlock-frontier.json.gz"
verified: "38a7ac0f5619b34f44b88492e88ad1fdfe45fa7427f85302c313c33974c756fa"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Commander card-unlock frontier

This generated report ranks minimum known compiler and rules blockers for the pinned Commander-legal card snapshot. It is not a claim of complete Comprehensive Rules coverage.

## Snapshot

- Cards considered: 31,623
- Oracle states: `{"exact":1043,"partial":14324,"unresolved":16256}`
- CardProgram states: `{"residual":30580,"trusted":1043}`
- Hard construction failures: 0
- Frontier fingerprint: `38a7ac0f5619b34f44b88492e88ad1fdfe45fa7427f85302c313c33974c756fa`

## Highest-leverage single families

| Family | Occurrences | Cards | Sole-blocker cards | Exact abilities | Readiness | Risk |
|---|---:|---:|---:|---:|---|---|
| `continuous_layer:continuous-effect-layers-and-dependencies` | 9,684 | 7,798 | 2,718 | 9,684 | missing_lowering | very_high |
| `mechanic_dependency:cr-605-mana-abilities` | 1,990 | 1,762 | 384 | 1,990 | partial | high |
| `effect_clause:deal-damage` | 1,122 | 1,089 | 154 | 364 | missing_lowering | high |
| `mechanic_dependency:cr-611-continuous-effects` | 565 | 518 | 150 | 346 | partial | high |
| `mechanic_dependency:cr-509-declare-blockers-step` | 421 | 416 | 124 | 385 | partial | high |
| `effect_clause:return` | 754 | 727 | 108 | 254 | missing_lowering | high |
| `activated_effect:deal-damage` | 592 | 558 | 102 | 235 | missing_lowering | high |
| `mechanic_dependency:cr-111-tokens` | 311 | 306 | 100 | 311 | partial | high |
| `effect_clause:destroy-target` | 590 | 557 | 89 | 254 | missing_lowering | high |
| `mechanic_dependency:cr-115-targets` | 849 | 821 | 75 | 167 | missing_contract | high |
| `activated_effect:return` | 451 | 450 | 72 | 168 | missing_lowering | high |
| `effect_clause:exile` | 1,062 | 1,012 | 69 | 465 | missing_lowering | high |
| `effect_clause:unparsed-target-creature-gets` | 217 | 214 | 68 | 141 | missing_lowering | high |
| `effect_clause:tap-state` | 387 | 378 | 67 | 147 | missing_lowering | high |
| `activated_effect:tap-state` | 322 | 311 | 66 | 166 | missing_lowering | high |
| `keyword_dependency:trample` | 974 | 968 | 60 | 907 | partial | medium |
| `activated_effect:unparsed-this-creature-gets` | 132 | 127 | 56 | 86 | missing_lowering | high |
| `effect_clause:look-reveal` | 579 | 574 | 55 | 109 | missing_lowering | high |
| `keyword_dependency:flash` | 592 | 591 | 52 | 592 | missing_contract | medium |
| `keyword_dependency:first-strike` | 363 | 360 | 52 | 327 | partial | medium |
| `activated_effect:unparsed-regenerate-this-creature` | 149 | 148 | 51 | 129 | missing_lowering | high |
| `effect_clause:counter` | 276 | 274 | 50 | 96 | missing_lowering | high |
| `activated_effect:create-token` | 487 | 476 | 49 | 204 | missing_lowering | high |
| `activated_effect:put-counter` | 408 | 397 | 47 | 184 | missing_lowering | high |
| `effect_clause:create-token` | 729 | 712 | 42 | 159 | missing_lowering | high |

## Highest-leverage bounded bundles

| Families | Exact cards | Exact abilities | Residuals |
|---|---:|---:|---:|
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, keyword_dependency:trample` | 3,443 | 12,581 | 12,581 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, mechanic_dependency:cr-509-declare-blockers-step` | 3,401 | 12,059 | 12,059 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, mechanic_dependency:cr-611-continuous-effects` | 3,400 | 12,020 | 12,020 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, effect_clause:deal-damage` | 3,377 | 12,038 | 12,038 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, mechanic_dependency:cr-111-tokens` | 3,360 | 11,985 | 11,985 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, keyword_dependency:flash` | 3,358 | 12,266 | 12,266 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, keyword_dependency:first-strike` | 3,338 | 12,001 | 12,001 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, effect_clause:return` | 3,332 | 11,928 | 11,928 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, activated_effect:deal-damage` | 3,332 | 11,909 | 11,973 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, activated_effect:return` | 3,314 | 11,842 | 11,884 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, effect_clause:destroy-target` | 3,312 | 11,928 | 11,928 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, activated_effect:tap-state` | 3,309 | 11,840 | 11,879 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, keyword_dependency:deathtouch` | 3,308 | 11,975 | 11,975 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, keyword_dependency:defender` | 3,304 | 11,970 | 11,970 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, activated_effect:create-token` | 3,300 | 11,878 | 11,955 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, mechanic_dependency:cr-121-drawing-a-card` | 3,299 | 11,868 | 11,868 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, mechanic_dependency:cr-115-targets` | 3,298 | 11,841 | 11,841 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, effect_clause:exile` | 3,294 | 12,139 | 12,139 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, activated_effect:unparsed-regenerate-this-creature` | 3,292 | 11,803 | 11,819 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, effect_clause:tap-state` | 3,291 | 11,821 | 11,821 |

## Hard construction failures

- None in the pinned Commander-legal snapshot.

## Boundary

This is a minimum-known-blocker frontier for the pinned Commander-legal snapshot. It does not prove complete Comprehensive Rules behavior.
The JSON artifact contains every card, every represented material ability, canonical blocker sets, dependency categories, and the bounded one/two/three-family evaluation.
