# Engineer Handoff — SOF-VD-04 HISTORIAN iter 1 fresh run (2026-07-03)

## Phase: FIX (Remediation)

## Issues to Address
**Zero.** The QA HISTORIAN probe produced zero non-terminal CRITICAL/HIGH/MEDIUM
issues for SOF-VD-04 (`column.collection`, `column.type`, `column.tag`).

## Triage Table
Empty — no issues to triage.

## Remediation Plan
None required. The SOF-VD-04 surface is spec-compliant end-to-end:

- **Item 1 — collection default false**: `Column.collection` defaults to `False`
  at direct construction, parser path (omitted), and explicit `false`.
  `to_dict()` correctly omits the default. Confirmed by 5 assertions.
- **Item 2 — multi-value non-collection error**: SQL generator emits the
  `array_length(fhirpath(...)) > 1` cardinality guard. DuckDB runtime on a
  multi-given Patient correctly raises
  `Invalid Input Error: ViewDefinition column 'givens' path 'name.given'
  violates collection=false / type unset; non-primitive output`. This matches
  the spec §2.2.1 "Multiple values found but not expected for column" rule.
- **Item 3 — collection=true multi-value**: `Column(path='name.given',
  name='givens', collection=True)` round-trips through parser, `to_dict()`,
  and SQL generation. DuckDB runtime returns the whole collection
  `[(['Alpha', 'Beta'],)]` without raising. This matches spec §2.2.1 step 3
  (`col.collection` is true → `val`).
- **Item 4 — type URI handling**: All 8 primitive/non-primitive types
  (`string`, `integer`, `boolean`, `decimal`, `dateTime`, `Coding`,
  `CodeableConcept`, `Quantity`) normalize to `ColumnType`. Full URI form
  normalizes; fragment form accepted; unknown external URI preserved verbatim
  (type is just a hint per spec §Column Types). Whitespace, non-string, and
  parser null-type all rejected with clear errors.
- **Item 5 — type mismatch reporting**: SQL includes both cardinality and
  type guards. DuckDB runtime on `type=integer` column whose path returns a
  non-integer string correctly raises
  `Invalid Input Error: ViewDefinition column 'pid' path 'id' violates
  collection=false / declared type integer`. This matches spec §Column Types
  "All values in a given column must be of a single data type".
- **Item 6 — tag 0..* with required name/value**: Empty array accepted
  (0..* lower bound). Single-tag round-trip exact. Missing name/value,
  whitespace name/value, non-dict item, and `None` all rejected. 100-tag
  stress passes. Parser rejects the plural `tags` form (spec uses singular
  `tag`). Duplicate tag names accepted (spec has no dedup rule for 0..*).

## Validation
- ViewDefinition pytest: **1055/1055** PASS (no regressions)
- Full conformance: **2822/2822** unchanged (per `PROC_VALIDATION.md` baseline)
- No source changes; no new regression tests required.

## Conclusion
**No remediation required.** Transition to ARCHITECT phase for structural audit.
