# Architect Handoff - FP-14 HISTORIAN

Date: 2026-06-12
Iteration: 1
Audit status: COMPLETE
QA retry: false

## Golden Standard

Wrote `.temp/architect/golden_standard.md` for this launch. Core invariants:
- FHIRPath comparison must be type-driven, not transport-string-driven.
- Native DuckDB/C++ and forced Python fallback public surfaces must match.
- Temporal ordering must route through `FP_Date`, `FP_DateTime`, `FP_Time`, and
  `FP_TimeBase.compare()` for precision and timezone semantics.
- Fixes must use FHIR type metadata and avoid field-specific branches.
- Validity checks must remain separate from sample evaluation emptiness.

## Audit Result

`QA-001` was correctly scoped to FP-14 comparison and fixed with general logic.
The change materializes FHIR temporal `ResourceNode` strings according to type
metadata (`date`, `dateTime`, `instant`, `time`) before comparison. It does not
special-case `Observation.effectiveDateTime` or `issued`, and it preserves the
existing temporal abstraction by delegating ordering to `FP_TimeBase.compare()`.

Architect findings opened: 0.
Open CRITICAL/HIGH/MEDIUM issues: 0.
QA coverage was sufficient; no retry was set.

## Recommended Fix Order

No further FP-14 HISTORIAN fixes are required. Existing review-10 findings
remain milestone risks outside this chunk.

## Validation Summary

- `python3 .temp/qa/fp14_historian_fresh_probe.py` passed, 30 expressions.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py -q` passed, 12/12.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py -q` passed, 25/25.
- `git diff --check -- fhir4ds/fhirpath extensions/fhirpath fhir4ds-private/docs/prompts/.ai_loop .temp/qa/fp14_historian_fresh_probe.py` passed.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935, CQL
  1706/1706, DQM 47/47, overall 2822/2822.
