# Engineer Handoff - FP-04 HISTORIAN

Resolved issues:
- FP04-HISTORIAN-001: Python fallback `repeat()` now de-duplicates projection results produced within the same expression evaluation using FHIRPath `=` equality semantics.
- FP04-HISTORIAN-002: Native C++ `repeat()` no longer pre-seeds the seen set with input items and no longer injects numeric/temporal input seeds. Rebuilt and copied `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

Files changed in this remediation:
- `fhir4ds/fhirpath/engine/invocations/filtering.py`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `AGENTS.md`
- `extensions/fhirpath/AGENTS.md`

Validation:
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py -q` -> 4 passed.
- `./build/release/test/unittest "*fhirpath*"` from `extensions/fhirpath` -> 114 assertions passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_existence_parity.py -q` -> 12 passed.
- `python3 conformance/scripts/run_fhirpath_r4.py`; parsed report -> FHIRPath R4 935/935, 0 failures.
- `python3 -m pytest fhir4ds/fhirpath -q` -> 1154 passed, 1 pre-existing warning.
- `python3 conformance/scripts/run_all.py | grep -E ...` -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

Residual risk: `repeat()` order remains undefined per spec. Tests assert deterministic outputs only for simple cases where both engines currently produce the same sequence.
