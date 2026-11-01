# Engineer Handoff — SOF-SQ-03 (iteration 1, HISTORIAN)

## Triage table
| Issue | Category | Triage |
|---|---|---|
| QA-005 main-body duckdb errors escape raw | ERROR_MODEL_CONSISTENCY | INTENDED |
| QA-006 resolver docstring understates contract | API_CONTRACT (docstring) | RESOLVED |

## Changes
1. `fhir4ds/sqlquery/runner.py` — `SQLQueryRunner.__init__` resolver docstring now states the full
   `DependencyResolver` contract: parsed `ViewDefinition`/`SQLQuery`/`SQLView` objects, structural
   ViewDefinition dicts (`select`+`resource`), and Library dicts, for any canonical. No behavior change.
2. `fhir4ds/sqlquery/tests/test_integration.py` — new `TestHistorianLaunch` (4 tests) locking in:
   mixed resolver shapes in ONE dependency list; parse→to_dict→re-parse byte-stability + identical
   execution; nested two-level resolver failure carries the failing level's label+canonical with
   `__cause__` preserved; duckdb-dialect preferred over plain `application/sql`.

## Rationale
- QA-005 INTENDED: no chunk mandate item covers main-body execution errors; the module threat model
  explicitly excludes author-controlled SQL; wrapping would mask duckdb diagnostics. Registered in
  `fhir4ds/sqlquery/AGENTS.md` NOT A BUG registry.

## Validation
- sqlquery suite: 113/113 (was 109/109; +4 new).
- Master gate: 2832/2832 (ViewDefinition 144, FHIRPath 935, CQL 1706, DQM 47).
- Binary md5s repo↔site-packages matched (fhirpath 57d0634b6ee6eddee9fc06a1355bef5a,
  cql c5b22d58310c1eb7bafa17ce7877f989); no native code touched this launch.
