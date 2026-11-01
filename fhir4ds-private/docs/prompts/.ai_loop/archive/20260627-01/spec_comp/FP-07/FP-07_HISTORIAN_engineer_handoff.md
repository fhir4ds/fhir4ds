# Engineer Handoff - FP-07 HISTORIAN

Date: 2026-06-12

## Issue Status

- `QA-001` MEDIUM `RESOLVED`: FHIRPath §5.5.6 string Long Decimal conversion.

## Root Cause

Both implementation paths treated String Decimal conversion as only the plain
Decimal regex class:

- Python fallback: `numRegex = ^[+-]?\d+(\.\d+)?$` in
  `fhir4ds/fhirpath/engine/invocations/misc.py`.
- Native C++: `isFHIRPathDecimalString()` in
  `extensions/fhirpath/src/fhirpath/evaluator.cpp`.

That excluded the current §5.5.6 example String value `'42L'`, even though the
newer Long literal path `42L.toDecimal()` was already supported.

## Fix

Added a narrow String Long Decimal grammar in both implementations:
optional sign, one or more digits, and uppercase `L`.

The suffix is stripped before Decimal parsing. Malformed forms remain rejected:
`1LL`, `1.0L`, lowercase `1l`, exponent notation, and whitespace-padded
strings.

Files changed:
- `fhir4ds/fhirpath/engine/invocations/misc.py`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `.temp/qa/fp07_historian_fresh_probe.py`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`

## Validation

Passed:

```bash
python3 .temp/qa/fp07_historian_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py -q
cmake --build build/release --config Release -j 8
./build/release/test/unittest "*fhirpath*"
git diff --check -- fhir4ds/fhirpath extensions/fhirpath fhir4ds-private/docs/prompts/.ai_loop .temp/qa/fp07_historian_fresh_probe.py
cmp -s extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension
sha256sum extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension extensions/fhirpath/build/release/repository/v1.5.2/linux_amd64/fhirpath.duckdb_extension
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
```

Results:
- Fresh probe passed 19 expressions.
- Focused conversion parity passed 20/20.
- Native FHIRPath tests passed 776 assertions.
- Extension hashes matched across build, package, and local repository copies.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935, CQL
  1706/1706, DQM 47/47, overall 2822/2822.

No new issues discovered.
