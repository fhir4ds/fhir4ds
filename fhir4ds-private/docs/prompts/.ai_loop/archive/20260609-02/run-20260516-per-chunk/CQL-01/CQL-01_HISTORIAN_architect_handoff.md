# Architect Handoff — CQL-01 HISTORIAN

## Verdict
- `CLEAN`

## Review Notes
- Confirmed the HISTORIAN finding was real: primitive CQL `as` is a runtime type assertion and mismatched primitive assertions must return NULL.
- Found one regression in the first remediation: dynamic FHIR/measure value assertions became too strict when the SQL value was physically `VARCHAR`, causing CMS771 SQL binding failure and CMS0334 accuracy loss.
- Remediated the regression by keeping literal and known conversion-function results strict, while using lexical guards plus `TRY_CAST` for dynamic FHIR/measure values so downstream arithmetic receives typed SQL.

## Validation
- Focused primitive parity pytest: 5 passed.
- Targeted DQM regression rerun for CMS771 and CMS0334: 2/2 measures at 100%.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- Broad CQL unit/integration/DuckDB integration pytest: 1359 passed, 5 skipped.
- `git diff --check`: clean.

## Residual Risk
- No open CQL-01 HISTORIAN findings. EXPLORER should independently retest primitive `as` in less direct query shapes, including nullable columns and FHIRPath-derived primitive values.
