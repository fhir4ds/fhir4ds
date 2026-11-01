# CQL-08 HISTORIAN Engineer Handoff

## Fixes Implemented
- Tightened `IsTrue` and `IsFalse` macros so typed Boolean NULL returns false and non-Boolean inputs remain false.
- Preserved day-precision DateTime identity by emitting `YYYY-MM-DDT` from three-component `DateTime(...)` constructor lowering.
- Made public `Coalesce` return Python `datetime` values as ISO strings in the fallback path.
- Added `YYYY-MM-DDT` parser support in Python and native C++ date/time helper paths.
- Made Python and native C++ predecessor/successor and interval operations raw-precision aware for day-precision DateTime values.
- Removed the midnight heuristic for full timestamp open bounds and preserved explicit day-precision DateTime markers through date add/subtract helpers.

## Primary Files Touched
- `fhir4ds/cql/duckdb/macros/logical.py`
- `fhir4ds/cql/duckdb/udf/logical.py`
- `fhir4ds/cql/duckdb/udf/datetime.py`
- `fhir4ds/cql/duckdb/udf/math.py`
- `fhir4ds/cql/duckdb/udf/interval.py`
- `fhir4ds/cql/translator/expressions/_temporal_components.py`
- `extensions/cql/src/cql/datetime.cpp`
- `extensions/cql/src/cql/boundary.cpp`
- `extensions/cql/src/cql/interval.cpp`
- `extensions/cql/src/cql_extension.cpp`
- `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`

## Tests Added or Extended
- `fhir4ds/cql/duckdb/tests/integration/test_nullological_parity.py`
- `fhir4ds/cql/duckdb/tests/integration/test_arithmetic_part2_parity.py`
- `fhir4ds/cql/duckdb/tests/integration/test_interval_part1_parity.py`
- `fhir4ds/cql/duckdb/tests/integration/test_interval_part2_parity.py`
- `fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py`

## Build Notes
- Rebuilt the native CQL extension with `cmake --build build/release --config Release -j 8` in `extensions/cql`.
- Copied the rebuilt `cql.duckdb_extension` into `fhir4ds/cql/duckdb/extensions/`.
- Verified source and bundled extension SHA-256 matched: `a90c8f944faebb6144913614d0db26cc648ad2ae050a67ec0f0ceef46984b147`.

## Residual Risk
No open issue remains for this chunk/personality. The highest-risk behavior is temporal precision encoding around `YYYY-MM-DDT`; it now has focused Python fallback, native-loaded, native C++ SQL, DQM, and full conformance coverage.
