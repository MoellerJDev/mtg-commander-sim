---
title: "ADR 0040: closed source-self references"
status: "ADR"
authoritative_source: "this decision record and quorune/rules/source_references.py"
verified: "2026-08-08"
audience: "rules, compiler, CardProgram, and architecture contributors"
maintenance: "hand-maintained"
adr_id: "0040"
decision_status: "accepted"
date: "2026-08-08"
---

# ADR 0040: closed source-self references

## Context

CR 201.5 makes an object's name in its own ability refer to that particular
object. CR 201.5c also recognizes shortened names printed in some Oracle text.
The compiler previously compared full names independently in counter, damage,
prevention, trigger, entry, activation-cost, and combat-declaration grammars.
One declaration path guessed the first word of every card name. That produced
competing authorities and could mistake an unrelated word for the source.

Runtime name matching is not required after exact Oracle text has lowered to a
`$source` CardProgram reference. The interpretation belongs at the pinned
compiler boundary and must therefore be closed, deterministic, and versioned.

## Decision

`SourceReferenceSpec` owns the represented source-name vocabulary. It
normalizes one nonempty Oracle name and accepts:

- the full name;
- the complete leading name before a comma;
- the complete leading name before the title delimiters “the” or “of”; or
- the leading proper name in an ordinary two-word name.

It never derives an arbitrary first word, suffix, nickname, or substring. The
model is frozen, hashable, punctuation-normalized for exact comparison, and
provides an escaped regular-expression form for whole-clause productions.
Malformed names fail during construction.

Counter placement, fixed damage, prevention, self zone-change triggers,
unconditional tapped entry, named source activation costs, and declaration
normalization consume the same model. Successful lowering emits ordinary typed
`$source` references; runtime result handlers receive no card name and do not
reparse Oracle text. The compiler version advances whenever this vocabulary
changes because recognized nodes and CardProgram fingerprints can change.

## Consequences

- Full and represented shortened names lower identically to the physical
  source object.
- `Syr Carah` may refer to `Syr Carah, the Bold`; `Syr` alone does not.
- A title form such as `Bontu the Glorified` retains the complete leading
  `Bontu` reference without authorizing arbitrary first-word matching.
- Existing two-word and “of” forms such as `Zurgo Bellstriker` and
  `Daxos of Meletis` retain their Oracle-shortened source references.
- Unsupported abbreviations remain precise material residuals.
- Source spans, capability closure, runtime mutation ownership, projections,
  and replay schemas do not change.
- CR 201.5a, gained-ability rewriting, alternate names, name-changing effects,
  and every shortened-name convention remain outside this bounded family.

## Alternatives

- Keep one exact-name comparison per compiler production. Rejected because the
  productions drift and do not share negative grammar.
- Accept every lexical prefix of the full name. Rejected because it guesses
  aliases not established by the represented grammar.
- Match names in runtime Oracle text. Rejected because that creates a second
  compiler authority and makes replay depend on live interpretation.
- Add card-name exceptions. Rejected because the family must scale through
  generic compiler grammar rather than printed-name behavior.

## Removal condition

Replace this vocabulary only with a more complete typed CR 201 name-reference
model that preserves closed compilation, precise residuals, source identity,
versioned CardProgram fingerprints, and the prohibition on runtime Oracle
interpretation and card-specific rules behavior.
