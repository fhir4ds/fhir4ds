# QA Handoff — FP-13 EXPLORER

Date: 2026-06-12
Iteration: 1
Personality: EXPLORER
Scope: FHIRPath §6.1 Equality (`=`, `!=`, `~`, `!~`) with Quantity, Date/Time, String, numeric, multi-item, and complex-object behavior across native C++ DuckDB and forced Python fallback paths.

## Spec Basis

Official source: HL7 FHIRPath continuous-build `input/pages/index.md`, §6.1 Equality.

Normative points used:
- Equality over primitive numerics is exact except Decimal trailing zeroes.
- Quantity equality/equivalence use unit conversion when units are commensurable and return empty when conversion is empty.
- Quantity equivalence compares after conversion to the least granular unit and must preserve operand precision.
- Complex equality/equivalence recurses through child elements.
- `!=` and `!~` are converses of `=` and `~`.

## Fresh Probe

Created `.temp/qa/fp13_explorer_fresh_probe.py` for this launch. The probe pins the repository root on `sys.path` so it imports the current checkout instead of any installed `fhir4ds` package.

The probe compared:
- Native C++ DuckDB extension registration.
- Forced Python fallback DuckDB registration.
- Direct Python fallback UDF helpers.

## Findings

| ID | Severity | Category | Status | Summary |
| --- | --- | --- | --- | --- |
| QA-001 | MEDIUM | SPEC_VIOLATION | VERIFIED | Forced Python fallback returned false for `Observation.value ~ 83.9 'kg'` over `185 '[lb_av]'`; native returned true. The fallback compared converted base values at converted precision instead of preserving original operand precision for Quantity equivalence. |
| QA-002 | MEDIUM | SPEC_VIOLATION | VERIFIED | Native C++ treated distinct large JSON integers such as `9007199254740992` and `9007199254740993` as equal/equivalent through binary `double` conversion, including direct paths, complex objects, and arrays. |

## Validation Evidence

Failing cases were reproduced before remediation in `.temp/qa/fp13_explorer_fresh_probe.py`.

Post-fix validation:
- `python3 .temp/qa/fp13_explorer_fresh_probe.py` passed, 43 expressions.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py -q` passed, 13/13.
- Adjacent collection/existence parity passed, 24/24.
- Native FHIRPath sqllogictest/unittest passed, 1000 assertions.
- Full conformance passed, 2822/2822.
