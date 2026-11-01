# Engineer Handoff: FP-04 HISTORIAN

Triage table:

| Issue | Category | Severity | Status |
|---|---|---:|---|
| QA-001 | SPEC_VIOLATION | MEDIUM | RESOLVED |

Root cause: native `Evaluator::evalOfType` returned an empty collection when
the AST had no type-argument child. `fhirpath_is_valid()` validates by parsing
and evaluating against a sparse Patient resource, so `entry.resource.ofType()`
was treated as a valid empty result instead of a wrong-arity type function.

Fix: changed `evalOfType` to require exactly one type argument and throw
`FHIRPathSpecError("ofType() takes exactly 1 type argument")` otherwise. The
existing public native UDF resilience converts that spec error to empty/NULL for
result UDFs, while `fhirpath_is_valid()` now returns `false`.

Regression coverage:
- Added native/fallback Python parity coverage in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py`.
- Added native sqllogictest coverage in
  `extensions/fhirpath/test/sql/fhirpath.test`.
- Rebuilt and copied the bundled extension to
  `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

Validation:
- Fresh QA probe after fix: 26 cases, 0 failures.
- Focused pytest: `test_filter_projection_parity.py` passed 6/6.
- Native extension unittest: 350 assertions passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.
