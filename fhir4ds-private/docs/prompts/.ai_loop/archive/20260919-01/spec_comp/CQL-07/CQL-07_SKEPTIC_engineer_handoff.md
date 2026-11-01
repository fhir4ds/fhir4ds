# Engineer Handoff — CQL-07 master launch

## Fixed (both VERIFIED, iteration 1)
- QA-001 HIGH (SPEC_VIOLATION, CQL 1.5 Appendix B §ToInteger/§ToLong):
  Decimal inputs to ToInteger/ToLong returned NULL; spec mandates truncation
  toward zero. Root cause: To* branch lists were written for the CQL-06 check
  twins and never grew the Decimal branch; additionally DuckDB
  CAST(decimal AS INTEGER) rounds (1.9→2), so the fix truncates explicitly.
  Fix: macros/conversion.py ToInteger DECIMAL branch
  `TRY_CAST(TRUNC(TRY_CAST(x AS DECIMAL(38,8))) AS INTEGER)` (inner TRY_CAST
  also keeps the macro binder valid for non-decimal parameter types);
  udf/conversion.py ConvertsToInteger/ConvertsToLong now accept Decimal with
  range checks on the truncated integer part, so ToLong(Decimal) converts and
  the CQL-06 twin invariant (ConvertsToT accepts ⇒ ToT converts) holds.
- QA-002 HIGH (SPEC_VIOLATION, CQL-06 .value doctrine on context singleton):
  `Patient.birthDate.value` returned NULL in population SQL while the
  retrieve-alias form worked. Root cause: `_resource_type_for_resource_ref`
  only recognized `<alias>.resource|data`, so the `_pt.patient_resource`
  context singleton never resolved a resource type and `.value` was kept in
  the FHIRPath string. Fix: `_property.py` recognizes `patient_resource`
  final column parts and resolves the type from the declared context type.

## Files changed
- fhir4ds/cql/duckdb/macros/conversion.py (ToInteger DECIMAL truncation branch)
- fhir4ds/cql/duckdb/udf/conversion.py (Decimal acceptance in
  ConvertsToInteger/ConvertsToLong)
- fhir4ds/cql/translator/expressions/_property.py (patient_resource singleton
  resource-type resolution)
- fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py
  (3 new regression tests)

## Validation
- Conversion parity suites: 23/23 pass (dual backend).
- Full conformance gate: ViewDefinition 144/144, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47 — OVERALL 2832/2832 (baseline held).
- Probe rerun (60-case dual-backend matrix): zero parity divergences.

## New issues
None discovered during remediation.
