# Engineer Handoff — CQL-08 HISTORIAN remediation (iteration 1, 2026-08-20)

## QA-001 MEDIUM — ToInteger/ToLong accept Decimal via truncation → RESOLVED
- Root cause: the CQL-07 SKEPTIC master launch added a DECIMAL truncation
  branch to the `ToInteger` macro and Decimal acceptance to
  `ConvertsToInteger`/`ConvertsToLong` based on the claim "spec mandates
  truncation". Verified live against cql.hl7.org Appendix B (three targeted
  fetches, incl. verbatim Table 9-E Decimal row): there is NO Decimal→Integer
  or Decimal→Long conversion, and `ToInteger` overloads are Boolean/String/
  Long only. Truncation is the separate `Truncate` operator. No official
  fixture pins truncation (only `ToInteger('-25')` → -25).
- Fix (spec: CQL 1.5 Appendix B Table 9-E + §ToInteger/§ToLong):
  - `fhir4ds/cql/duckdb/macros/conversion.py`: removed the DECIMAL truncation
    branch from `ToInteger` (Decimal now falls to ELSE NULL).
  - `fhir4ds/cql/duckdb/udf/conversion.py`: `ConvertsToInteger`/
    `ConvertsToLong` return False for Decimal; Integer/Long inputs keep the
    range-checked Long→Integer/Long conversions; `ToLong` inherits via
    `ConvertsToLong`.
  - Native path unaffected structurally: the C++ extension registers none of
    these names; the macro/UDF surface serves both cpp and python
  connections (verified py==cpp after fix).
- Tests: updated the two CQL-07 truncation pins in
  `test_conversion_function_parity.py` to the verified spec behavior
  (null/false, plus spec-defined overloads retained); added
  `test_cql_to_integer_long_reject_decimal_cql08_historian` covering
  ToInteger/ToLong/CanConvert/convert forms on both backends.

## QA-002 MEDIUM — nested Coalesce escapes static type guard → RESOLVED
- Root cause: `_infer_static_cql_type_for_logical_operand` returned "Any" for
  `FunctionRef` coalesce, so `Coalesce(1, Coalesce(null,'a'))` bypassed the
  SKEPTIC String/numeric family guard and leaked a raw DuckDB Binder Error
  at execution.
- Fix (spec: CQL 1.5 §Coalesce — return type is the common type of the
  arguments): the FunctionRef branch now infers Coalesce's static type from
  its first non-Any argument (`fhir4ds/cql/translator/expressions/
  _operators.py`), propagating through nesting. Nested String/numeric mixes
  now raise the same typed TranslationError as the flat form; homogeneous
  and dynamic cases unchanged (verified both orders, both backends).
- Test: `test_cql_coalesce_nested_static_type_guard_cql08_historian`
  (3 rejected forms raise TranslationError; 4 accepted forms execute py==cpp).

## QA-003 LOW — stale QuantityToString pin → RESOLVED (test-only)
- `test_structural_type_parity.py` pinned `"38 'weeks'"` from before the
  CQL-06 calendar-duration-keyword fix; both engines correctly produce
  `"38 weeks"` (calendar keyword bare, UCUM `'cm'` still quoted). Pin
  updated with a doctrine comment; suite 22/22.

## QA-004 LOW INTENDED — no code change.

## Files changed
- fhir4ds/cql/duckdb/macros/conversion.py
- fhir4ds/cql/duckdb/udf/conversion.py
- fhir4ds/cql/translator/expressions/_operators.py
- fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py
- fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py
- fhir4ds/cql/duckdb/tests/integration/test_nullological_parity.py (+2 tests)

## Validation
- Focused: nullological parity 15/15; conversion function parity 18 passed
  (incl. the 2 updated tests); structural parity 22/22; CQL-01 CanConvert +
  primitive-boundary tests pass (the 3 pre-existing failures are closed).
- Fresh full conformance: OVERALL 2832/2832 (ViewDef 144, FHIRPath 935,
  CQL 1706, DQM 47) — baseline held.
- Full `fhir4ds/cql` pytest: **5733 passed, 9 skipped, 0 failures** (log
  `.temp/qa/cql08_historian_2026_08_20/cql_pytest.log`; the 3 pre-existing
  working-tree failures are gone).
