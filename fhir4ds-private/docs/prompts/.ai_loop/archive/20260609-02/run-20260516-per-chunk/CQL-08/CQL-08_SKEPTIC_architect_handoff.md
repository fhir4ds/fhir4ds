# CQL-08 SKEPTIC Architect Handoff

## Outcome

`CQL-08` SKEPTIC passed after four remediations. No open defects remain from
this personality pass.

## Architectural Notes

- Nullological functions are now included in the static-alias inlining rule.
  This is the same class of issue found for conversion functions: compile-time
  scalar definitions must not lower to `_pt.patient_id` CTE lookups in
  standalone scalar SQL.
- Public `IsTrue`/`IsFalse` now enforce CQL's Boolean-only predicate semantics
  on the DuckDB surface instead of relying on SQL truthiness/coercion.
- `Coalesce` cannot be represented as one type-preserving DuckDB macro because
  CQL exposes both variadic scalar and single-list overloads. The direct public
  DuckDB function is therefore a variadic Python UDF with `VARIANT` output,
  while translated CQL may still use native SQL `COALESCE` for generated SQL.
- Forced Python fallback and native-loaded registration paths agree on the
  tested direct public surface for this chunk.

## Validation Record

- Focused nullological/macros pytest: 13/13 passed.
- Adjacent parity plus official CQL pytest: 3071/3071 passed.
- Full `fhir4ds` pytest: 7156 passed, 5 skipped, 9 warnings.
- Unified conformance: ViewDefinition 134/134, FHIRPath R4 935/935, CQL
  1706/1706, DQM 47/47, overall 2822/2822.
- `git diff --check`: clean.

