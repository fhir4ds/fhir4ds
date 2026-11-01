# Engineer Handoff - FP-10 HISTORIAN

Date: 2026-06-12

## Issue Triage

| Issue | Severity | Category | Status |
| --- | --- | --- | --- |
| `QA-001` | MEDIUM | SPEC_VIOLATION | RESOLVED |

## Root Cause

Native C++ `fn_upper()` and `fn_lower()` in
`extensions/fhirpath/src/fhirpath/evaluator.cpp` used a local hand-written
Unicode case table. That table covered ASCII, selected Latin, Greek, and
Cyrillic ranges but missed valid Unicode case mappings and full uppercase
expansions. The forced Python fallback used Python Unicode case conversion and
therefore returned the spec-expected results for the fresh probe.

Spec basis: FHIRPath §5.6.6 and §5.6.7 define `upper()` / `lower()` as
converting all characters in the singleton input string to upper/lower case;
FHIRPath string characters are Unicode scalar values.

## Fix

- Added native UTF-8 codepoint decode/encode helpers backed by DuckDB's
  vendored `utf8proc`.
- Replaced the duplicated `fn_upper()` / `fn_lower()` hand-coded range tables
  with a shared codepoint case-mapping path.
- Added explicit full uppercase expansion coverage for mappings not
  representable by `utf8proc`'s single-codepoint `toupper` API, including
  ligatures and `ß -> SS`.
- Preserved the lower-case full expansion for `İ -> i + combining dot`.
- Added permanent regression coverage in:
  - `fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py`
  - `extensions/fhirpath/test/sql/fhirpath.test`
- Rebuilt and copied the bundled native extension.

## Validation

Commands run:

```bash
python3 .temp/qa/fp10_historian_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py -q
extensions/fhirpath/build/release/test/unittest "*fhirpath*"
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/unit/test_string.py::TestUpper fhir4ds/fhirpath/duckdb/tests/unit/test_string.py::TestMatches fhir4ds/fhirpath/duckdb/tests/unit/test_string.py::TestReplaceMatches fhir4ds/fhirpath/duckdb/tests/unit/test_string.py::TestToChars -q
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
git diff --check -- extensions/fhirpath/src/fhirpath/evaluator.cpp extensions/fhirpath/test/sql/fhirpath.test fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py fhir4ds-private/docs/prompts/.ai_loop .temp/qa/fp10_historian_fresh_probe.py
sha256sum extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension extensions/fhirpath/build/release/repository/v1.5.2/linux_amd64/fhirpath.duckdb_extension
```

Results:

- Fresh probe passed: 29 expressions.
- Transform parity passed: 4/4.
- Native FHIRPath unittest/sqllogictest passed: 830 assertions.
- Unit string checks passed: 28/28.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935, CQL
  1706/1706, DQM 47/47, overall 2822/2822.
- Diff check passed.
- Extension hashes matched across build, repository, and package bundle:
  `616b265daaaf854f05eef350784bd7369d78c33505dafd7f5b63ef37e110a3da`.

## New Issues

None.
