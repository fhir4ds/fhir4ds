# Engineer Handoff: SOF-VD-11/HISTORIAN

Resolved:
- `SOF-VD-11-HISTORIAN-001` verified.

Change:
- `fhir4ds/viewdef/generator.py`: direct `%rowIndex` column generation now applies `SQLGenerator._get_sql_cast(column.type)` before returning the projection. For `type: "integer"`, generated SQL now emits `TRY_CAST(... AS INTEGER)` instead of leaking DuckDB's native ordinal `BIGINT`.
- `fhir4ds/viewdef/tests/integration/test_duckdb.py`: added native/fallback regression coverage asserting `typeof(name_index) = INTEGER` for a declared integer `%rowIndex` column.
- `fhir4ds/viewdef/AGENTS.md`: recorded the `%rowIndex` fast-path type boundary.
- `.ai_loop/.temp/qa/sof_vd11_historian_probe.py`: fresh HISTORIAN probe for official spec_tests and focused runner examples.

Validation:
- `python3 -m pytest fhir4ds/viewdef/tests/integration/test_duckdb.py::TestSimplePatientView::test_row_index_declared_integer_has_integer_sql_type_native_and_fallback -q` => 1 passed.
- `python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd11_historian_probe.py` => official native/fallback backend-runs 268/268; focused examples passed.
- `python3 -m pytest fhir4ds/viewdef/tests -q` => 977 passed.
- `python3 conformance/scripts/run_viewdef.py | grep -E "FAIL|ERROR|passed|Summary|Report schema|Running"` => ViewDefinition 134/134.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` => ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

No schedule or archive files were modified.
