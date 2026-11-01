# Engineer Handoff — SOF-SQ-02 (HISTORIAN launch, iteration 1)

## QA-001 (MEDIUM) — RESOLVED
- Reproducer: `SQLQueryRunner.execute` with `parameters={"d": datetime.time(12,0)}` for a declared `date` returned `(datetime.time(12,0),)` — value bound verbatim; declared registry type never applied. Same for `date`→`time` and `datetime`→`date`.
- Root cause: `runner._coerce`'s temporal branch returned any non-string `datetime` value untouched (`if not isinstance(value, str): return value`) — the Python-native analogue of the SKEPTIC's string-path gap.
- Fix (spec-grounded in `StructureDefinition-SQLQuery-notes.md` § Parameter Types "callers must honour" the declared type): new `_TEMPORAL_KINDS` registry maps DATE→date (datetime explicitly rejected: higher precision than declared), TIMESTAMP→(datetime, date; date accepted as less-precise dateTime, consistent with the earliest-instant partial-date doctrine), TIME→time. Every accepted value — string or native — is routed through the prepared `SELECT CAST(? AS <registry type>)` so the declared type always reaches DuckDB; wrong-kind values raise `SQLQueryTypeError` with declared-vs-got.
- Regression tests: new `TestNativeTemporalKindEnforcement` in `fhir4ds/sqlquery/tests/test_integration.py` (5 tests: time-for-date, datetime-for-date, date-for-time rejections; date-for-dateTime midnight; matching-native coercion fidelity).

## QA-002 (LOW) — RESOLVED (doc)
- `_bind_parameters` comment falsely claimed prepared SQL "would only consume the names it references"; DuckDB actually raises InvalidInputException for declared-but-unreferenced params. Comment corrected to document the real semantics. No behavior change (the DuckDB error is clear and no spec mandates a typed error here).

## Validation
- Focused: `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/sqlquery/tests/ -q` → 94/94 (89 baseline + 5 new).
- Reproducer re-run post-fix: time-for-date / datetime-for-date / date-for-time → SQLQueryTypeError; date-for-dateTime → midnight datetime; date-for-date / time-for-time / datetime-for-dateTime preserve values and registry types.
- Master gate (fresh): see architect handoff for final counts.
- Binary md5s (repo == site-packages, no native code touched): cql.duckdb_extension c5b22d58310c1eb7bafa17ce7877f989; fhirpath.duckdb_extension 57d0634b6ee6eddee9fc06a1355bef5a.

No workarounds; coercion remains registry-driven (`_TEMPORAL_KINDS` keyed by registry DuckDB type, no FHIR-type branching). No new issues discovered during fix.
