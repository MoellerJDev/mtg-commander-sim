# Deck Review MVP implementation status

Last updated: 2026-07-28

This document tracks the checked acceptance gates for the private Deck Review
MVP. It deliberately excludes live game state, pilot memory, capability
material, downloaded databases, and provider secrets.

## Baseline

- Requested starting commit: `dfe5a19c1fe08f0c4dc18c1b9dcda47e2ca68e3f`
- Sanitized pre-publication equivalent: `4dc3feb`
- Published baseline branch: `main`
- Published baseline tag: `v0.6.0`
- Baseline package version: `0.6.0`
- Current feature branch: `agent/review-mvp`
- Remote: `origin` → private `MoellerJDev/mtg-commander-sim`
- GitHub authentication: authenticated as `MoellerJDev`; no credential material
  was read or recorded
- Baseline validation: 113 tests passed locally; Windows/Ubuntu Python
  3.11/3.12 GitHub Actions matrix passed

The sole unpublished history was sanitized before first push. Runtime records,
databases, bulk downloads, caches, wheels, and private state are excluded by
repository policy.

## Checkpoint 0 — publication and CI

- [x] Complete-history source/security/large-object audit
- [x] Private GitHub repository created
- [x] Sanitized v0.6.0 baseline pushed to `main`
- [x] Annotated `v0.6.0` tag pushed without moving an existing tag
- [x] Repository hygiene, governance, compact offline fixture, and CI added
- [x] Four-job Windows/Ubuntu CI matrix passed
- [x] `agent/review-mvp` created from the published baseline

Checkpoint commit: `36f25ed` (`chore: prepare private repository and CI`).

## Checkpoint 1 — v0.7.0 exact targets and interaction

- [x] Declarative public-zone target query and structural target groups
- [x] Mode-aware candidate generation and mandatory-target action removal
- [x] Submission and resolution target revalidation
- [x] Partial target survival and all-targets-illegal rules counter
- [x] Empty-stack counterspell regression
- [x] Server-issued pitch, kicker, overload, commander-free, and X-life costs
- [x] Counterspell suite scenarios, including storm copies and delayed costs
- [x] Shared removal/disruption scenarios
- [x] Target/action telemetry wired into the fidelity report
- [x] Corrected seed-20260730 decision-opportunity regression
- [x] Complete suite passes after the final interaction slice
- [x] Corrected fixture replay and hidden-information audit pass
- [x] Package version updated to 0.7.0
- [x] Wheel build and clean-install verification pass
- [x] Coherent milestone commit pushed
- [x] v0.7.0 tag created only after every gate passes

Checkpoint result: 132 tests passed. Compilation, 11 schema checks,
repository/history secret and artifact scans, corrected exact replay, seat
projection, wheel build, clean installation, package-version import, and CLI
smoke testing passed. The corrected fixture advanced through turn sequence 8
and beyond D27 with both `suppressed_meaningful_windows` and
`illegal_target_actions_advertised` equal to zero.

## Checkpoint 2 — v0.8.0 exact-deck operation MVP

- [ ] Semantic preflight v2 and hash-drift invalidation
- [ ] Trusted material semantic closure for both live exact lists
- [ ] Reusable exact-list cost, search, trigger, static, replacement, copy,
  loop, and combat families
- [ ] `semantic_policy=trusted_only`
- [ ] `deck_operation_evidence` gate
- [ ] Resumable `review-batch` aggregation and attribution
- [ ] Deterministic scripted semantic soak
- [ ] Three consecutive qualifying four-seat persistent-Codex games
- [ ] Per-deck operation reports with source-record links
- [ ] Package version updated to 0.8.0
- [ ] Complete validation, milestone commit, and branch push

Duplicated-list fixtures must always retain `matchup_evidence=false`.

## GitHub finalization

- [ ] Full branch security/large-file audit
- [ ] Complete tests, replay/privacy, preflight, schemas, wheel, and clean
  installation pass
- [ ] `agent/review-mvp` pushed
- [ ] Draft PR opened against `main`
- [ ] Draft PR left unmerged and not marked ready automatically
- [ ] `OVERNIGHT_HANDOFF.md` written

## Next work

Begin v0.8 semantic preflight v2 and exact-list semantic closure. Do not run
live evidence games until both current live lists pass the trusted-material
preflight gate. After the review-MVP draft PR exists, rules-corpus work moves
to `agent/rules-completeness` and a stacked draft PR; it does not broaden this
feature branch.
