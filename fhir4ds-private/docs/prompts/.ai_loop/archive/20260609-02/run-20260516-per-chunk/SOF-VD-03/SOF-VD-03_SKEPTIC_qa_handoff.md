# QA Handoff - SOF-VD-03 SKEPTIC

## Scope

SQL-on-FHIR ViewDefinition select/column behavior: required non-empty root `select`, `column` cardinality, `column.path`, `column.name`, `column.description`, deterministic ordering, and root/select-relative FHIRPath execution contexts.

## Spec Anchors

- SQL-on-FHIR v2.0.0 `ViewDefinition.select` is `1..*`; `ViewDefinition.select.column` is `0..*`; `column.path` and `column.name` are `1..1` strings; `column.name` has the `sql-name` regex `^[A-Za-z][A-Za-z0-9_]*$`.
- `column.description` is `0..1 markdown` and should be retained when valid.
- Nested `select` is relative to a parent expression; if the parent has `forEach`/`forEachOrNull`, child paths apply to each selected item.

## Hypotheses Tested

1. Column SQL-name validation was probably copied from generic SQL identifier validation and still allowed leading underscores.
2. Parser shape validation likely assumed arrays/objects and leaked Python `AttributeError` for malformed `select` or `column`.
3. `column.path` and `column.name` truthiness checks likely accepted non-string values and deferred failure to SQL generation.
4. Markdown descriptions were likely retained without primitive type validation.
5. Multiple top-level selects and nested relative context might reorder columns or evaluate against the wrong root.
6. Native C++ and forced Python fallback might differ on nested/relative FHIRPath execution.

## Results

- Found `QA-001`: `column.name="_bad"` is accepted by parser, generator, and `ViewDefinition.from_dict`, violating the SQL-on-FHIR `sql-name` invariant.
- Found `QA-002`: malformed `select`/`column` shapes and non-string `path`/`name` values are not rejected at the parser boundary; several paths produce `AttributeError`, late `ValidationError`, or `TypeError`.
- Found `QA-003`: non-string `column.description` is accepted and retained even though the logical model type is markdown.
- No issue found for deterministic column order or relative execution context: probes for multiple top-level selects, nested `forEach`, and root-plus-nested selects produced expected column order and row values.
- Native C++ and forced Python fallback matched for a `forEachOrNull` ViewDefinition with root and select-relative columns.

## Validation During QA

- Focused official/current tests passed before remediation:
  `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests/test_spec_compliance.py fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/unit/test_generator.py -q --tb=short`
  Result: 535 passed.
