# Engineer Handoff — CQL-08 SKEPTIC remediation (iteration 1, 2026-08-20)

## QA-001 HIGH — Coalesce scalar arity capped at 5 → RESOLVED
- Root cause: `_translate_coalesce` (fhir4ds/cql/translator/expressions/
  `_functions.py`) and the public UDF `Coalesce` (fhir4ds/cql/duckdb/udf/
  `logical.py`) both raised for >5 scalar args. Spec (CQL 1.5 Developer's
  Guide §Coalesce) is variadic with no upper bound ("first non-null
  expression among two or more").
- Fix: reject only `<2` scalar args (single-arg remains the List<T>
  overload). No native change needed — the public `Coalesce` name is
  served by the Python UDF on both cpp and python paths.
- Re-verified: probe1_after.out — `Coalesce(null,null,1,2,3,4,5,6)` → 1 on
  both paths; population pipeline (probe2) unaffected.

## QA-002 MEDIUM — order-dependent type mixing → RESOLVED
- Root cause: mixed String/numeric operands were passed straight to DuckDB
  `COALESCE`, whose binder accepts or rejects the mix depending on argument
  order. Spec: arguments must be implicitly castable to a common type.
- Fix: AST-level static type-family check before translation — String-family
  mixed with Integer/Long/Decimal raises a typed TranslationError in both
  orders. Dynamic/unknown-typed operands pass through untouched (no silent
  fallback, no behavior change for FHIR-backed Coalesce).

## QA-003 / QA-004 LOW INTENDED — no code change (AGENTS.md registry updated).

## Files changed
- fhir4ds/cql/translator/expressions/_functions.py (arity + type-mix guard)
- fhir4ds/cql/duckdb/udf/logical.py (UDF arity)
- fhir4ds/cql/duckdb/tests/integration/test_nullological_parity.py
  (updated 2 stale arity pins; added mixed-order rejection cases; added
  variadic regression test `test_cql_coalesce_variadic_over_fhir_boolean_defaults_cql08`)

## Validation
- Focused nullological parity: 13/13 passed.
- Full conformance (fresh run): ViewDefinition 144/144, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47 — OVERALL 2832/2832. Baseline held.
- Full fhir4ds/cql pytest: running (log .temp/qa/cql08_skeptic_2026_08_20/cql_pytest.log).

## Out-of-scope observation (not CQL-08)
Two PRE-EXISTING failures in the shared working tree, reproduced with the CQL-08 edits
removed (git-checkout of the two touched source files), so not caused by this launch:
- test_structural_type_parity.py::test_cql_structural_quantity_assertion_preserves_fhir_quantity_comparison
  (cpp "38 'weeks'" vs py "38 weeks" — CQL-06 QuantityToString territory)
- test_cql01_primitive_types.py::TestCanConvert::test_can_convert_false
  (CanConvert(1.5, Integer) returns True — CQL-01 territory)
Left for the owning chunk's next personality launch; conformance suite unaffected (2832/2832).
