# QA Handoff - FP-13 HISTORIAN

## Scope
- Chunk: FP-13
- Spec: FHIRPath §6.1 Equality
- Personality: HISTORIAN
- Surfaces tested: native C++ DuckDB extension and forced Python fallback DuckDB UDFs.

## Normative Anchor
FHIRPath normative release §6.1 says `=` propagates empty operands, compares singletons by type-specific equality, and compares multi-item collections item-by-item in order. Date/Time equality must compare precision-by-precision, respect timezone offsets, and treat seconds and milliseconds as one decimal precision. `~` compares equivalent values, treats multi-item collections as order-insensitive, and recursively compares complex child properties using equivalence semantics. String equivalence ignores case and normalizes whitespace. `!=` and `!~` are converses.

## Probes
Created `.temp/qa/` and ran fresh ad hoc parity probes without using prior archives as evidence.

High-value expressions:
- `(@2012 | @2013) = (@2012 | @2014)`
- `(@2012 | @2013) != (@2012 | @2014)`
- `(@2017-11-05T01:30:00.0-04:00 | @2012) = (@2017-11-05T00:30:00.0-05:00 | @2012)`
- `(@2012-01-01T10:30:31.0 | @2012) = (@2012-01-01T10:30:31 | @2012)`
- `objA ~ objB` where child strings differ only by case and whitespace
- `arrA ~ arrB` where complex child objects are order-insensitive and string-equivalent

## Findings
- QA-001 HIGH: Multi-item Date/Time equality is not routed through the singleton temporal equality semantics consistently. Forced Python fallback only considered the first date/time item in some multi-item `=`/`!=` expressions. Native C++ multi-item `=` uses `fpValuesEqual()`, whose Date/Time branch compares string forms and misses timezone-normalized and seconds/milliseconds equality.
- QA-002 HIGH: Native C++ complex equivalence uses raw JSON equality for object/array values instead of recursive FHIRPath equivalence. It fails when child strings are equivalent by §6.1.2 case/whitespace rules, including multi-item unordered complex equivalence.

## Recommended Fix Direction
- Python: move the collection length/order handling in `fhir4ds/fhirpath/engine/invocations/equality.py::equality()` before singleton Date/Time dispatch so multi-item collections compare each pair.
- C++: make `fpValuesEqual()` Date/Time handling reuse the same `compareDateTimes(..., equivalence=false, equality=true)` semantics used by singleton `=`.
- C++: add recursive `fpValuesEquivalent()` semantics for JsonVal object/array values and use it for singleton and multi-item `~`/`!~`.

## Validation Needed
- Add focused parity tests in `fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py`.
- Add native SQL assertions in `extensions/fhirpath/test/sql/fhirpath.test` for C++ extension coverage.
- Rebuild and copy bundled `fhirpath.duckdb_extension` if C++ changes are made.
- Run focused FHIRPath parity/unit tests, native SQL tests, and full conformance before clean exit.
