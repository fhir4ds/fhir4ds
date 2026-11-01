# Engineer Handoff - CQL-06 SKEPTIC

## Issues Addressed

### QA-001 - RESOLVED

Private conversion macro helper registration used `except Exception: pass`,
which hid unexpected setup failures for the private helpers behind public
`ToDate`, `ToDateTime`, and `ToTime` macros.

## Fix

Changed `fhir4ds/cql/duckdb/macros/conversion.py::_create_private_function` to
catch only DuckDB duplicate/catalog-style registration exceptions and log that
expected duplicate path. Unexpected failures now raise during registration.

Added focused regression coverage in
`fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py`.

## Validation

```text
python3 .temp/qa/cql06_skeptic_probe.py
CQL-06 SKEPTIC probe passed

python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py fhir4ds/cql/duckdb/tests/integration/test_core_forced_backend_parity.py -q
5 passed

python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py fhir4ds/cql/duckdb/tests/integration/test_temporal_complex_parity.py -q
11 passed

python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
ViewDefinition 134/134
FHIRPath (R4) 935/935
CQL 1706/1706
DQM (QI Core 2025) 47/47
OVERALL COMPLIANCE 2822/2822
```

## Changed Files

- `.temp/qa/cql06_skeptic_probe.py`
- `fhir4ds/cql/duckdb/macros/conversion.py`
- `fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py`
- `AGENTS.md`
- `extensions/cql/AGENTS.md`
- `validation_summary.log`
