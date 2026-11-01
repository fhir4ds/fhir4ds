# QA Handoff — FP-17 SKEPTIC (iteration 1, 2026-08-18)

## Chunk
FHIRPath §6.5 Boolean Logic: `and`, `or`, `not()`, `xor`, `implies`.

## Method
Dual-path probe (native C++ `fhirpath.duckdb_extension` vs forced Python
fallback via `duckdb.__version__` override) through the `fhirpath()` UDT/UDF
surface, plus exported-helper API audit (`operators.boolean_and/or/xor/implies/
not`) and `fhirpath_is_valid` classification checks. Probe:
`.temp/qa/fp17_skeptic/probe.py` (119 cases) + round-2 edge battery (21 cases).

## Coverage
- Full 3VL truth tables for and/or/xor/implies (true/false/{} x true/false/{})
  via literals AND resource fields (present booleans, absent fields -> {}).
- Short-circuit semantics: false and {} -> false, true and {} -> {}, true or {}
  -> true, false or {} -> {}, false implies X -> true (incl. fixture-pinned
  false implies {} = true), {} implies true -> true, {} implies false/{} -> {}.
- Non-boolean singletons (§4.5 doctrine): 'x'/1 truthy through all 5 operators,
  `.not()` on non-boolean -> false.
- Multi-item operands: raise in core/helpers; wrapper NULL on BOTH engines
  (row resilience, established intent); helper API raises FHIRPathError
  (no 13th "exported helper API forgotten" instance here).
- Precedence/associativity (§6.8): and > or=xor (left-assoc) > implies;
  parenthesization; chained operators; `not()` as function form only.
- Empty-propagating subexpressions feeding boolean ops: comparisons of unequal
  non-empty values are false (not {}), (1/0) -> {}, missing-field propagation.
- is_valid: `1 and true`, `'x' implies 5` are VALID (runtime typing, not
  syntax); leading/trailing operator forms invalid; bare `not(...)` invalid
  grammar (function-only operator).
- Fixture anchoring: official R4 tests-fhir-r4.xml testBooleanLogicXOr1-9 and
  testBooleanImplies1-9 match implementation tables exactly.

## Results
- 0 parity diffs between native and fallback engines across all 140 probe cases.
- 0 spec violations. All behavior conforms to FHIRPath R4 §6.5 tables.
- Conformance baseline after probing: 2832/2832 (ViewDef 144, FHIRPath 935,
  CQL 1706, DQM 47) — no regression.

## Issues
None. Zero non-terminal CRITICAL/HIGH/MEDIUM issues -> clean exit eligible at
min_iterations=1.

## Probed earlier expectations that were MY errors (not bugs)
- `deceasedBoolean implies active` -> true (false antecedent, vacuous truth).
- `false or (false implies true)` -> true.
- `(s = 'nope') and true` -> false (unequal non-empty = false, not empty).
