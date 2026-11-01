# QA Handoff: SOF-VD-06/EXPLORER

Scope: SQL-on-FHIR ViewDefinition `select.forEach` and `select.forEachOrNull`.

Personality: EXPLORER.

Spec anchors:
- SQL-on-FHIR v2.0.0 ViewDefinition definitions: `select.forEach` is `0..1 string` and produces one row per selected element; `select.forEachOrNull` is `0..1 string` and preserves a single row with null nested values when the selected collection is empty. Source: https://sql-on-fhir.org/ig/2.0.0/StructureDefinition-ViewDefinition-definitions.html
- SQL-on-FHIR functional model: iterators flatten nested collections, `forEach` removes records with no results, `forEachOrNull` keeps an empty record, `%rowIndex` is 0-based within the active iterator, top-level `%rowIndex` is 0, and `select` cross-joins row sets. Source: https://sql-on-fhir.org/ig/latest/functional-model.html

Fresh probe:
- Wrote and ran `.temp/qa/sof_vd06_explorer_probe.py`.
- Covered present JSON null rejection for `forEach` and `forEachOrNull`.
- Covered direct dataclass mutual exclusion for `forEach` plus `forEachOrNull`.
- Covered top-level `%rowIndex`, parent `forEachOrNull` null-row preservation, and `%context`/`%resource`/`%rootResource` routing.
- Covered parent `%rowIndex` embedded inside a child iterator expression: `%context.given[%rowIndex]`.
- Covered nested `forEachOrNull` null rows combined with a sibling `forEach` that suppresses resources with no matching phone.
- Ran both forced Python fallback and the normal/native-loaded DuckDB registration path.

Result: no product defects found.

Validation:
- Fresh EXPLORER probe: PASS.
- Focused iterator/row-index pytest: `138 passed`.
- Full ViewDefinition pytest: `950 passed`.
- ViewDefinition conformance: `134/134`.
- Full conformance: `2822/2822` (`ViewDefinition 134/134`, `FHIRPath 935/935`, `CQL 1706/1706`, `DQM 47/47`).

Notes:
- Mixed `%context` and `%resource` or `%rootResource` inside one non-leading FHIRPath expression still fails fast by design because the current DuckDB UDF surface accepts a single JSON input context. The probe avoided treating that intentional boundary as a defect.
