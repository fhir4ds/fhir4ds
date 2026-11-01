# Code Review Findings - Release 0.0.8 Loop

## Findings

No blocking code-review findings.

## Review Scope

- DQM config/HAPI/Mongo malformed-input validation.
- `FileSystemSource` constructor validation and SQL quoting boundaries.
- DQM audit evidence pruning and Mongo compact materialization output shape.
- Release version consistency tests and CQL tests-runner metadata.
- Website/WASM release asset updates and TypeScript return-type fix.

## Notes

- DQM pruning has two call styles: direct `evaluate()` passes the current
  group, while compiled execution relies on `_group_id`. The helper correctly
  narrows to matching group IDs when `_group_id` is present.
- The CQL tests-runner metadata change is limited to generated Build metadata;
  runner invocation, server creation, result parsing, and skip-list behavior
  are unchanged.
- Website/WASM release changes follow the local checklist: single current
  public wheel, rebuilt demo, refreshed website static snapshot, and website
  typecheck/build validation.

## Verification

- `python3 -m pytest fhir4ds/dqm/tests/unit/test_config.py fhir4ds/dqm/tests/unit/test_hapi_materialization.py fhir4ds/dqm/tests/unit/test_mongo_materialization.py fhir4ds/dqm/tests/unit/test_evaluator.py fhir4ds/sources/tests/unit/test_filesystem.py -q`
  - 136 passed, 2 existing DQM DataFrame deprecation warnings.

## Residual Risk

- Full pre-release gates still need to rerun conformance, package pytest,
  benchmark comparison, wheel install/import checks, and website/docs gates.
