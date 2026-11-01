# Engineer Handoff: CQL-20 SKEPTIC

Resolved `QA-001` and `QA-002`.

Fixes:

- Added conservative static aggregate element-type validation in the CQL
  translator so invalid Boolean/numeric aggregate list operands raise
  `TranslationError` instead of becoming executable SQL that relies on DuckDB
  casts.
- Registered `geometricmean` in the aggregate pre-translation path and folded
  query-produced rows into scalar DuckDB lists before calling `GeometricMean`.
- Hardened direct numeric/statistical list macros so `Median`, `StdDev`,
  `Variance`, `PopulationStdDev`, `PopulationVariance`, `Product`, and
  `GeometricMean` reject string-list coercion.
- Changed `GeometricMean` macro behavior to handle null/empty/all-null inputs,
  zero values, and negative values without logarithm-domain execution errors.

Validation passed:

- `python3 .temp/qa/cql20_skeptic_probe.py`
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_aggregate_parity.py -q` -> 9/9
- Aggregate + macro/WASM focused pytest -> 23/23
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` -> 2822/2822 overall

Changed implementation/test files:

- `fhir4ds/cql/duckdb/macros/aggregate.py`
- `fhir4ds/cql/duckdb/macros/list.py`
- `fhir4ds/cql/translator/expressions/__init__.py`
- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/duckdb/tests/integration/test_aggregate_parity.py`
- `extensions/cql/AGENTS.md`
- `.temp/qa/cql20_skeptic_probe.py`
