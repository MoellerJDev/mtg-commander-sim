---
title: "ADR 0023: current-state documentation system"
status: "ADR"
authoritative_source: "this decision record"
verified: "2026-08-05"
audience: "maintainers, contributors, and coding agents"
maintenance: "hand-maintained"
adr_id: "0023"
decision_status: "accepted"
date: "2026-08-05"
---

# ADR 0023: current-state documentation system

## Context

The repository accumulated a large README, a second monolithic architecture
reference, branch handoffs, archived implementation-status pages, version-era
summaries and generated reports that repeated the same facts. Current guidance
could remain syntactically valid while describing an old branch, card snapshot
or subsystem boundary. Coding agents had to read too much prose and could not
reliably identify the present authority.

The documentation must support local users, rules contributors and coding
agents while rules ownership changes frequently.

## Decision

Use a docs-as-code system with these rules:

- classify living content by Diátaxis purpose: tutorial, how-to, reference or
  explanation;
- keep the README and architecture overview as concise routing pages;
- use C4 context/container views for stable system maps and avoid manually
  maintained code-level inventories;
- make code, schemas, tests and machine-readable policy the primary current
  authority;
- make generated reports the only authority for counts, fingerprints,
  integration state and next-work selection;
- keep living prose in present tense without branch, PR, CI-run or copied metric
  ledgers;
- retain historical rationale only in indexed ADRs and the changelog;
- delete superseded status, migration, roadmap and handoff narratives once
  durable guidance is consolidated;
- keep `AGENTS.md` as a compact navigation and guardrail contract rather than a
  status cache;
- require every maintained Markdown file to be indexed, metadata-valid,
  link-valid and checked in CI.

## Alternatives

- Keep all historical Markdown in place and label it more carefully. Rejected
  because duplicated search results still obscure the current authority.
- Put all guidance in one README. Rejected because tutorial, operations,
  reference and explanation needs conflict and the file becomes expensive to
  maintain and consume.
- Generate every document from source. Rejected because rationale, procedures
  and user guidance require reviewed human judgment.
- Adopt a separate documentation site or wiki. Rejected for now because
  repository-local Markdown provides versioned, reviewable context beside code.

## Consequences

Documentation changes remove stale files rather than preserving them as an
archive; Git retains the history. Contributors must update the existing owner
for changed behavior and regenerate measured status in the same pull request.
Coding agents have a deterministic reading path and can reject stale prose when
it conflicts with executable evidence. The index and validators become
documentation fitness functions and must evolve with any future structure
change.
