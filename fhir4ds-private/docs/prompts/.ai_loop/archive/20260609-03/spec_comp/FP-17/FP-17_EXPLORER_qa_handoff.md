# QA Handoff — FP-17 EXPLORER

Scope: FHIRPath N1 §6.5 Boolean logic, with §4.5 singleton evaluation and
§6.8 operator precedence as supporting normative rules.

Personality: EXPLORER.

Fresh probe:
- Added `.temp/qa/fp17_explorer_probe.py`.
- Compared bundled native C++ DuckDB UDFs, forced Python fallback SQL UDFs,
  and direct Python fallback helpers.
- Covered 21 edge expressions and 9 `fhirpath_is_valid()` cases.

Edge combinations covered:
- `implies` as the lowest-precedence Boolean operator:
  `t or f implies f`, `f implies t and f`.
- `and` higher than `or`/`xor`, and `or`/`xor` same-level left-to-right:
  `t xor t and f`, `t or f xor t`, `t xor {} or t`.
- Empty propagation across chained expressions:
  `t and {} or f`, `f or {} and t`.
- Root/member `not()` chains:
  `not().not()`, `t.not().not()`, `{}.not().not()`.
- Singleton truthiness for non-Boolean strings and complex JSON:
  `s.not() or f`, `complex.not() and t`.
- Filter predicates and row-resilient multi-item operand behavior:
  `nested.where(flag or gate).count() = 3`,
  `mix[1].where(a implies b).count() = 1`,
  `mix[0].where(a implies b).count() = 1`,
  `true implies arr`, `false and arr`, `true or arr`.

Validation:
- `python3 .temp/qa/fp17_explorer_probe.py`
  - Result: OK, 21 expression cases and 9 validity cases.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_boolean_logic_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py fhir4ds/fhirpath/duckdb/tests/unit/test_filter.py -q`
  - Result: 174 passed.

Issues:
- None. No source remediation required.

Durable notes:
- Updated `fhir4ds/fhirpath/AGENTS.md`.
- Updated `extensions/fhirpath/AGENTS.md`.
