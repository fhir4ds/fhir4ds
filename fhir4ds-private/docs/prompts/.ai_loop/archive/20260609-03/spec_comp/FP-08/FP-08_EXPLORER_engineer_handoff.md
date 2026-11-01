# Engineer Handoff - FP-08 EXPLORER

## Issue Resolved

`QA-001` MEDIUM: forced Python fallback treated an explicitly empty optional
Quantity unit argument as an omitted argument.

## Spec Basis

HL7 FHIRPath Normative Release v2.0.0:

- Section 4.4: a single-input function passed an empty collection as an
  argument returns empty.
- Section 5.5.7: `toQuantity([unit : String])` and
  `convertsToQuantity([unit : String])` take at most one optional singleton
  String unit argument.

## Root Cause

`make_param()` returns `[]` for an empty argument expression such as `{}`.
`misc.to_quantity()` and `misc.converts_to_quantity()` used truthiness checks
for `to_unit`, so `[]` was treated the same as omitted `None`.

## Fix

In `fhir4ds/fhirpath/engine/invocations/misc.py`:

- `to_quantity(..., to_unit=[])` now returns empty immediately.
- `converts_to_quantity(..., to_unit=[])` now returns empty immediately.
- Omitted `to_unit=None` remains unchanged.

Added focused regression coverage in
`fhir4ds/fhirpath/duckdb/tests/integration/test_fp08_empty_quantity_unit_parity.py`
for native C++ and forced Python fallback parity on:

- `1.toQuantity({})`
- `1.convertsToQuantity({})`

## Validation

- QA probe after fix: 35 cases, 0 native/fallback mismatches, 0 expectation failures.
- Focused pytest: 19 passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.

No native C++ source changed; no extension rebuild was required.
