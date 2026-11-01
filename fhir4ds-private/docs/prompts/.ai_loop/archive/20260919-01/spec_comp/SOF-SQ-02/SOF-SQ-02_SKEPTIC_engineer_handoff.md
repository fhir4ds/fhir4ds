# Engineer Handoff — SOF-SQ-02 (iteration 1)

All 5 issues RESOLVED in `/mnt/d/fhir4ds/fhir4ds/sqlquery/runner.py` (`_coerce`, `_bind_parameters`, new `_expand_partial_temporal`, new `_INTEGER_RANGES` / `_TEMPORAL_DUCKDB_TYPES` registries).

- QA-001 (HIGH): temporal params now coerced via DuckDB prepared `SELECT CAST(? AS <registry type>)` on the runner's connection; value bound, type name from the internal whitelist — no interpolation. Malformed strings and wrong Python types raise `SQLQueryTypeError` with parameter name + declared vs got. Root cause: `duckdb_type` was only used for isinstance gates on numeric/boolean paths; temporal path returned the value untouched.
- QA-002 (MEDIUM): explicit `bool` guard before integer/decimal isinstance checks.
- QA-003 (MEDIUM): signed 32/64-bit range enforcement (`integer` → int32, `integer64` → int64), matching FHIR widths; `integer64` values beyond int32 still accepted.
- QA-004 (MEDIUM): `decimal.Decimal` accepted for `decimal` (faithful FHIR decimal, per project parse_float=Decimal doctrine), converted to `float`.
- QA-005 (MEDIUM, discovered during fix verification): FHIR partial dates/dateTimes (`2020`, `2020-06`, date-only dateTime) normalize to the earliest instant of the stated period through a strict regex grammar before the cast; garbage still rejected.

## Validation
- Focused: `python3 -m pytest fhir4ds/sqlquery/tests/ -q` → 89/89 (70 baseline + 19 new in `TestParameterCoercionFidelity`).
- Master gate (fresh, PYTHONPATH=/mnt/d/fhir4ds): ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2832/2832 — baseline holds.
- Binary md5s (repo == site-packages, no native code touched): cql.duckdb_extension c5b22d58310c1eb7bafa17ce7877f989; fhirpath.duckdb_extension 57d0634b6ee6eddee9fc06a1355bef5a.

No workarounds; coercion semantics stay registry-driven. No new issues discovered beyond QA-005 (fixed).
