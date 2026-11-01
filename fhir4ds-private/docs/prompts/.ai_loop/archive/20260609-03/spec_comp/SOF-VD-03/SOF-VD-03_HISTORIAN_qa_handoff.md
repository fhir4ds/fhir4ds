# QA Handoff: SOF-VD-03 HISTORIAN

Scope: SQL-on-FHIR ViewDefinition select/column logical-model compliance for `SOF-VD-03`.

Spec anchor: SQL-on-FHIR v2 `ViewDefinition.select` is required `1..*`; `select.column` is `0..*`; `column.path` and `column.name` are required `1..1`; `column.name` must satisfy `^[A-Za-z][A-Za-z0-9_]*$`; `column.description` is optional markdown metadata; nested columns are relative to the active select context.

Fresh probe: `.temp/qa/sof_vd03_historian_probe.py`.

Coverage:
- Parser rejection for missing/empty/non-array root `select`.
- Parser rejection for missing `column.path`, missing/invalid `column.name`, and non-string `column.description`.
- `to_dict()` markdown retention and deterministic column ordering.
- Direct dataclass serializer/generator guard paths for invalid column names and empty root select.
- Generated SQL projection ordering across multiple select blocks.
- DuckDB execution for root columns plus `forEach`-relative columns and `%rootResource.id`.
- Native-loaded FHIRPath registration and forced Python fallback registration.
- Official repo fixtures from `basic.json` and `combinations.json`.

Result: no new issues found. `evolution.json` remains with an empty `issues` array.

Validation:
- Fresh probe: PASS.
- Focused parser/generator/spec pytest: `677 passed`.
- Full ViewDefinition pytest: `940 passed`.
- ViewDefinition conformance: `134/134`.
- Full conformance: `2822/2822`.
