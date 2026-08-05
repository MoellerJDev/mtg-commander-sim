---
title: "Reusable rules piece matrix"
status: "generated"
authoritative_source: "coverage/reusable-piece-matrix.json.gz"
verified: "b3c487cd6ba0c3a239d5fc25633f5f261efbefb03bfebef46a5961626eeaba2f"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Reusable rules piece matrix

Current Oracle IR material ability and residual spans plus all registered capabilities, mechanics, handlers, components, and pinned rule references. This inventories current source relations without claiming universal runtime completion.

Counts official ruling presence by Oracle ID. Ruling prose is not yet behaviorally classified, so these counts are composition evidence rather than coverage claims.

## Snapshot

- Profile: `commander_review`
- Ontology: `reusable-pieces-v1`
- Pieces: 985
- Cards indexed: 31,623
- Material abilities classified: 59,963
- Unclassified material spans: 0
- Mapped pinned rules: 582 / 3,300
- Applicable piece pairs: 19,583
- Covered piece pairs: 3

## Ontology classes

| Class | Pieces |
|---|---:|
| `actions_permissions` — Actions, permissions, and prohibitions | 4 |
| `card_forms` — Card types and specialized forms | 3 |
| `choices_continuations` — Modes, targets, choices, and continuations | 6 |
| `combat` — Combat | 4 |
| `compiler_cardprogram` — Compiler and CardProgram pieces | 187 |
| `continuous_effects` — Static abilities and continuous effects | 16 |
| `costs_mana` — Costs and mana | 6 |
| `events_mutations` — Typed events and mutations | 57 |
| `keyword_mechanics` — Keyword actions and keyword abilities | 577 |
| `multiplayer_commander` — Multiplayer, Commander, and profile pieces | 1 |
| `object_identity` — Object identity and lifetime | 26 |
| `one_shot_effects` — One-shot semantic effects | 79 |
| `players_format` — Players, relationships, and format state | 1 |
| `proposals` — Casting and activation proposals | 2 |
| `quantities` — Quantity and value expressions | 1 |
| `references` — References | 1 |
| `replacement_prevention` — Replacement and prevention | 12 |
| `triggers` — Triggers | 2 |

## Universal systems

| System | Status | Pieces | Blocking pieces |
|---|---|---:|---:|
| `action_legality_casting_activation_costs_mana` | `inventoried` | 12 | 5 |
| `combat` | `compositional` | 4 | 0 |
| `derived_characteristics_static_layers` | `inventoried` | 16 | 5 |
| `generic_triggers_stack_placement` | `inventoried` | 2 | 2 |
| `multiplayer_player_leaving_commander` | `represented` | 2 | 0 |
| `objects_identity_zones_faces_copies` | `represented` | 29 | 0 |
| `replacement_prevention` | `inventoried` | 12 | 5 |
| `state_turn_loops_stabilization` | `inventoried` | 0 | 0 |
| `targets_modes_searches_references_choices` | `inventoried` | 8 | 6 |
| `typed_transactions_events_mutations` | `inventoried` | 136 | 53 |

## Highest current blocker leverage

| Piece | Class | Residuals | Sole blockers | Expected cards | Runtime | Assurance |
|---|---|---:|---:|---:|---|---|
| `residual.continuous_layer.continuous-effect-layers-and-dependencies` | `continuous_effects` | 9,684 | 2,889 | 2,889 | `absent` | `untested` |
| `residual.activated_effect.unparsed-clause-grammar` | `one_shot_effects` | 2,880 | 695 | 695 | `absent` | `untested` |
| `residual.effect_clause.unparsed-clause-grammar` | `one_shot_effects` | 2,943 | 483 | 483 | `absent` | `untested` |
| `residual.mechanic_dependency.cr-611-continuous-effects` | `keyword_mechanics` | 565 | 152 | 152 | `absent` | `untested` |
| `residual.effect_clause.deal-damage` | `one_shot_effects` | 1,048 | 130 | 130 | `absent` | `untested` |
| `residual.mechanic_dependency.cr-509-declare-blockers-step` | `keyword_mechanics` | 421 | 124 | 124 | `absent` | `untested` |
| `residual.mechanic_dependency.cr-614-replacement-effects` | `keyword_mechanics` | 531 | 121 | 121 | `absent` | `untested` |
| `residual.effect_clause.return` | `one_shot_effects` | 754 | 108 | 108 | `absent` | `untested` |
| `residual.mechanic_dependency.cr-111-tokens` | `keyword_mechanics` | 311 | 104 | 104 | `absent` | `untested` |
| `residual.effect_clause.destroy-target` | `one_shot_effects` | 590 | 89 | 89 | `absent` | `untested` |
| `residual.activated_effect.deal-damage` | `one_shot_effects` | 525 | 85 | 85 | `absent` | `untested` |
| `residual.mechanic_dependency.cr-115-targets` | `keyword_mechanics` | 777 | 79 | 79 | `absent` | `untested` |
| `residual.activated_effect.return` | `one_shot_effects` | 451 | 78 | 78 | `absent` | `untested` |
| `residual.activated_effect.tap-state` | `one_shot_effects` | 322 | 74 | 74 | `absent` | `untested` |
| `residual.effect_clause.exile` | `one_shot_effects` | 1,062 | 72 | 72 | `absent` | `untested` |
| `residual.mechanic_dependency.cr-121-drawing-a-card` | `keyword_mechanics` | 205 | 71 | 71 | `absent` | `untested` |
| `residual.effect_clause.tap-state` | `one_shot_effects` | 387 | 67 | 67 | `absent` | `untested` |
| `residual.keyword_dependency.trample` | `keyword_mechanics` | 974 | 62 | 62 | `absent` | `untested` |
| `residual.activated_effect.create-token` | `one_shot_effects` | 487 | 57 | 57 | `absent` | `untested` |
| `residual.effect_clause.look-reveal` | `one_shot_effects` | 579 | 55 | 55 | `absent` | `untested` |
| `residual.activated_effect.put-counter` | `one_shot_effects` | 408 | 53 | 53 | `absent` | `untested` |
| `residual.keyword_dependency.first-strike` | `keyword_mechanics` | 363 | 53 | 53 | `absent` | `untested` |
| `residual.effect_clause.counter` | `one_shot_effects` | 276 | 50 | 50 | `absent` | `untested` |
| `residual.keyword_dependency.deathtouch` | `keyword_mechanics` | 336 | 45 | 45 | `absent` | `untested` |
| `residual.effect_clause.create-token` | `one_shot_effects` | 729 | 42 | 42 | `absent` | `untested` |
| `residual.effect_clause.destroy-mass` | `one_shot_effects` | 201 | 42 | 42 | `absent` | `untested` |
| `residual.effect_clause.draw` | `one_shot_effects` | 600 | 41 | 41 | `absent` | `untested` |
| `residual.activated_effect.search` | `one_shot_effects` | 236 | 41 | 41 | `absent` | `untested` |
| `residual.keyword_dependency.cycling` | `keyword_mechanics` | 297 | 40 | 40 | `absent` | `untested` |
| `residual.keyword_dependency.defender` | `keyword_mechanics` | 304 | 38 | 38 | `absent` | `untested` |

## Boundary

Inventory and classification are not implementation or trust. Universal systems remain conservatively below snapshot-complete until all required rules, pieces, rulings, and interactions close.
