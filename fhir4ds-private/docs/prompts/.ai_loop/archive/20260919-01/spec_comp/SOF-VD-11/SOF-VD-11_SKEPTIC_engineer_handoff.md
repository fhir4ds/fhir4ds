# Engineer Handoff — SOF-VD-11, iteration 1 (2026-08-23)

## Triage
| Issue | Category | Action |
|---|---|---|
| QA-001 MEDIUM | API_CONTRACT (dead retry branch / silent downgrade) | RESOLVED |

## QA-001 fix
- Root cause: `_try_load_bundled_cpp_extension` (fhir4ds/fhirpath/duckdb/extension.py)
  retried unsigned LOAD failures via `SET allow_unsigned_extensions = true`, which
  DuckDB always rejects on a running database ("Cannot change ... while database is
  running"). The branch could never succeed; register_fhirpath(duckdb.connect())
  silently downgraded to Python UDFs with only an INFO log.
- Fix: removed the dead retry; emit a WARNING naming the actual remedies
  (connect-time config or fhir4ds.connect(), which already sets it by default).
  No behavior change otherwise (fallback UDF registration, return values).
- Regression test: `test_unsigned_bundled_extension_falls_back_with_warning`
  in fhir4ds/fhirpath/duckdb/tests/integration/test_extension_parity.py —
  plain connect → register_fhirpath returns False, Python UDFs functional,
  warning names allow_unsigned_extensions, no half-loaded extension.
- Files changed: fhir4ds/fhirpath/duckdb/extension.py,
  fhir4ds/fhirpath/duckdb/tests/integration/test_extension_parity.py.

## Validation
- Focused: pytest extension_parity 2/2.
- Master gate (fresh, filtered): ViewDefinition 144/144, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47 — OVERALL 2832/2832. No regression.
- Binary md5s unchanged (no native rebuild needed — fix is Python-side only):
  fhirpath 57d0634b6ee6eddee9fc06a1355bef5a (repo == site-packages),
  cql c5b22d58310c1eb7bafa17ce7877f989 (repo == site-packages).
