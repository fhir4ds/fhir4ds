# Engineer Handoff - FP-10 SKEPTIC

## Issue Status

- `QA-001` - MEDIUM - RESOLVED

## Root Cause

The implementation was aligned with an older interpretation of `matches()`:
both forced Python fallback and native DuckDB/C++ used full-string matching.
The current HL7 FHIRPath String Manipulation section shows regex search
semantics for `matches()` and adds optional `i`/`m` flags to both `matches()`
and `replaceMatches()`.

The same older signature model existed in:

- Python invocation arity metadata.
- Python sparse `fhirpath_is_valid()` prechecks.
- Native C++ arity checks and evaluator dispatch.
- Native C++ `fn_matches()` using `std::regex_match`.

## Fix Summary

- Python fallback:
  - `matches()` now uses regex search semantics.
  - `matches()` and `replaceMatches()` accept optional `i`/`m` flags.
  - Invalid flag characters raise `FHIRPathError` and remain row-resilient at
    public DuckDB UDF boundaries.
  - Sparse validation compiles regex literals with literal flags where present.

- Native C++:
  - `fn_matches()` now uses `std::regex_search`.
  - Native arity checks accept `matches(regex, [flags])` and
    `replaceMatches(regex, substitution, [flags])`.
  - `i` maps to `std::regex_constants::icase`.
  - `m` enables multiline anchor behavior; `replaceMatches()` uses line-wise
    replacement for anchored multiline patterns so line separators are
    preserved.

- Tests:
  - Added/updated fresh probe, focused parity tests, Python unit tests, and
    native sqllogictest assertions.
  - Rebuilt and copied the bundled native extension.

## Key Files Changed

- `.temp/qa/fp10_skeptic_fresh_probe.py`
- `fhir4ds/fhirpath/engine/invocations/strings.py`
- `fhir4ds/fhirpath/engine/invocations/__init__.py`
- `fhir4ds/fhirpath/duckdb/udf.py`
- `fhir4ds/fhirpath/duckdb/functions/string.py`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py`
- `fhir4ds/fhirpath/tests/unit/test_new_functions.py`
- `fhir4ds/fhirpath/duckdb/tests/unit/test_string.py`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `extensions/fhirpath/src/fhirpath/evaluator.hpp`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`

## Validation

Passed:

```bash
python3 .temp/qa/fp10_skeptic_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py -q
python3 -m pytest fhir4ds/fhirpath/tests/unit/test_new_functions.py::TestMatchesSearchSemantics fhir4ds/fhirpath/duckdb/tests/unit/test_string.py::TestMatches fhir4ds/fhirpath/duckdb/tests/unit/test_string.py::TestReplaceMatches -q
cmake --build extensions/fhirpath/build/release --config Release -j 8
extensions/fhirpath/build/release/test/unittest "*fhirpath*"
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
git diff --check -- fhir4ds/fhirpath extensions/fhirpath fhir4ds-private/docs/prompts/.ai_loop .temp/qa/fp10_skeptic_fresh_probe.py
sha256sum extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension extensions/fhirpath/build/release/repository/v1.5.2/linux_amd64/fhirpath.duckdb_extension
```

Results:

- Fresh probe passed: 14 expressions x 2 paths.
- Focused parity passed: 4/4.
- Focused unit checks passed: 29/29.
- Native suite passed: 818 assertions.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47, overall 2822/2822.
- Extension hashes matched across build, repository, and package bundle.

## New Issues

None.
