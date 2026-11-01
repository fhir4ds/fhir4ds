# QA Handoff - SOF-VD-10 HISTORIAN

Personality: HISTORIAN
Chunk: SOF-VD-10, SQL-on-FHIR ViewDefinition terminology bindings,
constraints, cardinality, and required fields.

Spec anchors checked:
- Official SQL-on-FHIR ViewDefinition 2.1.0-pre logical model: `resource`
  and `fhirVersion` have required terminology bindings, `where.path` is 1..1,
  `select` is 1..*, `sql-expressions` permits at most one of `forEach`,
  `forEachOrNull`, or `repeat`, and `sql-name` applies to root `name`,
  `constant.name`, and `column.name`.
- Source pages consulted:
  https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html
  https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition-definitions.html

Fresh probes:
- Added and ran
  `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd10_historian_probe.py`.
- Covered valid and invalid `sql-name` values for root `name`,
  `constant.name`, and `column.name` through parser, `from_dict`, and direct
  generator/dataclass guard paths.
- Covered required fields and bindings: missing/null/list/unknown `resource`,
  missing/null/empty/non-array `select`, invalid `column.path`/`column.name`,
  missing/null/multiple constant `value[x]`, missing/null/non-string
  `where.path`, invalid `fhirVersion`, and valid ResourceType/FHIRVersion
  combinations.
- Covered `sql-expressions` row-generator mutual exclusion across parser,
  `ViewDefinition.from_dict()`, `to_dict()`, direct generator guards, and
  permissive `validate_view_definition()` warnings.
- Confirmed all 11 local official `expectError` fixtures fail explicitly
  during parse or SQL generation rather than being skipped.
- Executed a composed Patient view using constants, root `where`,
  `forEachOrNull`, `%rootResource`, and `%rowIndex`; native-loaded DuckDB and
  forced Python fallback returned identical expected rows.

Result: No product defects found. `issues` remains empty.

Validation:
- `python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd10_historian_probe.py`
  PASS.
- `python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/test_spec_compliance.py -q`
  639 passed.
- `python3 conformance/scripts/run_viewdef.py | grep -E "FAIL|ERROR|Running|passed|Summary|Report schema|ViewDefinition"`
  134/134 passed.
- `python3 -m pytest fhir4ds/viewdef/tests -q` 969 passed.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`
  ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47,
  overall 2822/2822.
