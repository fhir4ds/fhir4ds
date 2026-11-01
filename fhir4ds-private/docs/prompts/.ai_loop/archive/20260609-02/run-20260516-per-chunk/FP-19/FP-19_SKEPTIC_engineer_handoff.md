FP-19 SKEPTIC remediation handoff

Resolved issues:
- FP19-SK-001: Implemented FHIRPath string-escape handling for delimited identifiers in the Python core and native C++ lexer. Expressions such as `` `back\`tick` ``, `` `line\nbreak` ``, and `` `omega\u03A9` `` now resolve the intended model keys through native and forced Python fallback DuckDB paths.
- FP19-SK-002: Added a Python parser EOF check so direct core evaluation rejects expressions with trailing unconsumed tokens, e.g. `1 Month`, instead of evaluating only the prefix `1`.

Related native source/binary drift fixed during rebuild:
- Rebuilt and copied `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.
- While validating the rebuilt binary, existing literal parity tests exposed native `fhirpath_is_valid()` accepting malformed temporal shapes (`@2014-1`, `@2014-01-2`, `@2014-01-25T14+09`). Tightened native temporal lexing for malformed date separators and incomplete DateTime timezone offsets without breaking FP-18 no-whitespace arithmetic (`@2016-02-29T23:59+61 seconds` remains valid arithmetic).

Validation:
- `python3 -m pytest fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py -q`: 14 passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_arithmetic_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_aggregate_lexical_parity.py -q`: 39 passed.
- `cd extensions/fhirpath && ./build/release/test/unittest "*fhirpath*"`: 272 assertions passed.
- Full conformance summary: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
