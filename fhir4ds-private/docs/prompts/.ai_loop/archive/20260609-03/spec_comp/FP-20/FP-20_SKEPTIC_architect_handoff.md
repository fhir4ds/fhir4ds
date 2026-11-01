# Architect Handoff — FP-20 SKEPTIC

## Golden Standard
Wrote `.temp/architect/golden_standard.md` with 10 invariants for FHIRPath environment/reflection surfaces: native and forced fallback parity, pre-dispatch arity validation, singleton type enforcement, explicit environment-variable lookup, scoped `defineVariable()` behavior, bundled-extension alignment, and validation coverage.

## Structural Audit
The implemented changes are structurally narrow and align with the existing evaluator design. Both fixes live in native `Evaluator::evalFunction()` where public helper signatures are already guarded. The patch does not add model-specific type knowledge, does not alter fallback behavior, and does not broaden public API semantics. It closes silent native argument-ignoring paths by throwing `FHIRPathSpecError`, preserving row-resilient public UDF behavior through existing wrapper exception handling.

## QA Enforcer Gate
QA was sufficient for SKEPTIC scope. It used a fresh native-vs-forced-fallback probe, challenged unknown variables, scoped `defineVariable()` leakage, malformed helper arities, type specifier errors, formal syntax rejection, and current TypeInfo public shape. No `RETRY_QA` is needed.

## Issue Summary
Two MEDIUM `SPEC_VIOLATION` issues were found and resolved: native `type()` ignored unexpected arguments, and native `defineVariable()` accepted malformed call shapes. Focused parity, native sqllogictest, and full conformance all passed.

## Validation Evidence
- `python3 .temp/qa/fp20_skeptic_probe.py`: passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py -q`: 8 passed.
- `./build/release/test/unittest "*fhirpath*"`: 686 assertions passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Recommended Fix Order
No further engineer work is required for this pass. Continue with the next FP-20 personality from the outer spec compliance orchestrator.
