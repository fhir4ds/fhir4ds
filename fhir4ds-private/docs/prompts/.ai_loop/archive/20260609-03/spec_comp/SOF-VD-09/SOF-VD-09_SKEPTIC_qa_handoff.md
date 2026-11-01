# QA Handoff: SOF-VD-09 / SKEPTIC

## Scope

Fresh rerun for SQL-on-FHIR ViewDefinition root `where` behavior:
`ViewDefinition.where`, `where.path`, and `where.description`.

## Spec Anchors

- SQL-on-FHIR v2.0.0 ViewDefinition definitions: root `where` is `0..*`,
  `where.path` is required `1..1 string`, and `where.description` is optional
  `0..1 string`.
- SQL-on-FHIR functional model: `where` retains only records for which every
  FHIRPath expression returns true.
- FHIR JSON representation: present primitive properties must have valid
  values; null is not a valid JSON property value.

## Hypotheses Tested

1. Root `where` may have parser/generator validation but still bypass official
   JSON validation through direct dataclass serialization.
2. Root `where` filters may accidentally accept non-Boolean FHIRPath results as
   true.
3. Root `where` may lose root-resource scope once a select-level iterator is
   active.
4. Constants inside root `where` may fail to resolve before SQL generation.
5. Parser handling of missing/null/non-string path or description may drift from
   direct dataclass handling.

## Fresh Evidence

Probe: `.temp/qa/sof_vd09_skeptic_probe.py`

Result: parser and `SQLGenerator.generate()` reject malformed root `where`
objects, and native/fallback runtime execution preserved exact Boolean true
semantics, constants, every-constraint-true behavior, false/empty exclusion,
non-Boolean string exclusion, resource-type filtering, and root scope under
`forEach`.

The direct serializer still emitted invalid official JSON:

```text
ISSUE: root ViewDefinition.to_dict emitted invalid where: [{'description': None}]
```

## Issue Logged

`SOFVD09-SKEPTIC-001` HIGH: `ViewDefinition.to_dict()` copies root `where`
entries verbatim, allowing missing `path` and present-null `description` to be
serialized even though the parser and generator reject the same shape.
