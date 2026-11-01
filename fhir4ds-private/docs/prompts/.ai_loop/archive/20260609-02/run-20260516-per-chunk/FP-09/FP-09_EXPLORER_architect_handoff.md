# Architect Handoff - FP-09 EXPLORER

## Structural Health

FP-09 string search behavior is structurally sound for the audited public
surfaces. The native C++ evaluator and the forced Python DuckDB fallback agree
through public UDFs for adversarial string-search inputs, including Unicode
character indexing, empty-string arguments, invalid argument types, non-string
inputs, multi-item inputs, nulls, and boundary `substring()` cases.

The current design keeps the correct boundary between strict/helper semantics
and public DuckDB row resilience: strict/helper layers may raise typed semantic
errors, while public UDFs convert those errors to empty/NULL consistently across
backends.

## Golden Standard

Wrote `.temp/architect/golden_standard.md` with 10 falsifiable invariants for
FP-09. Key invariants audited:

- Typed extraction must replace host-language coercion for declared String and
  Integer parameters.
- Native C++ and forced Python fallback must be compared explicitly through
  public UDFs.
- UTF-8 character positions, not byte positions, govern `indexOf()` and
  `substring()`.
- Empty string and empty collection semantics must remain distinct.

## QA Audit

QA was sufficient. It did not stop at happy paths; it explicitly compared native
C++ and forced Python fallback behavior, tested Unicode and malformed/non-string
inputs, and checked direct helper behavior separately. No `RETRY_QA` veto is
needed.

## Issues by Category

| Category | Count | Status |
| --- | ---: | --- |
| SPEC_VIOLATION | 0 | None |
| API_CONTRACT | 0 | None |
| DATA_HANDLING | 0 | None |
| PERFORMANCE | 0 | None |
| REGRESSION_RISK | 0 | None |
| MISSING_FEATURE | 0 | None |

## Recommended Fix Order

No fixes recommended for this chunk/personality run.

## Validation

- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py fhir4ds/fhirpath/duckdb/tests/unit/test_string.py -q`
  - Result: 97 passed.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM" > ... && cat ...`
  - ViewDefinition: 134/134, 100.0%
  - FHIRPath (R4): 935/935, 100.0%
  - CQL: 1706/1706, 100.0%
  - DQM (QI Core 2025): 47/47, 100.0%
  - Overall: 2822/2822, 100.0%
