---
title: "ADR 0032: durable certification receipts"
status: "ADR"
authoritative_source: "this decision record and exact-head certification implementation"
verified: "2026-08-07"
audience: "maintainers and CI contributors"
maintenance: "hand-maintained"
adr_id: "0032"
decision_status: "accepted"
date: "2026-08-07"
---

# ADR 0032: Durable certification receipts

## Context

Tracked readiness data previously stored a feature SHA, certified SHA, branch,
pull-request chronology, and workflow run. A squash merge gives the certified
source tree a different commit identity, so `main` could not validate its own
generated status without another commit that rewrote those coordinates. That
follow-up commit then needed a new certification, creating a reconciliation
loop.

## Decision

Tracked readiness data owns durable product versions, policy, and the evaluated
source-tree fingerprint. It does not own a current PR number, exact head,
workflow run, merge SHA, runtime branch, or active integration phase.

After every required PR gate succeeds, `PR / Certification` publishes a strict
untracked receipt artifact for the exact PR head. The receipt includes the
complete required check suite and a fingerprint of canonical tracked Git blobs,
excluding generated reports that would otherwise be self-referential.

`Main smoke` resolves the merged pull request and its successful PR workflow
from GitHub, downloads that run's receipt, validates every coordinate, and
compares the current source tree with the certified exact-head fingerprint.
Commit identity is not the equivalence boundary, so a squash-equivalent tree is
accepted. Missing, expired, malformed, stale, failed, or materially different
evidence fails closed.

## Consequences

- A commit never predicts its merge SHA or certifying workflow run.
- Squash merges do not require a provenance-only follow-up commit.
- Exact-head branch protection remains the merge authority.
- GitHub execution evidence remains ephemeral and auditable without becoming
  product source.
- Main-smoke verification requires read access to Actions and pull-request
  metadata and a live receipt artifact for the merge being checked.

## Alternatives

- Storing the eventual merge SHA in the feature branch is impossible and
  self-referential.
- Marking each older SHA as historical still requires a new tracked rewrite
  after every merge.
- Trusting only a successful check name does not prove tree equivalence or bind
  the result to the merged PR head.
