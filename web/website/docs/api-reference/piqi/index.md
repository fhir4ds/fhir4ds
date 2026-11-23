---
id: piqi
title: fhir4ds.piqi
sidebar_label: piqi
description: "API reference for fhir4ds.piqi: the PIQI data-quality framework on ViewDefinition + SQLQuery — SAMs, rubrics, scorecards, taxonomy and terminology checks over DuckDB."
---

# `fhir4ds.piqi`

The `fhir4ds.piqi` module implements the PIQI (Patient Information Quality Improvement) framework on the SQL-on-FHIR stack: the PIQI clinical data model as ViewDefinitions, SAMs and rubrics as SQLQuery Libraries executed by the existing `fhir4ds.sqlquery` runner, and per-message scorecards with the PIQI Index.

```python
from fhir4ds.piqi import (
    load_piqi_views, run_sam, run_parameterized_sam, evaluate_rubric,
)
```

---

## 1. Scorecard facade

### `load_piqi_views(connection, *, source_table="resources")`

Materializes every packaged PIQI data-class ViewDefinition as a view in schema `piqi` (10 views). Returns the created view names.

### `run_sam(connection, sam, *, patient_id=None, source_table="resources")`

Executes one SAM instance. `sam` is a packaged instance id (`"piqi-sam-labresult-resultvalue-ispopulated"`) or a custom SAM Library dict. Returns rows with the uniform schema `(patient_id, element_id, data_class, entity, sam_mnemonic, result, detail)`; `result` is `'pass'` or `'fail'` — absence means "could not assess".

### `run_parameterized_sam(connection, sam, parameters, *, patient_id=None, source_table="resources")`

Executes a parameterized SAM (e.g. `Attr_MatchesRegex` with `{"pattern": ...}`); parameters bind through DuckDB prepared statements.

### `evaluate_rubric(connection, rubric, *, patient_id=None, message_id=None, data_provider_id=None, data_source_id=None, source_table="resources", verbose=False) -> PIQIScorecard`

Evaluates a rubric (packaged name `"sample"`, a Library dict, or the `(library, criteria)` tuple from `build_rubric`) and produces the scorecard.

### `PIQIScorecard`

| Field | Type | Description |
|---|---|---|
| `message_id` / `data_provider_id` / `data_source_id` | `str \| None` | Caller tags. |
| `potential_item_score` | `int` | Denominator (scorable items). |
| `total_item_score` | `int` | Numerator (passed items). |
| `piqi_index` | `float` | 0..100 (0 when the denominator is 0). |
| `critical_failure_count` | `int` | Failed critical criteria. |
| `data_class_frequency` | `dict[str, int]` | Rows per rubric-referenced class. |
| `potential_weighted_item_score` / `total_weighted_item_score` / `piqi_weighted_index` | `int \| float \| None` | Emitted only when some weight ∉ {0, 1}. |
| `dimension_rollup` | `dict[str, dict[str, int]]` | HDQT category → dimension → fail counts. |
| `issues` | `list[PIQIIssue]` | Verbose mode: one per failure. |

`PIQIIssue` = `(patient_id, element_id, data_class, entity, sam_mnemonic, dimension, detail)`. `PIQIScorecard.to_dict()` is a hash-stable JSON export.

## 2. Terminology SAMs

### `run_terminology_sam(connection, mnemonic, *, data_class, entity, valueset=None, endpoint=None, use_env=False, patient_id=None, source_table="resources")`

Evaluates `Concept_IsValidMember` or `Concept_IsConsistent` (and `Concept_IsActive`, which is `could not assess` everywhere) over one coded attribute. Resolution: local `valueset_codes` cache first (`provenance: local_valueset_cache`), then a `TerminologyEndpoint` (`terminology_endpoint`); with neither, rows carry `result=COULD_NOT_ASSESS`. Every row carries a `provenance` dict.

## 3. Authoring builders

| Export | Description |
|---|---|
| `build_view(name)` | Build one packaged data-class ViewDefinition dict. |
| `build_rubric(name, description, criteria, ...)` | Author a rubric Library + criteria metadata (returns a `(library, criteria)` tuple consumable by `evaluate_rubric`). Criteria reference SAM instances by id (e.g. `"labresult-test-iscomplete"`); the prerequisite chain is derived from the SAM's own `prereq` edges. |
| `build_parameterized_sam(...)` | Author a parameterized SAM Library (`Attr_MatchesRegex` / `Attr_InList` / `ObservationValueType_InList`). |
| `build_sam_catalog()` | Rebuild the packaged SAM instance catalog. |
| `CANONICAL_BASE` | `https://fhir4ds.org/piqi/` — canonical URL base for authored artifacts. |

## 4. Registry and taxonomy

| Export | Description |
|---|---|
| `get_view(view_name)` / `all_views()` | Packaged ViewDefinitions by name. |
| `get_sam(instance_id)` | A packaged SAM Library. |
| `get_rubric(name)` | A packaged rubric (Library + criteria metadata). |
| `piqi_resolver()` | Canonical-URL resolver over the packaged resources for `SQLQueryRunner`. |
| `PIQIDimension` | HDQT dimension enum (4 categories, 12 dimensions). |
| `resolve_dimension(mnemonic)` / `dimension_for_sam(...)` | Mnemonic → dimension resolution (alias-tolerant). |
| `COULD_NOT_ASSESS` | Sentinel result value for terminology SAMs. |
