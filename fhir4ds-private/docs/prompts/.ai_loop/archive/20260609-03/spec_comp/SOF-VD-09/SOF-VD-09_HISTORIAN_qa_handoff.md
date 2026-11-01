# QA Handoff - SOF-VD-09/HISTORIAN

Scope: SQL-on-FHIR ViewDefinition root `where`,
`ViewDefinition.where.path`, and `ViewDefinition.where.description`.

Spec anchors checked:
- SQL-on-FHIR v2 ViewDefinition definitions: root `where` is `0..*`;
  `where.path` is required `1..1 string`; `where.description` is optional
  markdown/string metadata.
- SQL-on-FHIR functional model: all root `where` predicates must evaluate true
  for a resource to be included.
- FHIR JSON representation: present properties must not use JSON null for
  primitive values.

Fresh HISTORIAN hypotheses:
1. All root `where` clauses must be conjunctive and exact Boolean true.
2. False, empty, missing/null, numeric, string, and scalar non-Boolean results
   must not include rows.
3. Constants and complex FHIRPath predicates inside root `where` must resolve
   before SQL generation.
4. Valid `where.description` must round-trip, while malformed `path` or
   `description` must fail at parser and direct serializer boundaries.
5. Root `where` scope must remain rooted even when selected rows use
   `forEach`, branch-local `where`, and `unionAll`.

Fresh probe:
- `.temp/qa/sof_vd09_historian_probe.py`
- Result: `PASS: SOF-VD-09 HISTORIAN root where probe`

Validation:
- Focused parser/where/DuckDB pytest:
  `python3 -m pytest fhir4ds/viewdef/tests/unit/test_where.py fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/integration/test_duckdb.py -q`
  -> `285 passed`
- ViewDefinition conformance:
  `python3 conformance/scripts/run_viewdef.py | grep -E ...`
  -> `134/134 tests passed (100.0%)`

Findings:
- No product defects found.
- `REV-045-001` remains open but was not directly encountered in the root
  `where` behavior under this chunk.
