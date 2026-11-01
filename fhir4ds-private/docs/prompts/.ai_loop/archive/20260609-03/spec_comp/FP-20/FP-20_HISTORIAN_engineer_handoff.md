# Engineer Handoff — FP-20 HISTORIAN

Issue resolved:
- `QA-001` MEDIUM, FHIRPath N1 §12 / §9: native external constants rejected
  valid hidden whitespace/comments between `%` and the identifier/string
  payload.

Root cause:
- The native lexer tokenized `%` and the environment-variable payload in one
  branch, but it did not consume hidden whitespace/comment tokens after `%`.
  This made `% 'ucum'`, `%/*grammar*/'ucum'`, `%//grammar\n'ucum'`, and
  `% \`context\`.id` invalid in native while the forced Python fallback
  accepted them.

Fix:
- `extensions/fhirpath/src/fhirpath/lexer.cpp` now calls `skipWhitespace()`
  immediately after consuming `%`.
- Added focused native/fallback parity coverage in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py`.
- Added native sqllogictest assertions in
  `extensions/fhirpath/test/sql/fhirpath.test`.
- Rebuilt and copied the bundled extension to
  `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.
- Updated affected `AGENTS.md` files.

Validation completed:
- `python3 .temp/qa/fp20_historian_probe.py`
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py -q`
- `extensions/fhirpath/build/release/test/unittest "*fhirpath*"`

Next phase:
- ARCHITECT.
