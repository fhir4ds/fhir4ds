# Architect Handoff — FP-01 SKEPTIC

Scope: FHIRPath §4.1 literal behavior across the Python core evaluator, DuckDB forced Python fallback, native C++ extension, and bundled package extension.

Golden standard:
- Written to `.temp/architect/golden_standard.md`.
- The key invariants are: one shared literal grammar boundary, native/fallback public UDF parity, valid Unicode scalar output for string escapes, preservation of Quantity value/unit shape, and mandatory rebuild/copy validation after native lexer changes.

QA enforcer gate:
- QA was sufficient. It verified current FHIRPath §4.1 literal rules before logging issues and covered invalid dates/times, numeric suffixes, no-whitespace quantities, string escapes, and native-vs-forced-fallback DuckDB parity.
- `RETRY_QA` was not set.

Structural audit result:
- No new architectural findings were added.
- The remediation is structurally aligned: the no-whitespace Quantity fix stays in the wrapper-only syntax precheck and does not create a new parser grammar; Unicode surrogate handling is centralized in the Python unescape path and the native lexer helper used by both strings and delimited identifiers.
- Regression coverage now guards both public DuckDB backends and native sqllogictest coverage for the two fixed literal boundaries.

Issue status:
- `QA-FP01-001` MEDIUM `SPEC_VIOLATION`: RESOLVED. Forced Python fallback now accepts `10'mg'` consistently with the formal `quantity: NUMBER unit?` grammar and native DuckDB output.
- `QA-FP01-002` MEDIUM `SPEC_VIOLATION`: RESOLVED. Valid UTF-16 surrogate-pair string escapes now materialize as one Unicode scalar value in Python and native public surfaces.

Validation:
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py -q` — 11 passed.
- `python3 -m pytest fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_aggregate_lexical_parity.py -q` — 30 passed.
- `./build/release/test/unittest "*fhirpath*"` — 308 assertions passed.
- `python3 conformance/scripts/run_all.py | grep ...` — ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

Recommended fix order:
- No engineer work remains for this inner loop.
