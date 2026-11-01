# Engineer Handoff: CQL-06 HISTORIAN

Resolved `QA-001`.

Changes:

- Added representable CQL Decimal validation at public Quantity/Ratio
  conversion boundaries in `fhir4ds/cql/duckdb/udf/quantity.py` and
  `fhir4ds/cql/duckdb/udf/conversion.py`.
- `ToQuantity` now rejects Quantity strings whose value has scale beyond 8 or
  integer range beyond the implementation `DECIMAL(38, 8)` boundary.
- `ConvertQuantity` now validates JSON-shaped Quantity input before delegating
  to the generic quantity conversion helper.
- `ConvertsToQuantity` now returns true for valid Ratio JSON because
  `ToQuantity(Ratio)` is supported.
- Native C++ `ToQuantity(VARCHAR)` now enforces the same string decimal
  representability check; the bundled `cql.duckdb_extension` was rebuilt.
- The generic `parse_quantity` path was intentionally kept permissive for
  internally generated arithmetic intermediates. An initial over-broad guard
  caused CMS832 DQM accuracy to drop to 76.5%; narrowing the guard restored
  CMS832 to 34/34 and full DQM to 47/47.

Validation:

- `python3 .temp/qa/cql06_historian_probe.py` passed.
- Focused pytest for conversion/core/temporal surfaces: 16 passed.
- Native CQL sqllogictest: 788 assertions passed.
- Targeted DQM CMS832 rerun: 100.0% accuracy, 34/34.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.
