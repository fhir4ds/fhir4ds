# Engineer Handoff: CQL-15 SKEPTIC

All three QA issues were remediated surgically.

Changes:
- Parser `per` values now accept UCUM string units after numeric values, enabling Quantity `expand ... per 1 'g'`.
- Python interval helpers preserve Quantity JSON for semantic `start`/`end`, `except`, and `expand`, and no longer coerce Quantity intervals against bare scalar points.
- Native C++ interval helpers now preserve Quantity shape during `expand`, use compatible-unit conversion, and serialize Quantity predecessor/predecessor boundaries without rounding away `1e-8` steps.
- The CQL translator now rehydrates FHIR `valueQuantity.value` numeric projections to sibling `valueQuantity` JSON when the peer is an `Interval<Quantity>`, preserving helper strictness while restoring CMS22.
- Added CQL-15 regression coverage in `test_interval_part1_parity.py`.

Validation:
- `PYTHONPATH=. python3 .temp/qa/cql15_skeptic_probe.py` passed.
- `PYTHONPATH=. python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_interval_part1_parity.py -q --tb=short` passed 12/12.
- Interval part 1/2/3 plus WASM/C++ surface passed 25/25.
- Official CQL interval category passed 412/412.
- CMS22 DQM rerun passed 43/43 after the translator shape fix.
- Full conformance passed 2822/2822: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47.
