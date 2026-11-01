# Engineer Handoff - FP-11 HISTORIAN

## Triage Table

| Issue | Severity | Category | Result |
| --- | --- | --- | --- |
| `QA-001` | MEDIUM | SPEC_VIOLATION | RESOLVED |
| `QA-002` | MEDIUM | SPEC_VIOLATION | RESOLVED |
| `QA-003` | MEDIUM | SPEC_VIOLATION | RESOLVED |

## Fixes

- `QA-001`: Fixed native C++ `abs()` and unary negation for Integer/Long
  values so representable 64-bit integer results do not pass through `double`.
  `9223372036854775807L.abs()` and `(-9223372036854775807L).abs()` now return
  `9223372036854775807`.
- `QA-002`: Fixed forced Python fallback Quantity detection for §5.7 Math by
  routing singleton Quantity detection through `util.parse_value(...)`, which
  recognizes ResourceNode/plain-dict FHIR Quantity JSON.
- `QA-003`: Fixed fallback Decimal `toString()` formatting so integral Decimal
  values include `.0`, matching the §5.5 Decimal representation and native
  behavior for `2.power(3).toString()`.

Spec source used:
https://raw.githubusercontent.com/HL7/FHIRPath/refs/heads/master/input/pages/index.md

## Files Changed

- `fhir4ds/fhirpath/engine/invocations/math.py`
- `fhir4ds/fhirpath/engine/invocations/misc.py`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_math_parity.py`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `.temp/qa/fp11_historian_fresh_probe.py`
- `.ai_loop/evolution.json`, `qa_handoff.md`
- `fhir4ds/fhirpath/AGENTS.md`, `extensions/fhirpath/AGENTS.md`

## Validation

```bash
python3 .temp/qa/fp11_historian_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_math_parity.py -q
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py -q
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/unit/test_math.py -q
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/unit/test_conversion.py -q
cmake --build extensions/fhirpath/build/release --config Release -j 8
extensions/fhirpath/build/release/test/unittest "*fhirpath*"
git diff --check -- fhir4ds/fhirpath extensions/fhirpath fhir4ds-private/docs/prompts/.ai_loop .temp/qa/fp11_historian_fresh_probe.py
python3 -m json.tool fhir4ds-private/docs/prompts/.ai_loop/evolution.json
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
```

Results:
- Fresh probe passed: 48 expressions.
- Math parity passed: 7/7.
- Conversion parity passed: 23/23.
- Unit math passed: 105/105.
- Unit conversion passed: 113/113.
- Native sqllogictest/unittest passed: 874 assertions.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47, overall 2822/2822.
- Rebuilt and bundled extension hashes match:
  `a39a4d50f1f8f1cbf3cd0438f8f6c96070e5455ed2032a437b57e1cdd96e3fe2`.
