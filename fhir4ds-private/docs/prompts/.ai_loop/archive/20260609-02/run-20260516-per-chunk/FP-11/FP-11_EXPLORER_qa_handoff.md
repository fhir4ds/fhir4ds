# QA Handoff - FP-11 EXPLORER

## Scope

Fresh FP-11 FHIRPath §5.7 Math EXPLORER pass. Did not inspect archived spec_comp outputs. Consulted the official HL7 FHIRPath Normative Release v2.0.0 §5.7 Math section directly.

## Probes

- Created `.temp/qa/fp11_explorer_probe.py`.
- Compared native/C++ DuckDB extension vs forced Python fallback for `fhirpath`, `fhirpath_text`, `fhirpath_json`, and `fhirpath_number`.
- Covered deterministic cases plus 80 seeded pathological literal/function combinations across `abs`, `ceiling`, `floor`, `round`, `sqrt`, `ln`, `exp`, and `truncate`.
- Ran existing focused parity: `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_math_parity.py -q`.

## Findings

- `QA-001` MEDIUM: Native `abs()` on Decimal literals lost source-text preservation and exposed binary double artifacts on text/json surfaces (`3.1415899999999999` vs fallback `3.14159`).
- `QA-002` MEDIUM: Native explicit `round(0)` returned Integer-form text/json (`3`/`[3]`) while fallback returned Decimal-form (`3.0`/`[3.0]`) for a precision-bearing call.

## Evidence

`.temp/qa/fp11_explorer_probe.py` checked 120 cases and found 8 mismatches, all reducing to the two issue classes above. Existing `test_math_parity.py` passed before the new cases were added, confirming these were uncovered gaps.
