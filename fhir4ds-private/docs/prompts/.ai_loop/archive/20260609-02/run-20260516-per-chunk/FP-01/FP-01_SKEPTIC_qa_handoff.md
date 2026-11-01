# QA Handoff — FP-01 / SKEPTIC

## Scope
- Chunk: FP-01 FHIRPath §4.1 Literals.
- Personality: SKEPTIC.
- Paths compared: Python core/direct DuckDB fallback UDFs and native C++ DuckDB extension.
- Spec consulted: FHIRPath N1 §4.1.2 String and formal grammar. The spec defines `\uXXXX` as a Unicode escape where `XXXX` is hexadecimal.

## Hypotheses Probed
- String escape handling might differ between Python and C++.
- Time/date/dateTime partial literal handling might diverge across paths.
- Large integer and decimal literal serialization might diverge across paths.
- Calendar duration quantity literals might diverge from UCUM quoted quantity literals.

## Findings
- `QA-001` HIGH: Python string literal unescape decoded only decimal `\u` escapes. Expressions such as `'\u00E9'` and `'\u03A9'` returned `u00E9`/`u03A9` in Python fallback/direct UDFs, while the native C++ DuckDB extension returned the correct Unicode characters.

## Evidence
- Probe: `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/fp01_skeptic_literal_probe.py`
- Before fix summary: native C++ loaded; 2 mismatches for `'\u00E9'` and `'\u03A9'`.
- After fix summary: native C++ loaded; mismatch count 0.

## Validation Run By QA
- `python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/fp01_skeptic_literal_probe.py`
- `python3 -m pytest fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py::test_string_unicode_escape_accepts_hex_letters fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py::test_string_escape_outputs_match_python_fallback fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py::test_unicode_hex_letter_string_escapes_match_spec -q`
- `python3 -m pytest fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py -q`
- `python3 conformance/scripts/run_fhirpath_r4.py`

## Notes For Remediation
- Focused fix is in the Python core string literal evaluator: decode `\u[0-9a-fA-F]{4}` with base 16.
- Keep the C++ lexer behavior unchanged; it already decodes hex-letter Unicode escapes correctly.
