# Engineer Handoff - SOF-VD-04 SKEPTIC

Resolved issues:

| Issue | Status | Resolution |
| --- | --- | --- |
| `SOFVD04-SKEPTIC-001` | RESOLVED | `parse_view_definition()` now rejects plural column-level `tags`. SQL-on-FHIR v2.0.0 defines the official repeating field as `ViewDefinition.select.column.tag`. |
| `SOFVD04-SKEPTIC-002` | RESOLVED | `ColumnTag.to_dict()` revalidates required `name` / `value`, and `SQLGenerator._validate_column_shape()` calls that shared validation for direct dataclass inputs. |

Changed files:
- `fhir4ds/viewdef/parser.py`
- `fhir4ds/viewdef/types.py`
- `fhir4ds/viewdef/generator.py`
- `fhir4ds/viewdef/tests/unit/test_parser.py`
- `fhir4ds/viewdef/tests/unit/test_generator.py`
- `fhir4ds/viewdef/AGENTS.md`
- `.temp/qa/sof_vd04_skeptic_probe.py`

Validation completed so far:
- Fresh probe: PASS.
- Focused parser/generator/DuckDB collection/type/tag tests: 48 passed.
- Full ViewDefinition pytest: 943 passed.
- ViewDefinition conformance: 134/134.
- Full conformance: 2822/2822.
