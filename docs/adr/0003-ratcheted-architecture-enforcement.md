---
title: "ADR 0003: ratcheted architecture and documentation enforcement"
status: "ADR"
authoritative_source: "this decision record"
verified: "a3ea421d021c45002048909073eeef69e6c113d9"
audience: "all code and documentation contributors"
maintenance: "hand-maintained"
adr_id: "0003"
decision_status: "accepted"
date: "2026-08-01"
---

# ADR 0003: ratcheted architecture and documentation enforcement

## Context

The working engine has accumulated a large legacy kernel, direct state writes,
card-specific semantic operations, oversized modules, and duplicated status
prose. A big-bang rewrite would put deterministic behavior, projections, and
replay at risk, while unenforced guidance would allow debt to grow during the
migration.

## Decision

Adopt machine-readable, ratcheted baselines. Protected domain modules cannot
depend on transport/application/AI layers. Declared mutation owners and legacy
specificity sites may not grow. New engine methods, card branches, operations,
and oversized code fail validation. A content-free Scryfall name-digest index
detects printed-name literals without committing card data; changing reviewed
allowances requires an ADR.

Documentation uses typed front matter, one authoritative map, internal-link and
stale-claim validation, generated numerical status, and validated ADR metadata.
Existing debt is compatibility allowance, not architectural approval.

## Alternatives

- A big-bang kernel rewrite was rejected because it would combine behavioral
  and structural risk without incremental replay evidence.
- Style guidance without CI enforcement was rejected because it cannot prevent
  regression.
- Freezing every current source hash was rejected because legitimate refactors
  and ordinary Scryfall-name index refreshes need independent paths.

## Consequences

Migration PRs must reduce or preserve the measured baseline and keep generated
artifacts fresh. New architecture decisions carry explicit review cost, but
future rules work cannot silently deepen the monolith or duplicate volatile
metrics. Baseline removal follows successful extraction; baseline expansion is
exceptional and reviewed.
