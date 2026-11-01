# QA Handoff - FP-18 EXPLORER

Personality: EXPLORER
Scope: FHIRPath N1 §6.6 Math Operations and §6.7 Date/Time Arithmetic.

Spec anchor:
- §6.6 requires single-element operands, empty propagation for empty operands, errors for incompatible items, Quantity arithmetic with appropriate units, and empty results for arithmetic overflow/underflow.
- §6.6.2 defines `/` as left operand divided by right operand and says Quantity division produces an appropriate unit.
- §6.7 date/time arithmetic uses calendar semantics; adding years that produce an out-of-range year is an error, and more precise quantities are converted to the input precision with decimals removed.

Fresh probe:
- Added `.temp/qa/fp18_explorer_probe.py`.
- Compared native C++ DuckDB registration against forced Python fallback over negative decimal `div`/`mod`, scalar/Quantity combinations, precision-preserving temporal arithmetic, timezone DateTimes, and min/max year boundary arithmetic.

Findings:
- `QA-001` HIGH: Date/Time arithmetic overflow is not row-resilient and not range-safe. Native C++ returns invalid year strings such as `10000`, `0000`, `10000-01-01`, and `0000-12-31T23:59:59`. Forced Python fallback leaks `OverflowError` through public UDFs for day/second boundary cases. Literal overflow should be invalid; resource-backed overflow should return empty/NULL while `fhirpath_is_valid()` remains structurally true.
- `QA-002` MEDIUM: Native scalar divided by Quantity computes `2 / 1 'mg'` as `0.5 'mg'`, which reverses the arithmetic and preserves the wrong unit. Fallback uses a reciprocal unit but renders it inconsistently as `1/'mg'`; both paths should return an appropriate reciprocal unit such as `2 '1/mg'`.

Recommended validation after remediation:
- `python3 .temp/qa/fp18_explorer_probe.py`
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_arithmetic_parity.py -q`
- Native sqllogictest for `extensions/fhirpath/test/sql/fhirpath.test`
- Full conformance through `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM" > validation_summary.log && cat validation_summary.log`
