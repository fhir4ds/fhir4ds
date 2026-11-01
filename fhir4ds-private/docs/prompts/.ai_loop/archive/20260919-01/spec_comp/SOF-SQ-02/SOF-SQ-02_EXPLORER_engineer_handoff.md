# Engineer Handoff — SOF-SQ-02 launch 3 (EXPLORER follow-up fixes)

## Triage

| Issue | Cat | Severity | Terminal state |
|---|---|---|---|
| QA-001 `:name` spec-example placeholders unsupported | SPEC_VIOLATION | HIGH | RESOLVED |
| QA-002 tz-aware datetime binds host-tz-dependently | DATA_HANDLING | HIGH | RESOLVED |
| QA-003 positional/mixed placeholder bodies raw-error | API_CONTRACT | LOW | INTENDED (documented) |
| QA-004 '24:00:00' TIME cast returns str | upstream | LOW | INTENDED (engine quirk) |

## Fixes

1. **QA-001** — `fhir4ds/sqlquery/runner.py`: new `SQLQueryRunner._rewrite_named_placeholders` (static). Before execution, declared-and-supplied `:name` placeholder tokens are rewritten to DuckDB's `$name`. The scanner skips single-quoted literals (with `''` escape), double-quoted identifiers, `--` and `/* */` comments, and the `::` cast operator; undeclared `:name` tokens are left verbatim so the engine's original error surfaces. Spec basis: sql-on-fhir-v2 `input/fsh/examples/sql-query-examples.fsh` (UniquePatientAddressesQuery `:city`) and `StructureDefinition-SQLQuery-notes.md` SQL Annotations (`:patient_id`, `:from_date`). No caller value is ever interpolated — the prepared-statement dict still carries all values.
2. **QA-002** — `fhir4ds/sqlquery/runner.py` `_coerce`: tz-aware `datetime.datetime` parameter values are normalized to naive wall time (`replace(tzinfo=None)`) before the registry CAST. Previously DuckDB converted native aware values through the host timezone (10:30+00:00 → 05:30 on host tz −5) while the identical string spelling cast to wall time 10:30 — same instant, different bound value per host. Now both spellings bind identically and deterministically.

## Regression tests

`fhir4ds/sqlquery/tests/test_integration.py`: new `TestSpecExamplePlaceholders` (6 tests: bind-by-name, reuse ×3, CAST+INTERVAL, colons in literals/line+block comments, `::` operator, undeclared-colon passthrough) and `TestTimezoneAwareDatetimeBinding` (2 tests: aware==string spelling incl. UTC; non-UTC offset keeps wall time).

## Validation

- sqlquery suite: 102/102 passed (was 94; +8 new).
- sqlquery+viewdev pytest: 1343 passed.
- Master gate `conformance/scripts/run_all.py`: OVERALL COMPLIANCE 2832/2832 (100%) — baseline held.
- Binaries: cql.duckdb_extension md5 c5b22d58310c1eb7bafa17ce7877f989; _duckdb.cpython-310-x86_64-linux-gnu.so md5 9c3ab5bfdc2aac48fc45013c5ad8ce9f (duckdb 1.5.2).

## New issues discovered

None during remediation.
