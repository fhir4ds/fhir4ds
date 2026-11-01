# Engineer Handoff - FP-17 SKEPTIC

## Triage

| Issue | Severity | Category | Status |
|---|---:|---|---|
| QA-001 | HIGH | SPEC_VIOLATION | VERIFIED |

## Fix

QA-001 root cause was native C++ `collectionIsBool()` returning `false` for multi-item collections. Boolean operator callers interpreted that as an empty/unknown operand, so expressions such as `arr or t`, `arr and f`, and `arr implies t` returned concrete truth-table results. Forced Python fallback raised singleton Boolean errors and public wrappers converted them to empty/NULL.

Changed `extensions/fhirpath/src/fhirpath/evaluator.cpp::collectionIsBool()` to throw `FHIRPathSpecError` when `col.size() > 1`. This preserves the existing public UDF row-resilience behavior through catch-to-empty/NULL while matching forced Python fallback. The intentional `false implies <expr>` short-circuit remains unchanged.

Added regression coverage in `fhir4ds/fhirpath/duckdb/tests/integration/test_boolean_logic_parity.py` that compares SQL-loaded native C++ and SQL-registered forced Python fallback for multi-item operands.

Rebuilt native extension:

```bash
cd extensions/fhirpath
cmake --build build/release --config Release -j 8
cd /mnt/d/fhir4ds
cp extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension
```

## Validation

Failing reproducer before fix:

```bash
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_boolean_logic_parity.py::test_multi_item_boolean_operands_return_empty_in_native_and_fallback -q --tb=short
```

Result before fix: failed with native `(['true'], '[true]', True)` vs fallback `([], None, None)` for `arr or t`.

Post-fix commands/results:

```bash
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_boolean_logic_parity.py -q --tb=short
```

Result: 2 passed.

```bash
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_boolean_logic_parity.py fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py -q --tb=short
```

Result: 19 passed.

```bash
cd extensions/fhirpath && ./build/release/test/unittest '*fhirpath*'
```

Result: all tests passed, 250 assertions in 2 test cases.

```bash
python3 conformance/scripts/run_dqm.py | grep -E "CMS56|FAILED|PASSED|Accuracy|accuracy|Summary|passed|Suite"
```

Result: 47/47 measures passed; CMS56 passed.

```bash
python3 conformance/scripts/run_all.py 2>&1 | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM|SUCCESS|Summary"
```

Result: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2822/2822, SUCCESS.

## Notes

One first master conformance run reported transient DQM CMS56 accuracy 82.8% (46/47 DQM) after all FHIRPath/CQL suites passed. A focused DQM rerun and a second master run both passed 47/47 and 2822/2822 overall. No code changes were made for DQM.
