# Engineer Handoff: SOF-VD-11 / EXPLORER

## Issue Resolved
- `SOF-VD-11-EXPLORER-001` HIGH, RESOLVED.

## Root Cause
- `SQLGenerator` disabled runtime `type().name` guards in iterator contexts because unrolled JSON fragments can have backend-dependent FHIRPath type metadata.
- That left no replacement type check for iterator aliases, so numeric/Boolean values declared as `string` could silently coerce.
- The direct `$this` branch also generated mixed DuckDB types, e.g. `COALESCE(fhirpath_number(...), CAST(json AS VARCHAR))`, causing valid `$this` integer projections to fail at bind time.
- `%rowIndex` was treated as a raw ordinal and only cast for integer-compatible declarations, so incompatible declarations such as `type: "string"` were accepted.

## Remediation
- Added physical JSON type guards for iterator contexts where FHIRPath metadata guards are disabled.
- Reworked `$this` column SQL generation so numeric/Boolean typed columns use typed UDF output and casts without a VARCHAR fallback.
- Added static `%rowIndex` declared-type validation and a `%rowIndex` decimal/integer-compatible cast path.
- Added integration regressions for native-loaded and forced Python fallback execution.
- Updated `fhir4ds/viewdef/AGENTS.md` with the fragile boundary.

## Files Changed
- `fhir4ds/viewdef/generator.py`
- `fhir4ds/viewdef/tests/integration/test_duckdb.py`
- `fhir4ds/viewdef/AGENTS.md`
- `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd11_explorer_probe.py`
- `fhir4ds-private/docs/prompts/.ai_loop/evolution.json`
- `fhir4ds-private/docs/prompts/.ai_loop/qa_handoff.md`

## Validation
- Fresh EXPLORER probe: PASS on native and forced fallback.
- Focused regression tests: `2 passed`.
- ViewDefinition tests: `979 passed`.
- ViewDefinition conformance: `134/134`.
- Full conformance: `2822/2822`.
