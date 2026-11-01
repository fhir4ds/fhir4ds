# Engineer Handoff: SOF-VD-06 EXPLORER

Iteration: 1
Status: fixes implemented and validated.

## Issues

- `QA-001` HIGH `RESOLVED`: `%rowIndex` embedded in FHIRPath column expressions and `select.where` predicates was passed unchanged to the DuckDB UDF surface, so native and forced Python fallback both returned NULL/empty results. The generator now substitutes the active row-index SQL expression into the FHIRPath string argument and threads row-index context through nested iterators.
- `QA-002` MEDIUM `RESOLVED`: non-leading `%resource`/`%rootResource` references inside iterator expressions evaluated against the unnested element. Root-only embedded root-variable expressions now route to the root SQL input; expressions that mix root variables with current-focus paths or `%context` fail fast because the two-argument DuckDB UDF surface cannot lower a multi-context expression correctly.

## Files Changed

- `fhir4ds/viewdef/generator.py`
- `fhir4ds/viewdef/unnest.py`
- `fhir4ds/viewdef/tests/integration/test_duckdb.py`
- `fhir4ds/viewdef/AGENTS.md`

## Validation

- `python3 -m py_compile fhir4ds/viewdef/generator.py fhir4ds/viewdef/unnest.py`
- `python3 -m pytest fhir4ds/viewdef/tests/integration/test_duckdb.py -k "row_index_embedded or embedded_root_variables or embedded_mixed_builtin or foreach_builtin_variables or foreach_complex_builtin or foreach_mixed_builtin" -q` -> `6 passed`
- `python3 -m pytest fhir4ds/viewdef -q` -> `841 passed`
- `python3 conformance/scripts/run_viewdef.py` -> `134/134`
- `python3 conformance/scripts/run_all.py` -> `2822/2822`, all suites 100%
- `python3 -m pytest fhir4ds/ -q` -> `7379 passed, 5 skipped, 9 warnings`
