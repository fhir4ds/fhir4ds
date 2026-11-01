ENGINEER HANDOFF - SOF-VD-03 HISTORIAN

Triage:

| Issue | Category | Status |
| --- | --- | --- |
| QA-SOF-VD-03-HISTORIAN-001 | SPEC_VIOLATION | RESOLVED |
| QA-SOF-VD-03-HISTORIAN-002 | SPEC_VIOLATION | RESOLVED |

Spec grounding:
- SQL-on-FHIR v2.0.0 defines `ViewDefinition.select` as 1..* and
  `select.column`, nested `select`, and `unionAll` as repeating elements.
  FHIR JSON represents repeating elements as arrays when present.
- SQL-on-FHIR v2.0.0 `ViewDefinition.select.column.name` says output column
  names must not duplicate; `unionAll` branches must produce matching column
  names/types.

Fixes:
- Parser/public constructor now reject present `null` for repeating select
  containers (`column`, nested `select`, `unionAll`) while preserving absent
  field behavior as an empty list.
- SQL generator now validates each effective `unionAll` branch schema against
  sibling/parent projected columns. Matching names across branches remain valid,
  but a branch column cannot collide with context columns in the same output row.

Regression tests added:
- Parser unit coverage for `column: null`, nested `select: null`, and
  `unionAll: null` at both `parse_view_definition` and
  `ViewDefinition.from_dict()` boundaries.
- Generator unit coverage for sibling/unionAll duplicate-name rejection and
  valid matching branch schemas.

Validation:
- `python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py::TestSelectParsing fhir4ds/viewdef/tests/unit/test_generator.py::TestFullQueryGeneration -q --tb=short`:
  32 passed.
- `python3 -m pytest fhir4ds/viewdef/tests -q --tb=short`: 771 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`:
  ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47,
  overall 2822/2822.

New issues:
- None.
