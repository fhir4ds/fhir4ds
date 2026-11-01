# Engineer Handoff — SOF-VD-05 HISTORIAN (iteration 1, 2026-08-23)

## Triage
| Issue | Severity | Category | Classification |
|---|---|---|---|
| QA-001 repeat collects only complex (dict) elements; primitive-yielding repeat paths return empty (both engines) | LOW | SPEC_GAP_UNPINNED | INTENDED |

## Work performed
No code changes required this launch. The only logged issue (QA-001) is terminal
INTENDED: the v2 SD (2.0.0 releases) defines no `select.repeat` element at all;
repeat behavior is pinned solely by the legacy sql-on-fhir.js fixture suite whose
repeat paths exclusively traverse object elements, and upstream sof-js (main) no
longer implements repeat. Native C++ and Python fallback agree (parity P3).
Documented in `fhir4ds/viewdef/AGENTS.md` NOT-A-BUG section per Step 5/§6.

Both SKEPTIC fixes from the prior launch were re-verified regression-free at
depth (unknown select-field rejection at depth 3 and inside unionAll branches;
present-empty column/select array rejection) via probe R1–R4.

## Validation (final tree, PYTHONPATH=/mnt/d/fhir4ds)
- ViewDef pytest: 1185/1185 passed.
- Master conformance gate `conformance/scripts/run_all.py` (fresh run):
  ViewDefinition 144/144, FHIRPath (R4) 935/935, CQL 1706/1706, DQM 47/47,
  OVERALL 2832/2832 — baseline held.
- Binary md5s (repo == ~/.local site-packages):
  fhirpath.duckdb_extension 57d0634b6ee6eddee9fc06a1355bef5a
  cql.duckdb_extension c5b22d58310c1eb7bafa17ce7877f989

## New issues discovered
None.
