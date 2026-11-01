# Engineer Handoff - CQL-04 EXPLORER

Resolved `QA-001` as a HIGH spec violation.

Root cause: `_infer_static_cql_type_for_logical_operand()` classified only a
small set of Boolean-returning functions and otherwise returned `Any` for
`FunctionRef`. It also unwrapped `as Any` but not `convert ... to Any`.
Consequently, non-Boolean conversion/function outputs could pass logical
validation and lower to raw SQL Boolean operators.

Fix:
- Added known CQL conversion/function return-type inference for logical
  validation in `fhir4ds/cql/translator/expressions/_operators.py`.
- Added `convert ... to Any` unwrapping so the source expression's concrete
  type remains visible to logical validation.
- Added regression cases to
  `fhir4ds/cql/duckdb/tests/integration/test_logical_parity.py`.
- Added `.temp/qa/cql04_explorer_probe.py` for fresh native/fallback/no-Python
  parity probing.
- Updated root `AGENTS.md` with the new logical validation invariant.

Verification:
- `.temp/qa/cql04_explorer_probe.py`: passed.
- `test_logical_parity.py`: 28 passed.
- `test_logical_parity.py` plus `test_primitive_parity.py`: 39 passed.
- Full conformance: 2822/2822.

No additional issues were discovered during remediation.
