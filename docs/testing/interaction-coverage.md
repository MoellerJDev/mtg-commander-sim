---
title: "Interaction coverage"
status: "current"
authoritative_source: "platform/reusable-piece-interaction-evidence.json, capability evidence, mechanic contracts, conformance records, semantic programs, and tests"
verified: "2026-08-05"
audience: "rules and test contributors"
maintenance: "hand-maintained"
---

# Interaction coverage

Rule-by-rule and card-by-card tests are necessary but cannot establish the
composition of effects. Interaction assurance tracks reusable capabilities,
applicable pairs, high-risk three-way combinations, official rulings, and
discrepancies found by differential or mutation testing.

For each rules slice, record:

- the `interaction` evidence class, exact test ID, and exact piece pair or
  higher-order tuple in `platform/reusable-piece-interaction-evidence.json`;
- participating capability or temporary mechanic-contract IDs;
- legal and illegal orderings, targets, costs, and visibility contexts;
- replacement/prevention competition and trigger/APNAP ordering;
- zone changes, last-known information, copy/control changes, and state-based
  action boundaries that can alter the result;
- whether the case has direct, property, mutation, replay, and privacy evidence;
- unresolved semantic/compiler dependencies.

Coverage must be derived into machine-readable reports. A green unit test for
one card does not promote its untested interactions. Two pieces citing the same
general contract test are not covered unless an explicit declaration says that
test asserts their interaction. Higher-order declarations project only the
pairs they actually name. An exact compiler node does not promote an untrusted
runtime dependency. The versioned capability registry is the authoritative
fine-grained trust graph for migrated slices; current mechanic contracts and
conformance cases remain migration inputs where fine-grained capability
mappings do not yet exist.
