# QA Handoff - SOF-VD-05 EXPLORER

Personality: EXPLORER
Chunk: SOF-VD-05, recursive `ViewDefinition.select.select`

Spec anchors:
- SQL-on-FHIR v2.0.0 defines `ViewDefinition.select.select` as a recursive nested select relative to the parent expression, and child selects under `forEach` / `forEachOrNull` apply for each parent item.
- The same model defines `where` as a repeating backbone element with required FHIRPath `path` and optional string `description`.

Fresh probe:
- `.temp/qa/sof_vd05_explorer_probe.py`

What passed before the defect:
- Parent `forEach` with two sibling nested child `forEach` rowsets cross-joined correctly under native-loaded and forced Python fallback connections.
- Parent `forEachOrNull` with a nested no-iterator child select preserved the missing parent row as SQL NULL, including a collection-valued child column.
- Deep default `$this` wrapper selects resolved against the root resource under native-loaded and forced Python fallback paths.
- Duplicate parent/child output column names were rejected by generator validation.

Finding:
- `SOFVD05-EXPLORER-001` HIGH, OPEN.
- Direct dataclass `ViewDefinition.to_dict()` / `Select.to_dict()` can serialize invalid nested `select.where` official JSON. Reproducer:

```python
ViewDefinition(
    resource="Patient",
    select=[
        Select(
            column=[Column(path="id", name="id")],
            select=[Select(where=[{"notPath": "active"}])],
        )
    ],
).to_dict()
```

Actual: emitted `{"where": [{"notPath": "active"}]}` under the child select. It also emitted nested where descriptions as `None` or numeric values.

Expected: serializer should reject malformed recursive select `where` shapes with the same validation used by parser and `SQLGenerator.generate()`.

Recommended fix:
- In `Select.to_dict()`, route `self.where` through shared `validate_where_conditions(...)` before serialization.
- Add focused serializer tests for nested select `where` missing `path`, null description, and non-string description.
- Re-run the fresh probe plus focused ViewDefinition parser/where/generator/integration tests and full conformance.
