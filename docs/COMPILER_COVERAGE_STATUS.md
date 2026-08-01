---
title: "Compiler coverage status"
status: "generated"
authoritative_source: "coverage/architecture-audit.json"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "compiler and rules contributors"
maintenance: "generated"
---

# Compiler coverage status

This generated report describes only the pinned Oracle corpus and current compiler. Exact compilation is not the same as complete game-behavior proof.

## Current representation

- Compiler: `oracle-ir-v12`
- Runtime IR: OracleCardIR plus SemanticProgram
- CardProgram V2 present: false
- Compiler module: 1,832 physical / 1,765 logical lines

## Stages

| Stage | Current status | Evidence complete |
|---|---|---:|
| `normalization` | `interleaved` | true |
| `segmentation` | `interleaved` | true |
| `lexing` | `not_a_distinct_stage` | false |
| `parsing` | `regex_and_helper_parsers_interleaved` | true |
| `binding` | `not_a_distinct_stage` | false |
| `typing` | `partial_dataclass_ir` | true |
| `lowering` | `interleaved_with_face_compilation` | true |
| `capability_closure` | `fine_grained_damage_slice_with_legacy_fallback` | true |
| `residual_classification` | `implemented_interleaved` | true |
| `validation` | `partial_program_registration_checks` | true |

## Fine-grained capability registry

- Registry schema/version: `1/1`
- Pinned rules effective date: `2026-06-19`
- Registry fingerprint: `dc5e739f764b077fdfce48a5f1c068f5039591b5206e6fb4498dc48a7f3828f4`
- Capability records: 15
- Trusted records: 8
- Blocked records: 7

| Broad aggregate | Capability records | Trusted | Blocked members |
|---|---:|---:|---|
| `cr-120-damage` | 13 | false | `damage.combat.excess`, `damage.prevention.order`, `damage.replacement.order`, `damage.result.infect`, `damage.result.lifelink`, `damage.result.wither`, `damage.trigger.noncombat` |

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
- Program entries: 255
- Unique program keys: 243
- Duplicate keys resolved by pack order: 12
- Unique Oracle IDs represented: 137
- Card-specific operation names: 15
- Typed card-override boundary present: false

## Snapshot fingerprints

- Oracle SHA-256: `34d43820bb1b85be99267367969396c81a0bc387061dbd00882d1e78a5e84aa9`
- Rulings SHA-256: `edabb33f1354d577f4a337c182f1093519b3499e71cec304f7474e7b362c0537`
- Oracle updated: `2026-07-31T21:03:00.228+00:00`
- Rulings updated: `2026-07-31T21:00:39.181+00:00`

## Boundary

The current compiler is partial and interleaved. Full-corpus exactness is not claimed. Fine-grained closure currently covers only the reviewed base-damage spell slice; other nodes retain the broad-contract fallback. CardProgram V2, typed handlers, and distinct compiler stages remain incremental work.
