---
title: "Mutation testing policy"
status: "current"
authoritative_source: "capability registry v5, capability evidence declarations, and executable mutation tests"
verified: "2026-08-01"
audience: "rules, security, replay, and trust contributors"
maintenance: "hand-maintained"
---

# Mutation testing policy

Dependency fail-closed testing and implementation mutation testing are
different evidence. Capability registry v5 records them separately.

`dependency_fail_closed_status` proves that a missing, blocked, cyclic, or
profile-incompatible dependency prevents trust. It is `not_applicable` only for
a dependency-free capability with a reviewed rationale.

`implementation_mutation_status` records whether an explicit implementation
mutant was killed. `not_run` and `survived` cannot support trusted status.
`not_applicable` requires a reviewed rationale and is not a shortcut for code
that simply lacks a mutation test.

The current focused mutation suite uses deterministic executable monkeypatch
mutants for critical represented guards and dispatch paths. Each mutation
evidence row names its fully qualified test in the generated capability
evidence index. This is bounded evidence, not a repository-wide mutation score;
the generated architecture report therefore keeps aggregate mutation score
`null` until a real configured tool run exists.

Critical authority, privacy, replay, trust, component-validation, target, cost,
priority, zone, replacement/layer, trigger, state-action, persistence, and
idempotency mutants block merge when they survive. A test that merely validates
the registry schema cannot substitute for behavioral or mutation evidence.

Run the focused checks with:

```bash
python -m unittest discover -s tests -p "test_capability_implementation_mutations.py" -v
python scripts/update_capability_evidence.py --check
```

New mutation evidence must declare capability, class, fully qualified test,
official rule IDs, supported profiles, and applicability. Renaming or removing
the test makes the packaged evidence index stale and fails CI.
