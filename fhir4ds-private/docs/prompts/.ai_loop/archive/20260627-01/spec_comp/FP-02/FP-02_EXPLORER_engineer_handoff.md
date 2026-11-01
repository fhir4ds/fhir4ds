# Engineer Handoff - SPEC FP-02 EXPLORER

## Issue Status

- `QA-001` HIGH `SPEC_VIOLATION`: RESOLVED.

## Root Cause

Python fallback `fhir4ds/fhirpath/engine/invocations/logic.py::implies_op` and native C++ `extensions/fhirpath/src/fhirpath/evaluator.cpp::Evaluator::evalBinaryOp` returned `true` for a false left operand before applying FHIRPath §4.5 singleton Boolean evaluation to the RHS.

FHIRPath §4.2 says Boolean operands are evaluated as Booleans using §4.5 before the three-valued truth table is applied. A multi-item RHS therefore must signal an evaluation error even when the LHS is false.

## Fix

- Changed Python fallback `implies_op` to coerce RHS before the false-LHS truth-table return.
- Changed native C++ `evalBinaryOp` `implies` branch to evaluate and coerce RHS before the false-LHS truth-table return.
- Added regression coverage for constant multi-item RHS forms and dynamic resource-backed multi-item RHS forms.
- Rebuilt the native extension and copied it to `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.
- Updated local FHIRPath AGENTS notes, including stale text that called the old false-LHS shortcut intentional.

## Files Changed

- `fhir4ds/fhirpath/engine/invocations/logic.py`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_boolean_logic_parity.py`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `.temp/qa/fp02_explorer_fresh_probe.py`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`

## Validation

- `python3 .temp/qa/fp02_explorer_fresh_probe.py` passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_boolean_logic_parity.py -q` passed, 53/53.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py -q` passed, 9/9.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py -q` passed, 4/4.
- `./build/release/test/unittest "*fhirpath*"` passed, 730 assertions.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## New Issues

None.
