ARCHITECT HANDOFF - SOF-VD-03 HISTORIAN

Golden standard:
- Wrote `.temp/architect/golden_standard.md` with 10 ViewDefinition invariants
  covering parser boundaries, repeating-element JSON shape, column sql-name
  validation, effective output schema uniqueness, `unionAll` branch equality,
  root/select-relative context handling, and DuckDB FHIRPath UDF routing.

Structural audit:
- The remediation is architecturally sound. Parser and public constructor
  boundaries now reject present-null repeating select containers without
  changing absent-field semantics. The generator validates duplicate names at
  the effective output-schema boundary while preserving legitimate matching
  `unionAll` branch schemas. No test-specific hardcoding or new layer crossing
  was introduced.

QA audit:
- QA was sufficient for HISTORIAN scope. It covered parser validation, SQL
  generation, DuckDB execution, official ViewDefinition fixtures via the
  ViewDefinition suite, deterministic column order, and native C++ versus
  forced Python fallback parity. No `RETRY_QA` needed.

Issue counts:
- SPEC_VIOLATION: 2 resolved.
- New architecture findings: 0.

Recommended fix order:
- None for this iteration. Both logged issues are resolved and verified.

Validation reviewed:
- Focused parser/generator pytest: 32 passed.
- Full ViewDefinition pytest: 771 passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.
