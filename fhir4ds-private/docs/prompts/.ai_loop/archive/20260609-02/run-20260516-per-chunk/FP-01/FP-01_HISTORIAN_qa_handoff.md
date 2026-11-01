# QA Handoff - FP-01 HISTORIAN

## Scope

Systematically walked FHIRPath N1 §4.1 literals: Boolean, String, Integer, Decimal, Date, Time, DateTime, Quantity, and time-valued Quantity literals. Tested native C++ DuckDB extension and forced Python DuckDB fallback where both exist.

## Spec Anchor

Used HL7 FHIRPath Normative Release N1 §4.1 and the formal grammar:
- §4.1.2 string escapes, including `\\`, unknown escapes, and `\uXXXX`.
- §4.1.7 DateTime timezone offset notation `(+|-)hh:mm` or `Z`.
- Grammar `DATE`, `DATETIME`, `TIME`, `TIMEFORMAT`, and `TIMEZONEOFFSETFORMAT`.

## Findings

### QA-001 - HIGH - RESOLVED

Python fallback string unescaping reinterpreted produced backslashes:
- Reproducer: `fhirpath_scalar(resource, r"'\\p'")`
- Actual before fix: `["p"]`
- Expected: `[r"\p"]`

Root cause: ordered global replacements converted `\\` to `\`, then a later catch-all escape replacement consumed the produced backslash.

### QA-002 - MEDIUM - RESOLVED

C++ DateTime parsing accepted invalid partial DateTime timezone offsets:
- Reproducer: native `fhirpath(resource, '@2014-01-25T14+99:99')`
- Actual before fix: `["2014-01-25T14+99:99"]`
- Expected: empty result, matching Python fallback

Root cause: `parseDateTimeParts` returned early at hour/minute precision without consuming trailing timezone text. The C++ lexer also accepted malformed temporal token shapes for `fhirpath_is_valid`.

## Validation

- `python3 -m pytest fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py -q` - passed
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py -q` - passed
- Focused combined pytest for core + DuckDB literal parity + forced fallback - 18 passed
- FHIRPath R4 conformance - 935 passed, 0 failed
