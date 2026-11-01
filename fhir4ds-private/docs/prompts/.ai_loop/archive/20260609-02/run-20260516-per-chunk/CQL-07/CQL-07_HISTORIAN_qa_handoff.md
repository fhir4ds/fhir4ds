# CQL-07 HISTORIAN QA Handoff

## Scope

CQL type conversion operators:
ToBoolean, ToConcept, ToDate, ToDateTime, ToDecimal, ToLong, ToInteger,
ToQuantity, ToRatio, ToString, and ToTime.

## QA-001: ToString(Ratio) emits raw JSON

Status: RESOLVED
Severity: HIGH

The official CQL 1.5.3 reference lists `ToString(argument Ratio) String` and
defines the Ratio string representation as `<quantity>:<quantity>`, with the
general rule that `ToString` results must be round-trippable.

Current translated CQL routes `ToString(ToRatio('10 ''mg'':2 ''mL'''))` through
a generic string cast. The result is Ratio JSON instead of the required
quantity-ratio text form such as `10.0 'mg':2.0 'mL'`.

Required repair:
- Add a `RatioToString` DuckDB UDF for Python fallback registration.
- Add a matching native C++ extension UDF.
- Route statically-known CQL Ratio operands for `ToString(...)` and
  `convert ... to String` to `RatioToString`.
- Test direct Python/C++ DuckDB parity and translated CQL behavior.

Resolution:
- Python fallback and native C++ now register `RatioToString`.
- CQL translation routes `ToString(Ratio)` and `convert Ratio to String` to
  `RatioToString`, producing values such as `10.0 'mg':2.0 'mL'`.
- Invalid Ratio quantity components return NULL rather than a misleading string.

Verification:
- `python3 -m pytest fhir4ds/cql/duckdb/tests/test_ratio_udfs.py` passed 35/35.
- Focused CQL-07 parity pytest passed 22/22.
- `./build/release/test/unittest "*cql*"` passed 624 assertions.
- Full `python3 -m pytest fhir4ds -q` passed 7154 tests with 5 skipped.
- Serial `python3 conformance/scripts/run_all.py` passed 2822/2822 overall.
