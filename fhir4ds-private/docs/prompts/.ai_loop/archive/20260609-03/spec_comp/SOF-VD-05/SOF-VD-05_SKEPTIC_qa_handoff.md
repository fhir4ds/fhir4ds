# QA Handoff: SOF-VD-05 / SKEPTIC

## Scope

Fresh SKEPTIC pass for SQL-on-FHIR ViewDefinition nested `select.select`
contentReference behavior.

## Spec Anchors

- SQL-on-FHIR v2.0.0 `ViewDefinition.select`: root `select` is `1..*`;
  nested `select.select` is `0..*` and references `ViewDefinition.select`.
- Nested selects are relative to the parent expression; if the parent has
  `forEach` or `forEachOrNull`, the child applies to each selected item.
- `forEach` defaults effectively to `$this` when absent.
- Parent/child selects repeat parent values for child rows; sibling selects
  are effectively cross joined.
- Recursive column validation rejects duplicate names across parent/child
  output and inconsistent union branches.

## Hypotheses Attacked

1. Malformed nested select containers might bypass parser, serializer, or
   direct generator guardrails.
2. Child selects might evaluate against the root instead of the parent
   iterator.
3. No-iterator children might lose the default `$this` focus.
4. Parent/child and sibling row multiplication might not follow the recursive
   model.
5. Duplicate output column names might evade recursive validation.
6. Deep contentReference recursion or empty nested selects might behave
   inconsistently.

## Fresh Evidence

- Probe: `.temp/qa/sof_vd05_skeptic_probe.py`
- Probe result: PASS
- Native DuckDB FHIRPath and forced Python fallback both matched expected rows
  for parent `forEach`, nested child `forEach`, `%resource` root access,
  no-iterator child default context, sibling nested selects, deep 20-level
  recursion, duplicate-name rejection, malformed direct dataclass shape
  rejection, and empty nested select identity behavior.
- Focused pytest:
  `python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/unit/test_generator.py fhir4ds/viewdef/tests/unit/test_foreach.py fhir4ds/viewdef/tests/unit/test_union.py fhir4ds/viewdef/tests/integration/test_duckdb.py -q`
  passed 353/353.
- Official ViewDefinition spec compliance pytest:
  `python3 -m pytest fhir4ds/viewdef/tests/test_spec_compliance.py -q`
  passed 435/435.

## Issues

No product defects found in this pass.

## Notes For Remediation

No code remediation is required. I added durable ViewDefinition agent memory for
the verified nested-select boundaries.
