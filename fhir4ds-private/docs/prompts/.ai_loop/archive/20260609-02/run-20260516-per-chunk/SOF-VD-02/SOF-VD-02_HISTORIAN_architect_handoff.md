# Architect Handoff: SOF-VD-02 HISTORIAN

## Structural Health

The constants surface is structurally sound after remediation. The fix keeps the model boundary in `types.py`: the accepted `value[x]` field set, exactly-one behavior, sql-name validation, and FHIR primitive validation are shared by `parse_view_definition()` and `Constant.from_dict()`. `SQLGenerator` still consumes parsed constants through `ConstantResolver` and does not duplicate value-choice discovery or primitive validation. DuckDB execution remains a downstream FHIRPath concern; native and forced Python fallback produced identical results for `%name_use` substitution in root `where` and column paths.

## QA Audit

QA was adequate for the HISTORIAN role. It used current source and fresh official/spec fixture tests, probed parser validation, public constructors, SQL generation, DuckDB execution, and native/fallback parity. No `RETRY_QA` veto is needed.

## Issue Summary

- `SPEC_VIOLATION`: 2 resolved.
- `API_CONSISTENCY`: 1 resolved.
- New architectural findings: 0.

## Validation Reviewed

- ViewDefinition focused/unit/spec/integration tests passed.
- Full pytest: 7272 passed, 5 skipped.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Recommended Fix Order

No further remediation is required for this chunk.
