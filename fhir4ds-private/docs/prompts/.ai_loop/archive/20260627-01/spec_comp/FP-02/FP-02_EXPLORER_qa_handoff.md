# QA Handoff - SPEC FP-02 EXPLORER

## Scope

- Chunk: FP-02, FHIRPath §4.2 Operators, §4.3 Function Invocations, §4.4 Null/empty propagation, §4.5 singleton collection evaluation.
- Personality: EXPLORER.
- Spec source checked fresh: HL7 FHIRPath CI/source content in `.temp/qa/fhirpath_spec_index.md`.

## Spec Notes

- §4.2 says Boolean operator operands are evaluated as Booleans using singleton collection evaluation before applying three-valued Boolean logic.
- §4.5 says a collection passed where a single item is expected becomes its single value, empty stays empty, and multi-item collections end evaluation with an error.
- The spec also warns implementations may short-circuit only when semantics are unchanged; authors should use `iif()` when short-circuit behavior is required to avoid errors.

## Exploration

Hypotheses tested:

- Malformed collection function arities diverge between native and forced Python fallback.
- Dot invocation of singleton-only functions over empty or multi-item collections leaks non-spec values.
- Operator keyword/function ambiguity around `contains` differs between parsers.
- Empty propagation through union, string functions, and Boolean logic breaks under unusual chains.
- `implies` short-circuiting skips RHS singleton validation.

Fresh probe:

- `.temp/qa/fp02_explorer_fresh_probe.py`

Pre-fix result:

```text
FAIL false implies (1 | 2)
  expected: ([], None, None, None, False)
  native:   (['true'], 'true', '[true]', True, True)
  fallback: (['true'], 'true', '[true]', True, True)
```

## Finding

`QA-001` HIGH, SPEC_VIOLATION: native DuckDB/C++ and forced Python fallback both short-circuit `false implies <rhs>` before applying §4.5 Boolean singleton evaluation to `<rhs>`. Multi-item RHS expressions such as `false implies (1 | 2)`, `false implies arr`, and `false implies iif(true, 1 | 2, 3)` return `true` instead of row-resilient empty/NULL results. Constant multi-item RHS forms also make `fhirpath_is_valid()` return true.

## Handoff

Fix both:

- Native `extensions/fhirpath/src/fhirpath/evaluator.cpp::Evaluator::evalBinaryOp` for `implies`.
- Python fallback `fhir4ds/fhirpath/engine/invocations/logic.py::implies_op`.

Add/adjust parity coverage in `test_boolean_logic_parity.py` and native sqllogictest coverage. Rebuild and copy the bundled extension after native changes.
