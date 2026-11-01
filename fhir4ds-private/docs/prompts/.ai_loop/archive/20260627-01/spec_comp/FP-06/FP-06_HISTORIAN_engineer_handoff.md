# Engineer Handoff - FP-06 HISTORIAN

Date: 2026-06-12

Issues handled:
- `QA-001` MEDIUM `RESOLVED`
- `ARCH-001` HIGH `RESOLVED`

Triage:
| Issue | Category | Reproduced | Terminal Status |
| --- | --- | --- | --- |
| `QA-001` | `SPEC_VIOLATION` | Yes, with `.temp/qa/fp06_historian_fresh_probe.py` before the fix | `RESOLVED` |
| `ARCH-001` | `API_CONTRACT` | Yes, with the expanded fresh probe and inline native/fallback comparison | `RESOLVED` |

Spec grounding:
- FHIRPath §5.5 conversion functions operate on empty-or-singleton input collections, with multi-item inputs signaling an error to the calling environment.
- FHIRPath §5.5.3 integer conversion uses exact integer-string grammar and Integer semantics.
- FHIRPath §4.1 defines Integer literals as 32-bit signed values and Unicode string escapes as valid scalar values; invalid literals make the expression invalid.

Fixes:
- `QA-001`: Updated `fhir4ds/fhirpath/duckdb/udf.py::_is_row_resilient_invalid_literal()` to include `_has_out_of_range_integer_literal()`, so forced Python fallback result UDFs return empty/NULL for out-of-range Integer literal expressions while `fhirpath_is_valid()` remains false.
- `ARCH-001`: Updated native `extensions/fhirpath/src/fhirpath_extension.cpp::EvaluateFhirpath()` to return an empty collection when `GetOrCompile()` returns no AST, matching existing row-resilience for evaluator `FHIRPathSpecError` and preserving `fhirpath_is_valid()` as the validity signal.
- Removed the known trailing whitespace in `extensions/fhirpath/src/fhirpath/evaluator.cpp`.
- Rebuilt and copied `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

Regression coverage:
- `.temp/qa/fp06_historian_fresh_probe.py` now covers 40 expressions across `iif`, Boolean conversion, Integer conversion, out-of-range Integer literal result wrappers, and an invalid surrogate literal control for the same native wrapper class.
- `test_conversion_parity.py` covers positive and negative out-of-range Integer literals in native and forced fallback DuckDB registrations.
- `test_literal_parity.py` now asserts invalid surrogate string literals are row-resilient across native and fallback result UDFs, not just `fhirpath_is_valid()`.
- `extensions/fhirpath/test/sql/fhirpath.test` has native assertions for invalid Integer and surrogate literal result wrappers.

Validation run:
```bash
python3 .temp/qa/fp06_historian_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py -q
cmake --build build/release --config Release -j 8
cp extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension
./build/release/test/unittest "*fhirpath*"
git diff --check -- fhir4ds/fhirpath extensions/fhirpath
sha256sum extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension extensions/fhirpath/build/release/repository/v1.5.2/linux_amd64/fhirpath.duckdb_extension
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
```

Validation result:
- Fresh probe passed, 40 expressions.
- Conversion plus literal parity passed, 39/39.
- Native fhirpath unittest passed, 764 assertions.
- `git diff --check -- fhir4ds/fhirpath extensions/fhirpath` passed.
- Extension hashes matched: `100f61ee3cb8d0702ea5a61fa32e9b326f9e1ecc631fb835236ebf5ac2ea2a18`.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

Review finding intersection:
- The native wrapper fix addresses the `REV-FP-001` class for public result UDF parser/lexer invalid expressions and the invalid surrogate reproducer covered by the focused tests.
- The whitespace cleanup addresses `REV-FP-004`.
- `REV-FP-002` and `REV-FP-003` remain outside this FP-06 fix.
