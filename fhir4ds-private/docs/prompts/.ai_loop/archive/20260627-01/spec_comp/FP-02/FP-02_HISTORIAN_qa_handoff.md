# QA Handoff - SPEC FP-02 HISTORIAN

Iteration: 1
Personality: HISTORIAN
Chunk: FHIRPath §4.2 Operators, §4.3 Function Invocations, §4.4 Null and Empty propagation, §4.5 singleton collection evaluation

## Spec Basis

- Official source consulted: `https://raw.githubusercontent.com/HL7/FHIRPath/refs/heads/master/input/pages/index.md`
- §4.3 says functions are invocations with arguments and that arguments must satisfy the function parameter contract.
- §4.4/§4.5 establish empty propagation and singleton conversion/error rules.
- The string function signature is `trim() : String`; argument-bearing `trim(...)` calls are not valid invocations.

## Fresh Probe

Created `.temp/qa/fp02_historian_fresh_probe.py`.

The probe compares native DuckDB/C++ registration and a forced Python fallback
registration for:

- Boolean empty propagation truth-table cells.
- Non-Boolean singleton Boolean evaluation.
- String concatenation versus arithmetic empty propagation.
- Invocation precedence around unary `-`.
- Runtime singleton row resilience.
- Invalid function invocation arity for `trim`.

## Issue Found

`QA-001` MEDIUM, OPEN.

Native DuckDB/C++ accepts `s.trim(1)` and `s.trim({})`, returning the same value
as `s.trim()` and reporting `fhirpath_is_valid=true`. Forced Python fallback
returns public empty/NULL results but also reports `fhirpath_is_valid=true`.

Expected: public result UDFs return empty/NULL and both validators report
`fhirpath_is_valid=false` for argument-bearing `trim(...)`.

Focused failing command:

```bash
python3 .temp/qa/fp02_historian_fresh_probe.py
```

Observed failing cases:

- native `s.trim(1)` -> `['abc']`, valid true; expected empty/NULL, valid false
- fallback `s.trim(1)` -> empty/NULL, valid true; expected empty/NULL, valid false
- native `s.trim({})` -> `['abc']`, valid true; expected empty/NULL, valid false
- fallback `s.trim({})` -> empty/NULL, valid true; expected empty/NULL, valid false

## Suggested Fix Surface

- Native: add `trim` to the exact zero-argument function validation in
  `extensions/fhirpath/src/fhirpath/evaluator.cpp`.
- Fallback: add `trim` to the Python fallback static string-function arity
  precheck so `fhirpath_is_valid('s.trim(1)')` becomes false.
- Tests: add native/fallback parity coverage for `s.trim(1)` and `s.trim({})`;
  add native sqllogictest assertions; rebuild and copy the bundled extension.
