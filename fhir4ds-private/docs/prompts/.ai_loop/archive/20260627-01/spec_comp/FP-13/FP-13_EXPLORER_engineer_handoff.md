# Engineer Handoff — FP-13 EXPLORER

Date: 2026-06-12
Iteration: 1

## Triage

| ID | Category | Severity | Root Cause | Terminal Status |
| --- | --- | --- | --- | --- |
| QA-001 | SPEC_VIOLATION | MEDIUM | Python fallback Quantity equivalence converted both operands to base units and then applied decimal equivalence to the converted values, which let conversion-introduced precision change the §6.1 result. | VERIFIED |
| QA-002 | SPEC_VIOLATION | MEDIUM | Native C++ JSON numeric equality/equivalence compared raw JSON numbers via `yyjson_get_num()` / `double`, collapsing distinct Integer/Long-sized values above binary floating-point exactness. | VERIFIED |

## Fixes

- Updated `fhir4ds/fhirpath/engine/invocations/equality.py` so different-unit Quantity equivalence compares converted base values using a half-width tolerance derived from each original operand's authored precision and conversion scale.
- Updated `extensions/fhirpath/src/fhirpath/evaluator.cpp` with exact JSON number canonicalization for equality and zero-decimal equivalence, and routed direct `FPValue` JSON numeric comparisons through those helpers before generic numeric `double` comparison.
- Added regression coverage in `fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py`.
- Added native SQL assertions in `extensions/fhirpath/test/sql/fhirpath.test`.
- Rebuilt and copied `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

## Verification

```bash
python3 .temp/qa/fp13_explorer_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py -q
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_existence_parity.py -q
cmake --build extensions/fhirpath/build/release --config Release -j 8
extensions/fhirpath/build/release/test/unittest "*fhirpath*"
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
git diff --check -- fhir4ds/fhirpath extensions/fhirpath fhir4ds-private/docs/prompts/.ai_loop .temp/qa/fp13_explorer_fresh_probe.py .temp/architect/golden_standard.md
python3 -m json.tool fhir4ds-private/docs/prompts/.ai_loop/evolution.json
sha256sum extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension extensions/fhirpath/build/release/repository/v1.5.2/linux_amd64/fhirpath.duckdb_extension fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension
```

Results:
- Fresh probe passed, 43 expressions.
- Equality parity passed, 13/13.
- Collection/existence parity passed, 24/24.
- Native sqllogictest/unittest passed, 1000 assertions.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- Extension hashes matched: `7ead65e01b040370a4b71ff47b6e949500b28ef944edf4eb1ae55cd62e575845`.

No open implementation issues remain for this chunk.
