# Engineer Handoff: CQL-18 SKEPTIC

## Issues Resolved

### QA-001: Transported Clinical List Equivalence

Status: VERIFIED

Root cause:

`CQLListElementEquivalent` only handled Quantity, String, and raw equality.
Transported `List<Code>` / `List<Concept>` values, including values produced by
`singleton from { { ... } }`, could therefore compare Code JSON by display and
version rather than CQL clinical equivalence. The translator also failed to
recognize `singleton from` over a nested list as list-typed, so translated `~`
fell through to raw SQL `=`.

Fix:

Added pure-SQL clinical shape/equivalence helpers in
`fhir4ds/cql/duckdb/macros/list.py` and routed
`CQLListElementEquivalent` through them before raw equality. Extended list-type
detection in `_is_list_typed_ast` for `SingletonExpression` and parsed unary
`singleton from` over nested list values.

### QA-002: Quantity List Equality Misclassified As Scalar Quantity

Status: VERIFIED

Root cause:

`_is_cql_quantity_expr` classified a `ListExpression` containing Quantity
elements as a Quantity expression. That made `{ 1 'g' } = { 1000 'mg' }` lower
to scalar `quantity_compare(parse_quantity(CAST([quantity] AS VARCHAR)), ...)`
instead of list equality.

Fix:

Kept `singleton from { 1 'g' }` classified as Quantity, but stopped classifying
the list expression itself as Quantity. Quantity list equality now routes
through `CQLListEqualEq`, whose element helper performs unit-aware Quantity
comparison.

## Validation

- Fresh probe: `.temp/qa/cql18_skeptic_probe.py`
- List Part 1 parity: 7/7
- List Part 1 + Part 2 parity: 13/13
- Official list parser category: 212/212
- CQL conformance: 1706/1706
- Full conformance: 2822/2822

## Changed Files

- `fhir4ds/cql/duckdb/macros/list.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/translator/expressions/_temporal_intervals.py`
- `fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py`
- `.temp/qa/cql18_skeptic_probe.py`
