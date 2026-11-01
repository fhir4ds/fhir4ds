# Architect Handoff - SOF-VD-09/HISTORIAN

Architectural result: PASS.

Golden standard:
- `.temp/architect/golden_standard.md` records the root `where` invariants for
  parser, serializer, direct dataclass validation, SQL generation, constants,
  current/root scope, and native/fallback parity.

Audit summary:
- The current implementation routes root `ViewDefinition.where` through shared
  `validate_where_conditions()` boundaries in parser, serializer, and direct
  SQL-generator preflight.
- SQL generation preserves exact singleton Boolean true semantics with
  `fhirpath_json(...) = '[true]'`, avoiding DuckDB truthiness/coercion.
- Root filters are applied against the root resource after row generators are
  composed, while branch/select filters retain their own current focus.
- Constants resolve through `ConstantResolver` before SQL generation.
- No hardcoded fixture/resource/profile-specific behavior was found in this
  scope.

QA quality assessment:
- Adequate. The fresh HISTORIAN probe covered official root `where` model
  validation, metadata retention, constants, complex FHIRPath, false/empty/
  missing/non-Boolean exclusions, and root scope across `forEach` and
  `unionAll` under native-loaded and forced Python fallback execution.
- `RETRY_QA` is not required.

Validation:
- Fresh probe: `PASS: SOF-VD-09 HISTORIAN root where probe`
- Focused parser/where/DuckDB pytest: `285 passed`
- ViewDefinition conformance: `134/134 tests passed (100.0%)`
- Full conformance: `2822/2822` overall

Issues by category:
- `SPEC_VIOLATION`: 0
- `API_CONTRACT`: 0
- `DATA_HANDLING`: 0
- `REGRESSION_RISK`: 0

Recommended fix order:
- None for this pass.

Notes:
- `REV-045-001` remains open and outside this root `where` pass.
- `spec_schedule.json` and `ARCHIVE_LOG.md` were not modified.
