# CQL-08 SKEPTIC QA Handoff

## Scope

- Chunk: `CQL-08`
- Spec area: CQL Nullological Operators
- Items: `Coalesce`, `IsNull`, `IsFalse`, `IsTrue`
- Personality: SKEPTIC
- Freshness: inspected current source and tests only; did not rely on archived
  prior workflow outputs.

## Findings

### QA-CQL08-SKEPTIC-001 - RESOLVED

- Severity: HIGH
- Static definitions used as nullological operands generated `_pt.patient_id`
  correlated CTE lookups even when the source definition was compile-time
  static. Standalone translated definitions such as `IsTrue(BoolAlias)` and
  `Coalesce({NullAlias, StringAlias})` could fail to bind.
- Fix: extended static inlining to nullological functions and static list
  elements.

### QA-CQL08-SKEPTIC-002 - RESOLVED

- Severity: MEDIUM
- Public `IsTrue`/`IsFalse` macros returned true for non-Boolean values such as
  `1` and `0`.
- Fix: macros now require `typeof(x) = 'BOOLEAN'` and explicit true/false.

### QA-CQL08-SKEPTIC-003 - RESOLVED

- Severity: MEDIUM
- Forced Python fallback `logicalCoalesce('[null, {"x": 1}]')` returned Python
  repr text instead of compact JSON, diverging from the native-loaded path.
- Fix: object/list values from JSON-list input now serialize with compact JSON.

### QA-CQL08-SKEPTIC-004 - RESOLVED

- Severity: HIGH
- Public DuckDB `"Coalesce"` was a two-argument macro only. It failed variadic
  calls and the CQL single-list overload.
- Fix: removed the narrow macro and registered a variadic `Coalesce` UDF with
  `VARIANT` return type, preserving Date/scalar/list values.

## Verification

- Focused nullological/macros pytest: 13/13 passed.
- Adjacent parity plus official CQL pytest: 3071/3071 passed.
- Full `python3 -m pytest fhir4ds -q`: 7156 passed, 5 skipped, 9 warnings.
- Full `python3 conformance/scripts/run_all.py`: 2822/2822 passed.
- `git diff --check`: clean.

