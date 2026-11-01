# Engineer Handoff — CQL-09 Comparison Operators (HISTORIAN, iteration 1)

## QA-001 (MEDIUM) — RESOLVED
`{{1, null}, {2}} = {{1, 2}, {2}}` returned false; CQL 1.5 §9.4 Equal requires
null (nested-list elements recurse into list equality; an uncertain inner
element propagates).

Fix: `fhir4ds/cql/duckdb/macros/list.py` — new `CQLNestedListEqElem` /
`CQLNestedListEqTemporal` macros plus subquery-free JSON leaf comparators
`CQLJsonEqElem` / `CQLJsonEqTemporal`. The element CASE inside
`CQLListEqualEq` / `CQLListEqualTemporalEq` now routes LIST-typed elements
(duckdb `ends_with(typeof(x), '[]')`) to the nested macros instead of letting
`CQLListElementEqual`'s generic `left = right` fallback collapse uncertainty.
The nested macros normalize both sides through `TRY_CAST(x AS JSON[])`
(type-agnostic — returns NULL for scalars, enabling a single body that binds
for every element type), enumerate positions with `range(1, len+1)`, and
aggregate 3VL markers via `list_contains(..., FALSE)` / `list_count` vs
length.

DuckDB constraints that shaped this (documented in AGENTS.md): macros cannot
recurse (syntactic bind-time expansion → depth-limit errors); correlated
UNNEST is unsupported; subqueries inside lambda expressions are unsupported
(this forced the leaf comparators to be pure CASE — numerics via
DECIMAL(38,8) so `1.0` vs `1` is TRUE across json_type DOUBLE/UBIGINT;
strings exact; temporals via `cqlDateTimeEqual` precision-walk).
Documented boundary: embedded clinical/quantity/interval JSON objects at
depth ≥ 2 and lists nested deeper than 2 levels compare
uncertainty-preserving (equal-shape → TRUE else NULL) — never definitely
wrong, but may say null where the spec could prove false. Depth-1 clinical /
quantity / interval / tuple list elements remain exact (unchanged paths).

## QA-002 (MEDIUM) — RESOLVED
`{ Tuple { a: 1, b: null } } = { Tuple { a: 1, b: 2 } }` returned false; spec
null (tuple elements compare field-wise with `=`; one-sided null field is
uncertain).

Fix: new `CQLTupleValueEqual` macro — `json_keys` set equality, then
`json_each` field-wise 3VL (null-null → TRUE, one-sided JSON null → NULL,
numerics via DECIMAL(38,8) after the both-numeric guard, nested objects
conservative, key-set mismatch → FALSE). `CQLListElementEqual` gained a
JSON-OBJECT branch routed to it, placed after the clinical/interval/quantity
branches so Code/Concept/Interval/Quantity doctrines are untouched.

## QA-003 (LOW) — INTENDED (terminal, no fix)
`Code { code: null, ... } =` same → true. §9.4 Equal does not define Code
equality; consistent with pinned CQL-02 absent==explicit-null doctrine.
Recorded in AGENTS.md NOT-A-BUG doctrine.

## Implementation notes
- SQL-macro-only fix: shared by forced-Python and native registrations — no
  extension rebuild required (verified both paths).
- Single-writer discipline: only `macros/list.py`, the new parity test, and
  `AGENTS.md` were modified.
- First cut used inline correlated-unnest subqueries (DuckDB binder rejects)
  and a second cut used lambda-delegated leaf macros (subqueries-in-lambda
  rejection); final design is the JSON[]-normalized marker approach above.

## Regression coverage
New test `test_cql_null_uncertainty_preserved_in_composite_list_elements`
in `fhir4ds/cql/duckdb/tests/integration/test_comparison_operator_parity.py`
(13 cases × py+cpp: nested-list uncertainty/known-equal/unequal/length-
mismatch/trailing-zeros/!= propagation/temporal precision, tuple-in-list
uncertainty/known/numeric/missing-field).

## Validation
- Comparison parity suite: 14/14 passed (incl. SKEPTIC regression test).
- List suites: test_list_part1_parity + test_list_part2_parity +
  test_list_udfs — 76/76 passed.
- SKEPTIC probe re-run: only the SKEPTIC's own documented false-positive
  expectations differ; zero new regressions.
- Full conformance gate: ViewDefinition 144/144, FHIRPath 935/935, CQL
  1706/1706, DQM 47/47, OVERALL 2832/2832 — baseline held.
