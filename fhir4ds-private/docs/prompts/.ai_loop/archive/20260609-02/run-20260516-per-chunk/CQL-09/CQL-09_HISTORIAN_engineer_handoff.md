# Engineer Handoff - CQL-09 HISTORIAN

## Remediation Summary

Resolved all three QA findings for CQL comparison operators.

- Public Date/DateTime comparison helpers now keep strict precision uncertainty. `_compare_at_min_precision()` defaults to no Date-to-DateTime promotion, fixing the official `DateTimeBetweenIsNull` behavior.
- Interval boundary comparisons now explicitly pass `promote_date_to_datetime=True` when they need full-day endpoint normalization, preserving CMS2/DQM interval-window behavior.
- Decimal literal equivalence now uses least-precise-operand rounding for static numeric/decimal literals, without relying on DuckDB's overloaded `round(x, p)` name.
- Quantity equivalence now calls `quantityCompare(..., '~')`; Python fallback and native C++ duration logic now return NULL for calendar-vs-definite equality/ordering and true for CQL duration equivalence cases such as `1 year ~ 365 days`.

## Files Changed

- `fhir4ds/cql/duckdb/udf/datetime.py`
- `fhir4ds/cql/duckdb/udf/interval.py`
- `fhir4ds/cql/duckdb/udf/quantity.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/duckdb/tests/integration/test_comparison_operator_parity.py`
- `fhir4ds/cql/duckdb/tests/integration/test_interval_part1_parity.py`
- `extensions/cql/src/cql/quantity.cpp`
- `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`

## Verification

- Focused comparison/interval pytest: 5 passed.
- Official comparison operator pytest: 198 passed.
- CQL native extension unittest: 628 assertions passed.
- CMS2 DQM forced Python fallback: 36/36.
- CMS2 DQM native-loaded: 36/36.
- Full conformance: 2822/2822.
- Full `fhir4ds/` pytest: 7162 passed, 5 skipped, 9 warnings.

## Notes

The first temporal fix caused CMS2 to drop to 29/36 because it changed a shared helper globally. The durable boundary is now explicit: public comparison helpers are strict; interval helper internals opt into endpoint promotion. Keep that split when changing temporal comparison code.

