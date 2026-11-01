# Code Review Findings

## Scope

Reviewed the remediation changes for the CQL tests runner compatibility work:

- parser Ratio literal handling;
- translator type inference and operator routing changes;
- DuckDB CQL macro/UDF semantic changes;
- FHIR `$cql` facade regression tests for Long and code-only Concept output;
- `conformance/scripts/run_cql_tests_runner.py` harness skip documentation.

## Findings

No blocking findings.

## Review Notes

- The runner skip list is limited to documented runner comparison/extractor
  limitations. Local facade integration tests verify the corresponding FHIR4DS
  behavior for Long result metadata and code-only `Concept` serialization.
- Changed macro SQL uses static SQL text or static guard fragments; no user
  input is interpolated into DuckDB SQL.
- Runner subprocess calls use argument lists with `shell=False`.
- Final full runner report:
  `conformance/reports/cql_tests_runner_full_report_final.json`
  with `1669 passed / 62 skipped / 0 failed / 0 errors`.

