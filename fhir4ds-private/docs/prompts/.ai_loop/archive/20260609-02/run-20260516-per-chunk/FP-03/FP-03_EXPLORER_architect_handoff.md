## Architect Handoff: FP-03 EXPLORER

Structural audit result: CLEAN. The remediation keeps the intended boundary intact: strict FHIRPath criteria and Boolean aggregate validation live in the Python/native core evaluators, while DuckDB public UDF resilience remains at the adapter boundary by converting typed spec errors to empty/NULL outside strict mode. Native and forced Python fallback parity is now explicitly covered for invalid criteria and invalid trailing aggregate values.

Issue counts:
- SPEC_VIOLATION: 2 found, 2 verified.
- New architecture findings: 0.
- QA retry required: no.

Golden standard written to `.temp/architect/golden_standard.md`. The most important invariant confirmed is that filter-style criteria (`where`, `exists(criteria)`, `all(criteria)`) must not reuse permissive singleton truthiness intended for Boolean operators or non-strict `iif` wrapper behavior.

Recommended fix order: no further engineer phase needed for FP-03. Keep future existence changes covered by native plus forced-fallback parity tests and rebuild/copy the bundled extension after every C++ evaluator change.
