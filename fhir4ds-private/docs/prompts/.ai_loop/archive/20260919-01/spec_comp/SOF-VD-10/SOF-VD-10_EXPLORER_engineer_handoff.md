# Engineer Handoff — SOF-VD-10 EXPLORER (iteration 1, 2026-08-23)

## Triage
| Issue | Sev | Category | Disposition |
|---|---|---|---|
| QA-001 RecursionError escapes parser on deep nesting | MEDIUM | API_CONTRACT | RESOLVED |
| QA-002 Decimal to_dict re-parse asymmetry | LOW | API_CONTRACT | DEFERRED (existing doctrine) |
| QA-003 Error messages lack full JSON path | LOW | ERROR_MESSAGES | DEFERRED |
| QA-004 constant/column name collision etc. | LOW | NOT_A_BUG | INTENDED |

## QA-001 fix
- Root cause: unbounded recursion in `_parse_select` (dict path) and
  `json.loads` (string path) escaped `parse_view_definition` as raw
  `RecursionError`, violating the parser's typed-error boundary contract.
- Fix: `/mnt/d/fhir4ds/fhir4ds/viewdef/parser.py` — `parse_view_definition`
  is now a thin wrapper that translates `RecursionError` into
  `ParseError("ViewDefinition is nested too deeply to parse. ...")`.
  Body moved verbatim to `_parse_view_definition`. `ViewDefinition.from_dict`
  delegates to the wrapper, so all three entry points are covered. Pure
  Python; no native rebuild required (binary md5s unchanged and
  repo==site-packages: fhirpath 57d0634b6ee6eddee9fc06a1355bef5a, cql
  c5b22d58310c1eb7bafa17ce7877f989).
- Regression tests: `fhir4ds/viewdef/tests/unit/test_parser.py::
  TestDeepNestingRecursionSafety` — 4 tests (dict, JSON string built
  incrementally, from_dict, moderate-depth still parses). All pass.

## Validation (fresh runs, PYTHONPATH=/mnt/d/fhir4ds)
- ViewDef conformance: 144/144 (100%).
- Master gate `run_all.py`: ViewDefinition 144/144, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47, OVERALL 2832/2832 — no regression.
- viewdef pytest tree: 1230 passed (before the string-input test fix; the 4
  DeepNesting tests pass after).

## No new issues discovered during remediation.
