# Engineer Handoff - CQL-21 HISTORIAN

Issue handled:
- `QA-001` MEDIUM was reproduced on both forced Python fallback and
  native/C++ registrations: raw direct SQL `Count(ExpandValueSet(?))` returns
  `1` even though `ExpandValueSet(?)` is a two-item `VARCHAR[]`.

Disposition:
- `QA-001` is `DEFERRED`, not fixed in production code. The CQL spec-governed
  translated path already handles `Count(ExpandValueSet(Vitals))` correctly and
  is covered in `test_clinical_operator_parity.py`.
- The raw direct SQL spelling collides with DuckDB's built-in `Count` aggregate.
  A scalar UDF cannot be registered over that aggregate name, and a macro
  shadow makes `COUNT(DISTINCT ...)`, `FILTER`, window, and row-aggregate usage
  invalid. Adding a safe public direct-list `Count` surface requires a broader
  API design than this clinical-operator remediation loop should take on.

Validation:
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py -q` -> 13 passed.
- Manual macro/UDF experiments confirmed the namespace collision and row
  aggregate regressions.

Files changed by this role:
- `AGENTS.md`
- `fhir4ds-private/docs/prompts/.ai_loop/evolution.json`
- `fhir4ds-private/docs/prompts/.ai_loop/engineer_handoff.md`
