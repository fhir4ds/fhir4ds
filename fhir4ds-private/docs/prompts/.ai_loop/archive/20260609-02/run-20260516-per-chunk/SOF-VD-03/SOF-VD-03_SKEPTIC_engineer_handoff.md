# Engineer Handoff - SOF-VD-03 SKEPTIC

## Issues Resolved

- `QA-001` resolved: `ViewDefinition.select.column.name` now uses the SQL-on-FHIR `sql-name` invariant at parser, `ViewDefinition.from_dict`, and generator/direct-dataclass boundaries.
- `QA-002` resolved: malformed `select`/`column` container shapes and non-string `column.path`/`column.name` now fail with typed parser/public-constructor errors instead of `AttributeError`, late `ValidationError`, or `TypeError`.
- `QA-003` resolved: `column.description` now requires markdown/string metadata when present and still preserves valid markdown strings.

## Files Changed

- `fhir4ds/viewdef/types.py`: added shared column field validators and applied them in `ViewDefinition.from_dict`.
- `fhir4ds/viewdef/parser.py`: added explicit root/nested select and column object-array validation plus shared column primitive validation.
- `fhir4ds/viewdef/generator.py`: kept generic SQL table identifier quoting unchanged and added SQL-on-FHIR-specific output column quoting/validation.
- `fhir4ds/viewdef/tests/unit/test_parser.py`: added regression coverage for the QA reproducers and direct generator bypass.
- `fhir4ds/viewdef/AGENTS.md`: recorded SOF-VD-03 select/column validation guidance.

## Verification

- QA repro after fix: all malformed select/column cases rejected; `ViewDefinition.from_dict` and direct generator column-name bypass rejected.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/unit/test_generator.py fhir4ds/viewdef/tests/unit/test_security.py -q --tb=short`
  - 148 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests/test_spec_compliance.py fhir4ds/viewdef/tests/integration/test_duckdb.py -q --tb=short`
  - 464 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests -q --tb=short`
  - 766 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`
  - ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/ -x --tb=short | tail -n 80`
  - 7303 passed, 5 skipped, 9 warnings.

## Notes for Architect

- The stricter SQL-on-FHIR column-name validation is intentionally separate from generic SQL table identifier quoting so `source_table` references with leading-underscore schema/table parts keep the existing SQL safety contract.
- Direct construction of `Column(...)` remains a lightweight dataclass path, but SQL generation now enforces the public output-name invariant before emitting SQL.
