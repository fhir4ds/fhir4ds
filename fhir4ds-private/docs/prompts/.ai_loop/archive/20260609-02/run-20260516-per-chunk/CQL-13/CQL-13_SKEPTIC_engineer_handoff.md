# CQL-13 SKEPTIC Engineer Handoff

## Code Changes

Primary implementation areas:

- `fhir4ds/cql/translator/expressions/_temporal_components.py`
- `fhir4ds/cql/translator/expressions/_temporal_duration.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/translator/expressions/_functions.py`
- `fhir4ds/cql/translator/types.py`
- `fhir4ds/cql/duckdb/udf/datetime.py`
- `extensions/cql/src/cql/datetime.cpp`
- `extensions/cql/src/cql_extension.cpp`

Test areas:

- `fhir4ds/cql/duckdb/tests/integration/test_datetime_part1_parity.py`
- `fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py`
- `fhir4ds/cql/duckdb/tests/integration/test_wasm_translate_execute_gate.py`
- `fhir4ds/cql/tests/unit/test_v2_expressions.py`
- `extensions/cql/test/sql/cql.test`

## Implementation Notes

- `DifferenceBetween` now lowers to `cqlDifferenceBetween`, with Python fallback and native C++ registration.
- Duration/difference helpers return scalar-or-interval `VARCHAR`; every numeric boundary that consumes those helpers must choose explicitly between uncertainty-aware comparison and numeric scalar casting.
- `div` must raise for statically known uncertainty intervals to preserve official invalid conformance, but dynamic/scalar duration math such as CMS0334 must still cast safely.
- `list_sum` and `list_avg` cast list elements through `TRY_CAST(... AS DOUBLE)` at the list aggregate boundary so scalar duration/difference strings can aggregate without binder failures.
- Partial DateTime marker values (`YYYYT`, `YYYY-MMT`, `YYYY-MM-DDT`) are DateTime values and must not be flattened to Date values.

## Current State

All SKEPTIC issues are resolved and verified. No open engineering blockers remain for CQL-13 SKEPTIC.
