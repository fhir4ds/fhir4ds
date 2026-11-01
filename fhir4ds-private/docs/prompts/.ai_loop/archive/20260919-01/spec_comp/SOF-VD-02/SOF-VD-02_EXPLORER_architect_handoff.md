# Architect Handoff — SOF-VD-02 (EXPLORER), iteration 1

## Golden-standard check (chunk-local invariants)
1. Constant handling has a single canonical module (`viewdef/constants.py`); builtin variable set defined once and imported. — Holds; fix touched only `generator.py` guard classification.
2. Fixes must be general, not reproducer-shaped. — Holds: the `true`/`false` literal routing fix covers ANY bare boolean-literal column path (constant-fed or hand-written), matching the existing expression-guard semantics (complex-guard branch rejects only OBJECT/ARRAY JSON).
3. Dual-engine lockstep: any behavioral ViewDef change needs native + Python-fallback coverage. — Holds: regression tests run both engines (`allow_unsigned_extensions` native and forced-fallback monkeypatch); outputs identical.
4. Spec citation in code. — Holds: the new branch comment cites the SQL-on-FHIR v2 column.type invariant.
5. No silent fallbacks introduced. — Holds; QA-002 (builtin shadowing silence) is pre-existing, spec-silent, DEFERRED with recommendation.

## QA Enforcer Gate
QA executed the full EXPLORER mandate e2e (const-vs-const, unionAll depth, forEachOrNull guards, mixed boolean where, function args incl. quantity-magnitude adjudication, base64/url/uuid/oid/canonical quoting round-trips, builtin shadowing, 120 constants, sql-name edges, prior-fix re-verification). Probes were execution-based, not parse-only. No RETRY_QA.

## Verification (final tree)
- Focused: 2 new integration tests pass (both engines).
- `pytest fhir4ds/viewdef/tests`: 1170 passed (baseline 1168 + 2 new).
- `conformance/scripts/run_viewdef.py`: 144/144 (100%).
- Master gate `run_all.py` (PYTHONPATH=/mnt/d/fhir4ds): OVERALL 2832/2832 — ViewDef 144, FHIRPath 935, CQL 1706, DQM 47. Baseline holds.
- Binaries unchanged (Python-only fix), md5 repo == site-packages: fhirpath 57d0634b6ee6eddee9fc06a1355bef5a, cql c5b22d58310c1eb7bafa17ce7877f989.

## Terminal state
- QA-001 MEDIUM RESOLVED/VERIFIED (fix + dual-engine tests + gates).
- QA-002 LOW DEFERRED (spec ambiguity; surfaced for human).
- Iteration 1 >= min_iterations 1; zero non-terminal CRITICAL/HIGH/MEDIUM → CLEAN exit. workflow=null.
