# Engineer Handoff — FP-01 / SKEPTIC

## Triage
| Issue | Severity | Category | Status |
|---|---:|---|---|
| QA-001 | HIGH | SPEC_VIOLATION | RESOLVED |

## Fix
- Root cause: `fhir4ds/fhirpath/engine/evaluators/__init__.py::string_literal` decoded only `\u` escapes with four decimal digits.
- Spec reference: FHIRPath N1 §4.1.2 String defines `\uXXXX` as a Unicode character escape where `XXXX` is hexadecimal; the formal grammar defines `UNICODE` as `u HEX HEX HEX HEX`.
- Change: generalized the regex to `\\(u[0-9a-fA-F]{4})`, reusing the existing base-16 `match()` helper.

## Tests Added
- `fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py::test_string_unicode_escape_accepts_hex_letters`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py::test_unicode_hex_letter_string_escapes_match_spec`
- Expanded `test_string_escape_outputs_match_python_fallback` to cover `'\u00E9'` and `'\u03A9'`.

## Validation
- Targeted parity probe: native C++ loaded; mismatch count 0.
- `python3 -m pytest fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py -q` — 13 passed.
- `python3 conformance/scripts/run_fhirpath_r4.py` — 935/935 passed.

## New Issues
- None.
