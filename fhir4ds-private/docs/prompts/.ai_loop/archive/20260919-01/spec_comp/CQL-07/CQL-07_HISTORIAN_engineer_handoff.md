# Engineer Handoff — CQL-07 HISTORIAN launch

## Fixed (RESOLVED, iteration 1)
- QA-001 HIGH (SPEC_VIOLATION, CQL 1.5 Appendix B §ToQuantity Table 9-E):
  ToQuantity(Quantity) returned NULL instead of the identity conversion;
  violated the CQL-06 twin invariant (ConvertsToQuantity accepted the same
  JSON). Root cause: udf/quantity.py toQuantity() routed every '{'-prefixed
  string exclusively to _quantity_from_ratio_json, which requires
  numerator/denominator shape. Fix: after the Ratio attempt, a new
  _quantity_identity_from_json() validates the Quantity shape
  (is_valid_quantity_object) and re-emits the canonical form; invalid shapes
  still return null (no silent fallback). Native lockstep: cql::to_quantity
  (extensions/cql/src/cql/quantity.cpp) gained the same JSON identity branch
  via parse_quantity_json/format_quantity_json with unit validation.

## Files changed
- fhir4ds/cql/duckdb/udf/quantity.py (toQuantity dispatch + identity helper)
- extensions/cql/src/cql/quantity.cpp (native identity branch)
- fhir4ds/cql/duckdb/extensions/cql.duckdb_extension (rebuilt + deployed,
  md5 d7a80566c7d2a4890ec94816ddd816c7, matched across repo bundle and
  ~/.local site-packages; verified via direct LOAD and package register path;
  no ~/.duckdb cache copy existed)
- fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py
  (+2 regression tests: macro/e2e identity, twin invariant, invalid shapes)

## Validation
- Reproducer passes on both backends (python-only and cpp-registered).
- Focused suites after deploy: 112/112
  (conversion function parity 14, conversion check parity, quantity, ratio).
- Full conformance gate fresh run: ViewDefinition 144/144, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47 — OVERALL 2832/2832 (baseline held).

## New issues
None discovered during remediation.
