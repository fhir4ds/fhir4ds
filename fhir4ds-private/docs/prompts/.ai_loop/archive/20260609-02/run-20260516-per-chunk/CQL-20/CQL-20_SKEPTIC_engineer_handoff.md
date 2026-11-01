# Engineer Handoff - CQL-20 SKEPTIC Aggregate Functions

## Issues Remediated

### QA-001 - Direct Boolean Aggregate Macros

Root cause: `AllTrue` and `AnyTrue` were SQL macros over DuckDB row aggregates (`bool_and`/`bool_or`), so list arguments bound as `BOOLEAN[]` and failed.

Fix:
- Updated `fhir4ds/cql/duckdb/macros/aggregate.py` so `AllTrue`, `AnyTrue`, `AllFalse`, and `AnyFalse` operate on list arguments, filter null elements, and preserve CQL defaults for null/empty lists.
- Preserved row-aggregate compatibility for statistical names (`Median`, `Mode`, `StdDev`, `Variance`, population aliases) because macro-shadowing those names as list functions breaks existing DuckDB SQL aggregate usage. CQL list statistical behavior remains handled by the translator and `statistical*` helpers.

### QA-002 - Python/C++ statisticalMode Tie Parity

Root cause: Python fallback `statisticalMode` returned the first tied value while native/no-Python C++ returned SQL NULL for tied modes.

Fix:
- Updated `fhir4ds/cql/duckdb/udf/aggregate.py` to return NULL when multiple non-null values share the highest frequency.

### QA-003 - Quantity Aggregate Unit Semantics

Root cause: translated Quantity aggregates extracted raw `$.value` fields and reused the first unit, so compatible mixed-unit lists were aggregated as plain numbers.

Fix:
- Added unit-aware Quantity aggregate lowering in `fhir4ds/cql/translator/expressions/_functions.py`.
- `Sum` and `Avg` now reduce through `quantityAdd` / `quantityDivide`.
- `Min` and `Max` now reduce through `quantityCompare`.
- `Median`, `Mode`, `Product`, `StdDev`, `Variance`, `PopulationStdDev`, and `PopulationVariance` convert elements to a common compatible unit before list aggregation and return Quantity JSON.
- Added CQL-20 parity/regression coverage in `fhir4ds/cql/duckdb/tests/integration/test_aggregate_parity.py`.

### ARCH-001 - Named Quantity List Aggregate Bypass

Root cause: the quantity-aware aggregate path only recognized inline `SQLArray` expressions. A named definition such as `define Qs: {1 'g', 1000 'mg'}` translated through the scalar definition lookup path before aggregate lowering, producing a one-row CTE lookup and numeric `SUM(TRY_CAST(...))` rather than CQL list aggregation.

Fix:
- Updated aggregate pre-translation so identifiers with `List<Quantity>` metadata inline their definition AST for aggregate lowering when possible.
- Added named-list regressions for `Sum(Qs)` and `Avg(Qs)` to the aggregate parity probe and pytest coverage.

## Institutional Memory

Updated `extensions/cql/AGENTS.md` with a CQL Aggregate Functions fragile-area note covering list aggregate public boundaries, statisticalMode parity, and Quantity aggregate unit preservation.

## Validation

- `python3 .temp/qa/cql20_skeptic_probe.py` -> passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_aggregate_parity.py -q --tb=short` -> 4 passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_aggregate_parity.py fhir4ds/cql/duckdb/tests/test_macros_tier1.py fhir4ds/cql/tests/unit/test_v2_expressions.py -q --tb=short` -> 217 passed.
- `./build/release/test/unittest '*cql*'` from `extensions/cql` -> 768 assertions passed.
- `python3 conformance/scripts/run_all.py` -> 2822/2822, 100%.
- `python3 -m pytest -q --tb=short` -> 7219 passed, 5 skipped, 9 warnings.

## Changed Paths

- `fhir4ds/cql/duckdb/macros/aggregate.py`
- `fhir4ds/cql/duckdb/udf/aggregate.py`
- `fhir4ds/cql/translator/expressions/__init__.py`
- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/duckdb/tests/integration/test_aggregate_parity.py`
- `extensions/cql/AGENTS.md`
- `.temp/qa/cql20_skeptic_probe.py`
