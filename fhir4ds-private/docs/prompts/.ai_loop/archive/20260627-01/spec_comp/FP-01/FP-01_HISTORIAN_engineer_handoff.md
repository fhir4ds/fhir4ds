# Engineer Handoff — FP-01 HISTORIAN

## Issue Status

`QA-001` MEDIUM `SPEC_VIOLATION` — RESOLVED.

Spec citation: FHIRPath §4.1 String literals. `\uXXXX` escapes are UTF-16 code
units; surrogate code units must be paired into a valid Unicode scalar value.

## Root Cause

Python `_unescape_fhirpath_string()` converted any valid four-digit Unicode
escape into `chr(code_unit)`, including lone surrogate halves. Native
`Lexer::readString()` did the equivalent through `appendUnicodeEscape()`.
That made `'\uD834'` validate as a legal string literal and then fail later
when DuckDB tried to materialize invalid Unicode.

## Fix

- Added surrogate-pair validation in
  `fhir4ds/fhirpath/engine/evaluators/__init__.py`.
- Added matching surrogate-pair validation in
  `extensions/fhirpath/src/fhirpath/lexer.cpp`.
- Preserved existing malformed non-surrogate escape behavior, including
  `\u005` becoming `u005`.
- Added regression coverage in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py`.
- Added native sqllogictest coverage in
  `extensions/fhirpath/test/sql/fhirpath.test`.
- Rebuilt and copied the bundled native extension to
  `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

## Validation

- `python3 .temp/qa/fp01_historian_fresh_probe.py` — PASS.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py -q` — 19 passed.
- `./build/release/test/unittest "*fhirpath*"` from `extensions/fhirpath` — 716 assertions passed.
- `python3 conformance/scripts/run_fhirpath_r4.py`; parsed report — 935/935 passed.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM|COMPLIANCE|Passed|Total|SUCCESS" > validation_summary.log && cat validation_summary.log` — 2822/2822 overall.

## Notes

The first native patch also rejected short malformed `\u` sequences such as
`\u005`; focused pytest caught that regression. Per the recovery gate, I wrote
`state/deep_research_findings.md` and narrowed the C++ return signal to
surrogate-only failures before rerunning validation.
