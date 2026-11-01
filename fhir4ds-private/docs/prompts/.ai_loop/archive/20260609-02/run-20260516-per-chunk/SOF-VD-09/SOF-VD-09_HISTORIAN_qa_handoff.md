# QA Handoff - SOF-VD-09 HISTORIAN

## Scope

SQL-on-FHIR ViewDefinition root `where` semantics after the prior SKEPTIC remediation. This pass independently checked root-level FHIRPath constraints, exact Boolean inclusion, false/empty/null exclusion, non-Boolean result handling, `where.description` retention and validation, constants in root predicates, complex FHIRPath, and root-resource SQL scope over a shared mixed-resource table.

## Spec Basis

Verified against SQL-on-FHIR v2.0.0 `StructureDefinition-ViewDefinition` and functional model:

- `ViewDefinition.where` is `0..*` and every constraint must evaluate true for the resource to be included.
- `ViewDefinition.where.path` is a FHIRPath expression evaluated with the root resource collection as input and may reference constants with `%name`.
- `ViewDefinition.where.description` is `0..1` string metadata.
- The functional model `where` retains only rows whose FHIRPath expression returns true.

## Fresh Probe

Created and ran `.temp/qa/sof_vd_09_historian_probe.py`.

Probe coverage:

- `active` root predicate includes only singleton Boolean true.
- `active=false`, missing `active`, JSON null `active`, literal `false`, and `{}` exclude rows.
- Non-Boolean valid FHIRPath values (`id`, `'true'`, `1`) do not satisfy the filter.
- Two root `where` predicates combine as AND, including constants and `name.where(...).exists()`.
- Root `where` remains scoped to the root Patient while a nested `forEach` iterates `name`.
- Shared physical `resources` table emits and honors the `resourceType = 'Patient'` predicate.
- Parser and `ViewDefinition.from_dict()` preserve valid `where.description` and reject numeric/null descriptions; generator direct-dataclass guard also rejects invalid metadata.
- Native C++ DuckDB registration and forced Python fallback produced identical outputs.

Result: PASS, 7 cases. Native extension was available.

## Validation

- Fresh probe: PASS.
- Focused unit/parser where tests: `33 passed, 131 deselected`.
- Focused integration where tests: `5 passed, 50 deselected`.
- Targeted SKEPTIC regression integration tests: `3 passed`.
- ViewDefinition conformance: `134/134 tests passed (100.0%)`.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Findings

No new issues. No `evolution.json` issue entries were added.
