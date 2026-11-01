# CQL-19 EXPLORER — QA Handoff (iteration 1)

## What was probed
Fresh probe: `/mnt/d/fhir4ds/.temp/qa/cql19x_explorer_probe.py` (3-engine:
forced_python / native / no_python) plus inline population-SQL isolation
scripts. Coverage per mandate: Skip/Take boundary counts (0, negative,
oversized, decimal 1.5 -> typed TranslationError, string count rejected);
Tail/Last of empty and single-element lists; union dedup (1 vs 1.0 equivalent
dedup, Code equivalent dedup, null dedup, 3-list chained unions);
NotEqual/NotEquivalent asymmetric null operands; properly includes/in with
duplicates and boundary equality (element + list forms); singleton-from at
0/1/2 with null elements; Length of union/intersect results; temporal and
quantity lists (Last/Tail/Length, 1 'g' vs 1000 'mg' union dedup); two-level
define-alias chains; e2e multi-patient population SQL over retrieves.

## Conformant (verified, no action)
Skip/Take/Tail/Length/Last static boundaries; union dedup semantics incl.
equivalent-vs-equal classes and nulls; NotEqual null->null; NotEquiv
null->TRUE is CORRECT per CQL 1.5 (Equivalent is null-tolerant: null~x false
so !~ true; probe expectation error, NOT A BUG — cql.hl7.org Appendix B
Not Equivalent + 04-logicalspecification); properly includes boundaries;
singleton-from 0/1/null-element; alias chains for Tail/Last/Singleton/
Skip/Take/NotEq/ProperlyIncludes via population SQL; typed rejection of
decimal/string counts.

## Issues opened (all translator-level, py==cpp==no_python)
- QA-001 HIGH — union operand that is an alias-of-alias stored-list define
  emits `(SELECT * FROM "<aliasCTE>")` (2 columns) -> BinderException.
- QA-002 HIGH — Tail/Skip/Take/Length over retrieve-shaped list operands
  (inline `[Observation] O return O.id`, bare `[Observation]`,
  resource-define aliases, stored define of a query return) produce broken
  SQL (column-ref binder errors, ARRAY_SLICE on rows, scalar-subquery
  multi-row, array_length(JSON/VARCHAR)). Last/First/flatten fine.
- QA-003 MEDIUM — singleton from (<query retrieve list>) with >1 element
  silently returns NULL instead of the typed SingletonFrom error.

## Notes for FIX
- Execution context: these are population-SQL paths; standalone define SQL
  legitimately references CTEs, so use translate_library_to_population_sql
  for reproducers (pattern in test_clinical_operator_parity.py).
- DQM-sensitivity: RetrievePlaceholder rows-gating invariant from SKEPTIC
  (union dispatch MUST include RetrievePlaceholder) is adjacent — any fix to
  union operand normalization must re-run the DQM gate.
