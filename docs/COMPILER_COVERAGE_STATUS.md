---
title: "Compiler coverage status"
status: "generated"
authoritative_source: "coverage/architecture-audit.json"
verified: "40241e6a7a4e77a3dab3df93c6a726b0f82186fb"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Compiler coverage status

This generated report describes only the pinned Oracle corpus and current compiler. Exact compilation is not the same as complete game-behavior proof.

## Current representation

- Compiler: `oracle-ir-v12`
- Runtime IR: OracleCardIR lowered to canonical CardProgram V2 with a derived SemanticProgram compatibility index
- CardProgram V2 present: true
- Compiler module: 1,832 physical / 1,765 logical lines

## Canonical CardProgram

- Schema version: `2`
- Schema: `schemas/card-program-v2.schema.json`
- Required card fields: 14
- Required per-ability fields: 27
- Model: `mtg_commander_sim/card_programs/model.py`
- Generated/reviewed adapter: `mtg_commander_sim/card_programs/adapters.py`
- Runtime validator: `mtg_commander_sim/card_programs/validation.py`
- Canonical reviewed registry CardPrograms: 137
- Intrinsic strict-capability-ready CardPrograms: 0
- Trust bases: `{"legacy_reviewed": 137}`

## Stages

| Stage | Current status | Evidence complete |
|---|---|---:|
| `normalization` | `interleaved` | true |
| `segmentation` | `interleaved` | true |
| `lexing` | `not_a_distinct_stage` | false |
| `parsing` | `regex_and_helper_parsers_interleaved` | true |
| `binding` | `not_a_distinct_stage` | false |
| `typing` | `partial_dataclass_ir` | true |
| `lowering` | `generated_abilities_extracted_and_aggregated_to_card_program_v2` | true |
| `capability_closure` | `fine_grained_damage_slice_with_legacy_fallback` | true |
| `residual_classification` | `implemented_interleaved` | true |
| `validation` | `card_program_v2_schema_roundtrip_source_trust_and_fingerprint_validation` | true |

## Fine-grained capability registry

- Registry schema/version: `1/7`
- Pinned rules effective date: `2026-06-19`
- Registry fingerprint: `e2e3e8ddeff69cb66f8a4c97e55104d59c530f85e828e1ab738767c790e7953d`
- Evidence fingerprint: `58bd8c8174a1f6c4530bd7edc5b2de751df510872214484d6f4b07f10f28b751`
- Explicit evidence declarations: 108
- Capability records: 23
- Trusted records: 8
- Blocked records: 7
- Dependency fail-closed statuses: `{"not_applicable": 10, "not_run": 6, "passed": 7}`
- Implementation mutation statuses: `{"killed": 11, "not_run": 12}`

| Broad aggregate | Capability records | Trusted | Blocked members |
|---|---:|---:|---|
| `cr-121-drawing-a-card` | 1 | false | `zone.draw.library_to_hand` |
| `cr-120-damage` | 13 | false | `damage.combat.excess`, `damage.prevention.order`, `damage.replacement.order`, `damage.result.infect`, `damage.result.lifelink`, `damage.result.wither`, `damage.trigger.noncombat` |
| `cr-725-the-monarch` | 1 | false | `variant.monarch.designate` |
| `cr-111-tokens` | 1 | false | `token.creation.additional_replacement` |
| `cr-614-replacement-effects` | 1 | false | `zone.change.destination_replacement` |
| `cr-613-continuous-effects` | 1 | false | `continuous.power_toughness.fixed_anthem` |
| `tap-and-untap` | 3 | false | `permanent.tap.effect`, `permanent.untap.all_creatures`, `permanent.untap.effect` |

## Pinned corpus accounting

| Scope | Oracle IDs | Exact | Partial | Unresolved | Material residuals | Complete |
|---|---:|---:|---:|---:|---:|---:|
| Full Oracle | 38,484 | 2,959 | 16,092 | 19,433 | 69,890 | false |
| Commander legal | 31,623 | 338 | 14,663 | 16,622 | 61,213 | false |

## Full-corpus residual kinds

| Kind | Count |
|---|---:|
| `dependency_contract` | 19,769 |
| `trigger` | 15,247 |
| `static_ability` | 12,150 |
| `spell_effect` | 11,392 |
| `effect` | 7,350 |
| `cost` | 2,009 |
| `replacement_effect` | 1,792 |
| `declaration_restriction` | 170 |
| `declaration_cost` | 11 |

## Semantic packs and implicit overrides

- Pack files: 12
- Program entries: 259
- Unique program keys: 247
- Duplicate keys resolved by pack order: 12
- Unique Oracle IDs represented: 137
- Card-specific operation names: 15
- Typed card-override boundary present: true
- Explicit typed overrides: 0

## Snapshot fingerprints

- Oracle SHA-256: `34d43820bb1b85be99267367969396c81a0bc387061dbd00882d1e78a5e84aa9`
- Rulings SHA-256: `edabb33f1354d577f4a337c182f1093519b3499e71cec304f7474e7b362c0537`
- Oracle updated: `2026-07-31T21:03:00.228+00:00`
- Rulings updated: `2026-07-31T21:00:39.181+00:00`

## Boundary

The current compiler is partial and interleaved. Full-corpus exactness is not claimed. Fine-grained closure currently covers only the reviewed base-damage spell slice; other nodes retain the broad-contract fallback. CardProgram V2 now provides canonical aggregation, validation, and replay pinning. Typed handlers and fully distinct compiler stages remain incremental work.
