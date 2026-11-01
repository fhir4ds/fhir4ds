# Engineer Handoff - FP-03 HISTORIAN

Resolved issues:
- QA-001: Native C++ existence distinctness now uses structural yyjson equality for JSON arrays/objects, so object member order no longer affects `distinct()`, `isDistinct()`, `subsetOf()`, or direct equality.
- QA-002: Python core/fallback existence membership and distinctness now route through `equality.equality()` instead of ad hoc JSON/string keys, fixing mixed numeric duplicates such as `1` and `1.0`.
- QA-003: Native and Python quantity equality now agree for compatible units such as `cm`/`mm` and `mg`/`g`; §5.1 membership/distinctness uses that equality.

Files changed:
- `fhir4ds/fhirpath/engine/invocations/existence.py`
- `fhir4ds/fhirpath/engine/invocations/equality.py`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_existence_parity.py`
- `AGENTS.md`
- `extensions/fhirpath/AGENTS.md`

Validation:
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_existence_parity.py -q` -> 7 passed.
- `./build/release/test/unittest "*fhirpath*"` -> 114 assertions passed.
- `python3 -m pytest fhir4ds/fhirpath/tests/unit fhir4ds/fhirpath/duckdb/tests/unit fhir4ds/fhirpath/duckdb/tests/integration -q` -> 1149 passed, 1 pre-existing warning.
- `python3 conformance/scripts/run_fhirpath_r4.py` -> report generated with 935/935 passed.

Residual risk:
- Quantity equality still depends on the curated UCUM conversion table in `shared/ucum_units.hpp` / Python `_quantity_base`; units outside those tables retain existing unsupported/empty behavior.
