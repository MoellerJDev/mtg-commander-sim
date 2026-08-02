---
title: "Compiler coverage status"
status: "generated"
authoritative_source: "coverage/architecture-audit.json"
verified: "6c09dab765e615610f697a7a850bb6502093f0a0"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Compiler coverage status

This generated report describes only the pinned Oracle corpus and current compiler. Exact compilation is not the same as complete game-behavior proof.

## Current representation

- Compiler: `oracle-ir-v13`
- Runtime IR: OracleCardIR lowered to canonical CardProgram V2 with a derived SemanticProgram compatibility index
- CardProgram V2 present: true
- Compiler module: 1,814 physical / 1,744 logical lines

## Canonical CardProgram

- Schema version: `2`
- Schema: `schemas/card-program-v2.schema.json`
- Required card fields: 14
- Required per-ability fields: 27
- Model: `mtg_commander_sim/card_programs/model.py`
- Generated/reviewed adapter: `mtg_commander_sim/card_programs/adapters.py`
- Runtime validator: `mtg_commander_sim/card_programs/validation.py`
- Canonical reviewed registry CardPrograms: 143
- Intrinsic strict-capability-ready CardPrograms: 0
- Trust bases: `{"legacy_reviewed": 143}`

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

- Registry schema/version: `1/10`
- Pinned rules effective date: `2026-06-19`
- Registry fingerprint: `081fc22b30b49bd9251c1339fa429b61d122d55b20625796f9c8c94c024058c5`
- Evidence fingerprint: `ff02b43111dec059b7cf22364cf6982894e986643d4fa6d634682823e37ffdd2`
- Explicit evidence declarations: 189
- Capability records: 30
- Trusted records: 17
- Blocked records: 4
- Dependency fail-closed statuses: `{"not_applicable": 11, "not_run": 3, "passed": 16}`
- Implementation mutation statuses: `{"killed": 21, "not_run": 9}`

| Broad aggregate | Capability records | Trusted | Blocked members |
|---|---:|---:|---|
| `cr-121-drawing-a-card` | 1 | false | `zone.draw.library_to_hand` |
| `cr-120-damage` | 18 | false | `damage.combat.excess`, `damage.prevention.order`, `damage.replacement.order`, `damage.trigger.noncombat` |
| `cr-725-the-monarch` | 1 | false | `variant.monarch.designate` |
| `cr-903-commander` | 1 | true | none |
| `cr-111-tokens` | 1 | false | `token.creation.additional_replacement` |
| `cr-614-replacement-effects` | 1 | false | `zone.change.destination_replacement` |
| `cr-613-continuous-effects` | 1 | false | `continuous.power_toughness.fixed_anthem` |
| `tap-and-untap` | 3 | false | `permanent.tap.effect`, `permanent.untap.all_creatures`, `permanent.untap.effect` |

## Pinned corpus accounting

| Scope | Oracle IDs | Exact | Partial | Unresolved | Material residuals | Complete |
|---|---:|---:|---:|---:|---:|---:|
| Full Oracle | 38,484 | 3,042 | 16,050 | 19,392 | 69,416 | false |
| Commander legal | 31,623 | 403 | 14,631 | 16,589 | 60,793 | false |

## Full-corpus residual kinds

| Kind | Count |
|---|---:|
| `dependency_contract` | 19,364 |
| `trigger` | 15,247 |
| `static_ability` | 12,093 |
| `spell_effect` | 11,391 |
| `effect` | 7,350 |
| `cost` | 2,009 |
| `replacement_effect` | 1,781 |
| `declaration_restriction` | 170 |
| `declaration_cost` | 11 |

## Semantic packs and implicit overrides

- Pack files: 15
- Program entries: 265
- Unique program keys: 253
- Duplicate keys resolved by pack order: 12
- Unique Oracle IDs represented: 143
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
