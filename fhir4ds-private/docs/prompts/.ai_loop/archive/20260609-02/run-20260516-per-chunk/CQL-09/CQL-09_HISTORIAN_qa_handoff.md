# QA Handoff - CQL-09 HISTORIAN

## Scope

Audited CQL comparison operators for the active CQL-09 chunk: `between`, `=`, `~`, `>`, `>=`, `<`, `<=`, `!=`, and `!~`. Per instruction, this run did not inspect archived `.ai_loop/spec_comp/**` artifacts.

## Spec Sources

- CQL 1.5.3 Appendix B Comparison Operators, official reference: `https://cql.hl7.org/09-b-cqlreference.html`
- Current official XML fixture: `fhir4ds/cql/tests/official/cql-tests/tests/cql/CqlComparisonOperatorsTest.xml`

## Fresh Probes

Used `.temp/qa` workspace and direct Python snippets against current source. Compared native-loaded DuckDB registration with forced Python fallback registration using:

- `translate_cql(...)` scalar definitions
- direct public `quantityCompare`/comparison helper paths through generated SQL
- existing focused parity test file inspection: `fhir4ds/cql/duckdb/tests/integration/test_comparison_operator_parity.py`

## Findings

1. `QA-CQL09-HISTORIAN-001` - HIGH
   `@2012-01-01 between @2012-01-01T12 and @2012-01-02T12` should be null per the official CQL `DateTimeBetweenIsNull` example. Native C++ returns null, forced Python fallback returns false because `_compare_at_min_precision` promotes a Date to midnight DateTime before declaring uncertainty.

2. `QA-CQL09-HISTORIAN-002` - MEDIUM
   Decimal equivalence lowers to plain SQL equality. `3.54 ~ 3.5` returns false, but CQL decimal equivalence compares rounded values at the least precise operand precision, so this case should be true.

3. `QA-CQL09-HISTORIAN-003` - HIGH
   Duration quantity comparison/equivalence does not distinguish CQL calendar durations from definite durations. `1 year = 365 days` returns false instead of null, and `1 year ~ 365 days` returns false instead of true.

## Suggested Remediation

- Remove Date-to-midnight promotion from the forced Python fallback min-precision comparison path.
- Add static decimal-literal equivalence lowering using `raw_str` precision.
- Add duration-unit semantics to Python and native C++ `quantityCompare`, using a distinct equivalence operator path for `~`/`!~` so equality/comparison nullability remains spec-correct.

## Final Status

All three findings were remediated and verified. The temporal fix was narrowed after a CMS2 regression: public CQL comparison helpers remain strict, while interval boundary helpers explicitly opt into Date-to-DateTime endpoint promotion for DQM day-window behavior.
