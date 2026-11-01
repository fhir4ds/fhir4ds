# QA Handoff - CQL-09 SKEPTIC

Scope probed: CQL comparison operators for `between`, equality, equivalence,
relative comparison, Quantity unit compatibility, Date/DateTime precision,
list/tuple comparison, and native-loaded versus forced Python fallback DuckDB
execution.

Spec references verified: CQL 1.5.3 Appendix B comparison operators. `between`
is inclusive `>=`/`<=`; Quantity comparison with incompatible dimensions returns
null; `~` returns true for equivalent values or both null and false otherwise;
string equivalence ignores case and normalizes whitespace; list and tuple
equivalence recurse by element/name.

Findings:
- `QA-CQL09-SKEPTIC-001`: `1 'm' between 50 'cm' and 150 'cm'` returned false
  in both native-loaded and forced Python fallback registrations because the
  translator lowered `between` directly to SQL comparisons over Quantity JSON
  strings instead of using Quantity comparison helpers.
- `QA-CQL09-SKEPTIC-002`: generic `~`/`!~` used SQL equality for strings,
  lists, and tuples. Reproducers included `'John Doe' ~ 'john doe'`,
  `'a b' ~ 'a\tb'`, `{'ABC'} ~ {'abc'}`, and
  `Tuple { x: 'ABC' } ~ Tuple { x: 'abc'}` returning false instead of true.

No archived `.ai_loop/spec_comp/**` artifacts were inspected.
