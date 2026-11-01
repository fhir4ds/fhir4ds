# Engineer Handoff — CQL-17 EXPLORER

Status: FIXED

Resolved issues:
- `QA-001`: Python/native-loaded `intervalUnion` no longer widens finite open boundaries. It now serializes effective Start/End boundaries, and C++ `Interval::union_of` uses the same canonical effective-bound output.
- `QA-002`: Decimal interval part-3 helpers now preserve CQL scale-8 successor/predecessor behavior across Python fallback and no-Python C++. `intervalStart`, `intervalEnd`, `pointFrom`, `intervalWidth`, and `interval_size` were aligned.
- `QA-003`: Translated `point in (interval union interval)` now routes interval-valued set-operation results through `intervalContains` instead of SQL `IN`.
- `QA-004`: No-Python C++ Quantity interval width/size now converts compatible high-bound units into the low-bound unit before subtraction.

Files changed:
- `fhir4ds/cql/duckdb/udf/interval.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/duckdb/tests/integration/test_interval_part3_parity.py`
- `extensions/cql/src/cql/interval.cpp`
- `extensions/cql/src/cql/interval.hpp`
- `extensions/cql/src/cql_extension.cpp`
- `extensions/cql/test/sql/cql.test`
- `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`
- `.temp/qa/cql17_explorer_probe.py`

Validation run:
- `python3 .temp/qa/cql17_explorer_probe.py` -> passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_interval_part3_parity.py -q --tb=short` -> 3 passed.
- `extensions/cql/build/release/test/unittest "*cql*"` -> 768 assertions passed.
- Native and bundled CQL extension SHA-256 matched: `785d6566fff2d4eceb00afd137ef9e91e52bd1c7a68b29f2e03cea7e17cdfac0`.

Architect focus:
- Confirm no regression in the broader interval cluster and official conformance.
- Confirm decimal interval output changes do not break public CQL DuckDB expectations.
