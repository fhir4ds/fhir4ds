# Engineer Handoff — SOF-VD-13 EXPLORER launch (2026-08-24)

## Triage
| Issue | Sev | Category | Terminal state |
|---|---|---|---|
| QA-001 | LOW | SPEC_VIOLATION | RESOLVED |
| QA-002 | LOW | API_SURFACE | INTENDED |

## QA-001 (RESOLVED)
- Root cause: `fhir4ds/viewdef/parser.py:validate_view_definition` gated the cnl-0 warning on `vd.name[0].isupper()`, which is unicode-aware; CanonicalResource cnl-0 regex `^[A-Z]([A-Za-z0-9_]){1,254}$` has an ASCII-only first-char class, so 'Éxample' must warn. Only reachable via directly-constructed ViewDefinition objects (JSON parse path pre-empted by the sql-name ParseError).
- Fix: explicit ASCII range check `"A" <= vd.name[0] <= "Z"` with a comment citing the spec regex.
- Test: `TestCnl0NameWarningPerSpecG2::test_non_ascii_capital_name_warns` in `fhir4ds/viewdef/tests/unit/test_parser.py`.

## QA-002 (INTENDED)
- `generate_view_sql()` neither logs nor returns validator warnings. Not spec-mandated; the sql-on-fhir.js reference does not surface cnl warnings either. Programmatic capture exists via exported `validate_view_definition()` (returns warning list). Recorded in AGENTS.md NOT A BUG registry.

## Validation (final tree, PYTHONPATH=/mnt/d/fhir4ds)
- cnl-focused unit tests: 18/18 passed.
- ViewDefinition suite: 144/144 (100%).
- Master gate: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47) — no regressions.
- Binary md5s (no native changes this launch): cql.duckdb_extension c5b22d58310c1eb7bafa17ce7877f989 (repo == site-packages); fhirpath.duckdb_extension 57d0634b6ee6eddee9fc06a1355bef5a (repo bundle == release build).

## Files changed
- /mnt/d/fhir4ds/fhir4ds/viewdef/parser.py (cnl-0 ASCII check)
- /mnt/d/fhir4ds/fhir4ds/viewdef/tests/unit/test_parser.py (regression test)
