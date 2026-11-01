# Architect Handoff - FP-04 EXPLORER

## Structural Health

The FP-04 EXPLORER loop is structurally clean after remediation. `QA-001`
exposed a real native model-metadata drift at the `ofType()` subtype boundary:
native C++ used a smaller embedded R4 hierarchy than the Python fallback's
generated model files. The fix restores native/fallback parity for the scoped
§5.2 behavior without changing parser semantics, public UDF error resilience,
or primitive exactness rules.

## Golden Standard

Wrote `.temp/architect/golden_standard.md` with 10 invariants covering
`where`, `select`, `repeat`, `ofType`, native/fallback parity, bundled
extension freshness, native sqllogictest coverage, and the longer-term need
for shared/generated model metadata.

## QA Audit

QA was sufficient. The EXPLORER pass did not stop at happy paths; it compared
native and forced Python fallback outputs with mixed resource subclasses,
invalid criteria, nested projection/index expressions, repeat de-duplication,
and type-specifier failures. No `RETRY_QA` flag is set.

## Findings

| Issue | Category | Status |
| --- | --- | --- |
| `QA-001` | SPEC_VIOLATION | VERIFIED |

No new architect findings were opened. The duplicated native model table remains
known architecture debt, but this pass added appropriate parity and native
extension coverage for the touched behavior.

## Validation

- `python3 .temp/qa/fp04_explorer_fresh_probe.py` passed, 28 expressions.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py -q` passed, 9/9.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py -q` passed, 12/12.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py -q` passed, 11/11.
- `extensions/fhirpath/build/release/test/unittest "*fhirpath*"` passed, 750 assertions.
- Full conformance passed twice after the fix; architect gate result:
  ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Recommended Fix Order

No follow-up engineer phase is required for this inner loop.
