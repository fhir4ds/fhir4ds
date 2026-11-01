# Engineer Handoff - FP-05 SKEPTIC

## Issue Resolved

`QA-001` (`HIGH`, `SPEC_VIOLATION`) is resolved.

## Root Cause

Native `Evaluator::evalFunction` did not enforce exact child counts for the
FHIRPath section 5.3/5.4 subsetting and combining function signatures. As a
result, no-argument functions such as `first()` and `tail()` ignored unexpected
arguments, and one-argument functions such as `skip(num)`, `take(num)`,
`union(other)`, and `combine(other)` ignored extra arguments. `fn_skip` and
`fn_take` also returned early when the input collection was empty before
checking whether `num` was a singleton Integer, so `fhirpath_is_valid()` could
accept invalid count arguments on its sparse validation Patient.

## Fix

Changed `extensions/fhirpath/src/fhirpath/evaluator.cpp` to:

- Reject arguments for `single()`, `first()`, `last()`, and `tail()`.
- Require exactly one argument for `skip()`, `take()`, `combine()`,
  `intersect()`, `exclude()`, and `union()`.
- Validate `skip()`/`take()` count cardinality and Integer type before
  empty-input short-circuiting.

Added regression coverage in:

- `fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py`
- `extensions/fhirpath/test/sql/fhirpath.test`

Rebuilt and copied the bundled extension to:

- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`

## Validation

- QA probe: `.temp/qa/fp05_skeptic_probe.py` -> 46 cases, 0 mismatches.
- Focused pytest: `test_collection_operator_parity.py` -> 8 passed.
- Native FHIRPath unittest: 366 assertions passed.
- Extension artifact SHA-256 matches build output and bundled package copy.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.

## New Issues

None.
