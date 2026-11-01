# QA Handoff: SOF-VD-04 SKEPTIC

## Scope

SQL-on-FHIR ViewDefinition column `collection`, `type`, and `tag` behavior.

## Spec Anchors

- SQL-on-FHIR v2.0.0 `ViewDefinition.select.column.collection`: defaults to
  false; implementations SHALL report an error if multiple values are produced
  when collection is not true.
- SQL-on-FHIR v2.0.0 `ViewDefinition.select.column.type`: FHIR
  StructureDefinition URI; relative URIs imply
  `http://hl7.org/fhir/StructureDefinition/`; non-primitive returns require a
  type; implementations should report type mismatches.
- SQL-on-FHIR v2.0.0 `ViewDefinition.select.column.tag`: 0..* backbone element;
  `tag.name` and `tag.value` are required strings. Database/type-hint tags are
  metadata unless explicitly implemented.

## Fresh Evidence

- Probe script:
  `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd_04_skeptic_probe.py`
- Probe log:
  `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd_04_skeptic_probe_before.log`
- Official/current local validation still passes before fixes:
  `python3 -m pytest fhir4ds/viewdef/tests/test_spec_compliance.py -q --tb=short`
  -> 435 passed.
- Official ViewDefinition conformance still passes before fixes:
  `python3 conformance/scripts/run_viewdef.py` -> 134/134 passed.

## Findings

1. `SOF-VD-04-QA-001` HIGH: public default SQL generation/execution silently
   emits only the first value for a scalar column that produces multiple values.
   Native and forced Python fallback both returned `Alpha` for `name.family`
   with two values. Strict mode catches the heuristic, but the default public
   path does not report the spec-required error.

2. `SOF-VD-04-QA-002` MEDIUM: full FHIR StructureDefinition URI column types are
   treated as unknown and lowered to `fhirpath_text`; omitted type for a
   non-primitive path such as `Observation.code` also executes without error.

3. `SOF-VD-04-QA-003` MEDIUM: primitive type mismatches silently return NULL.
   `gender` declared as `integer` generated `TRY_CAST(fhirpath_number(...))` and
   returned NULL in both native and fallback paths.

4. `SOF-VD-04-QA-004` MEDIUM: `column.tag` arrays are ignored entirely, and
   malformed tag entries missing `name`/`value` or using non-object items parse
   successfully.

## Recommended Remediation

- Make collection enforcement spec-strict by default and keep an explicit
  permissive escape hatch only if needed for legacy callers.
- Normalize column type declarations from relative/full FHIR
  StructureDefinition URIs to internal type behavior while preserving the
  authored URI metadata.
- Add type mismatch checks that raise actionable DuckDB execution errors for
  declared primitive mismatch and missing/mismatched non-primitive output.
- Add a `ColumnTag` dataclass plus parser/public-constructor/generator guard
  validation for `column.tag`; preserve tags and leave type-hint semantics
  unchanged unless explicitly handled.
