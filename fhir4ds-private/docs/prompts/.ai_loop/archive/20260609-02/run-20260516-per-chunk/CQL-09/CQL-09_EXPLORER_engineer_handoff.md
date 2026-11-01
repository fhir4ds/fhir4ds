# Engineer Handoff - CQL-09 EXPLORER

Resolved all QA findings.

Changes made:
- Dynamic FHIR comparison lowering now uses `fhirpath_number` for numeric evidence and a Quantity-aware `parse_quantity`/`quantity_compare` path for JSON Quantity choices before falling back to primitive numeric comparisons.
- Python and native C++ `quantityCompare` now apply least-precision decimal equivalence for non-duration quantities and keep duration equality/equivalence semantics distinct.
- `parseQuantity()` no longer exposes internal `_precision` metadata in public JSON output.
- Retrieve/precomputed-column optimization now preserves `fhirpath_number` when a registered precomputed column is not numeric and casts optimizer-created scalar subqueries before numeric literal comparisons.
- `fhirpath_number` projection is now limited to FHIR `value`/`value.*` paths so internal CQL tuple JSON numeric properties continue through safe numeric casts.
- Regression tests were added for dynamic FHIR comparison edges, Quantity equivalence, scalar-subquery precomputed-column numeric guards, and internal tuple numeric text comparisons.

Verification:
- `cmake --build build/release --config Release -j 8`
- `./build/release/test/unittest '*cql*'` -> 628 assertions passed
- `PYTHONPATH=/mnt/d/fhir4ds python3 .temp/qa/cql09_explorer_probe.py` -> all probe cases passed on native and forced Python fallback
- Focused pytest set -> 141 passed
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_comparison_operator_parity.py -q` -> 6 passed
- `python3 -m fhir4ds.dqm.tests.conformance --measure CMS871 --verbose` -> 10/10, 100%
- Full pytest -> 7166 passed, 5 skipped, 9 warnings
- Full conformance -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822
