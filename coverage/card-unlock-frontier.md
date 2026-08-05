---
title: "Commander card-unlock frontier"
status: "generated"
authoritative_source: "coverage/card-unlock-frontier.json.gz"
verified: "f56370fbb01fd621a63d58510a488a60a9003d6c6caf16b7cf02c815f4048e02"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Commander card-unlock frontier

This generated report ranks minimum known compiler and rules blockers for the pinned Commander-legal card snapshot. It is not a claim of complete Comprehensive Rules coverage.

## Snapshot

- Cards considered: 31,623
- Oracle states: `{"exact":814,"partial":14553,"unresolved":16256}`
- CardProgram states: `{"residual":30809,"trusted":814}`
- Hard construction failures: 0
- Frontier fingerprint: `f56370fbb01fd621a63d58510a488a60a9003d6c6caf16b7cf02c815f4048e02`

## Highest-leverage single families

| Family | Occurrences | Cards | Sole-blocker cards | Exact abilities | Readiness | Risk |
|---|---:|---:|---:|---:|---|---|
| `continuous_layer:continuous-effect-layers-and-dependencies` | 9,684 | 7,798 | 2,337 | 9,684 | missing_lowering | very_high |
| `mechanic_dependency:cr-605-mana-abilities` | 1,990 | 1,762 | 369 | 1,990 | partial | high |
| `keyword_dependency:flying` | 3,155 | 3,133 | 192 | 2,842 | partial | medium |
| `effect_clause:deal-damage` | 1,122 | 1,089 | 154 | 364 | missing_lowering | high |
| `mechanic_dependency:cr-611-continuous-effects` | 565 | 518 | 111 | 346 | partial | high |
| `effect_clause:return` | 754 | 727 | 108 | 254 | missing_lowering | high |
| `mechanic_dependency:cr-509-declare-blockers-step` | 421 | 416 | 98 | 385 | partial | high |
| `mechanic_dependency:cr-111-tokens` | 311 | 306 | 90 | 311 | partial | high |
| `activated_effect:deal-damage` | 592 | 558 | 90 | 235 | missing_lowering | high |
| `effect_clause:destroy-target` | 590 | 557 | 89 | 254 | missing_lowering | high |
| `mechanic_dependency:cr-115-targets` | 849 | 821 | 73 | 167 | missing_contract | high |
| `effect_clause:unparsed-target-creature-gets` | 217 | 214 | 68 | 141 | missing_lowering | high |
| `effect_clause:tap-state` | 387 | 378 | 67 | 147 | missing_lowering | high |
| `effect_clause:exile` | 1,062 | 1,012 | 66 | 465 | missing_lowering | high |
| `activated_effect:return` | 451 | 450 | 63 | 168 | missing_lowering | high |
| `activated_effect:tap-state` | 322 | 311 | 59 | 166 | missing_lowering | high |
| `effect_clause:look-reveal` | 579 | 574 | 55 | 109 | missing_lowering | high |
| `keyword_dependency:trample` | 974 | 968 | 50 | 765 | partial | medium |
| `effect_clause:counter` | 276 | 274 | 50 | 96 | missing_lowering | high |
| `activated_effect:create-token` | 487 | 476 | 46 | 204 | missing_lowering | high |
| `activated_effect:unparsed-this-creature-gets` | 132 | 127 | 44 | 86 | missing_lowering | high |
| `activated_effect:put-counter` | 408 | 397 | 42 | 184 | missing_lowering | high |
| `effect_clause:create-token` | 729 | 712 | 42 | 159 | missing_lowering | high |
| `effect_clause:destroy-mass` | 201 | 190 | 42 | 88 | missing_lowering | high |
| `effect_clause:draw` | 600 | 592 | 41 | 127 | missing_lowering | high |

## Highest-leverage bounded bundles

| Families | Exact cards | Exact abilities | Residuals |
|---|---:|---:|---:|
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, keyword_dependency:flying` | 3,366 | 14,516 | 14,516 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, keyword_dependency:trample` | 3,072 | 13,391 | 13,391 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, mechanic_dependency:cr-611-continuous-effects` | 3,061 | 12,906 | 12,906 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, mechanic_dependency:cr-509-declare-blockers-step` | 3,042 | 12,911 | 12,911 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, effect_clause:deal-damage` | 3,019 | 12,890 | 12,890 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, keyword_dependency:trample` | 3,013 | 12,439 | 12,439 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, mechanic_dependency:cr-111-tokens` | 2,995 | 12,837 | 12,837 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, keyword_dependency:flash` | 2,994 | 13,118 | 13,118 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, keyword_dependency:first-strike` | 2,979 | 12,849 | 12,849 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, effect_clause:deal-damage` | 2,979 | 12,038 | 12,038 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, effect_clause:return` | 2,974 | 12,780 | 12,780 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, mechanic_dependency:cr-509-declare-blockers-step` | 2,974 | 12,059 | 12,059 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, activated_effect:deal-damage` | 2,964 | 12,761 | 12,825 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, mechanic_dependency:cr-611-continuous-effects` | 2,957 | 12,020 | 12,020 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, effect_clause:destroy-target` | 2,954 | 12,780 | 12,780 |
| `continuous_layer:continuous-effect-layers-and-dependencies, mechanic_dependency:cr-605-mana-abilities, mechanic_dependency:cr-111-tokens` | 2,951 | 11,985 | 11,985 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, keyword_dependency:reach` | 2,947 | 12,855 | 12,855 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, activated_effect:return` | 2,945 | 12,694 | 12,736 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, activated_effect:tap-state` | 2,944 | 12,692 | 12,731 |
| `continuous_layer:continuous-effect-layers-and-dependencies, keyword_dependency:flying, mechanic_dependency:cr-115-targets` | 2,940 | 12,693 | 12,693 |

## Hard construction failures

- None in the pinned Commander-legal snapshot.

## Boundary

This is a minimum-known-blocker frontier for the pinned Commander-legal snapshot. It does not prove complete Comprehensive Rules behavior.
The JSON artifact contains every card, every represented material ability, canonical blocker sets, dependency categories, and the bounded one/two/three-family evaluation.
