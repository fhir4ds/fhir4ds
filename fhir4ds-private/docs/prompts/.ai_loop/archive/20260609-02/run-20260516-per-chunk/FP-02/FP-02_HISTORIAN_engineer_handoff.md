# Engineer Handoff - FP-02 HISTORIAN

Resolved:
- QA-001 MEDIUM: Python fallback DuckDB wrappers returned empty for `iif(gender, 1, 2)` while native C++ returned `[1]`.

Root cause:
- `fhir4ds/fhirpath/engine/util.py::is_true()` rejected all singleton non-Boolean values. That is correct for strict core conformance in official R4 `testIif6`, but too strict for the non-strict DuckDB fallback wrapper path, which intentionally converts row-level `FHIRPathError` to empty and should match native wrapper behavior for single FHIR nodes.

Fix:
- Added `singleton_non_boolean=False` to `util.is_true()`.
- Updated `fhir4ds/fhirpath/engine/invocations/misc.py::iif_macro()` to enable singleton non-Boolean truthiness only when `ctx["strict_mode"]` is false.
- Added `iif(gender, 1, 2)` to `fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py` so native C++ and forced Python fallback remain aligned.
- Updated root `AGENTS.md` with the strict-core vs non-strict-wrapper invariant.

Validation:
- Regression first failed before fix: `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py::test_boolean_singleton_evaluation_matches_python_fallback -q`.
- After fix: same regression passed.
- `python3 -m pytest fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py -q` -> 8 passed.
- `python3 -m pytest fhir4ds/fhirpath -q` -> 1143 passed, 1 existing warning.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

No new issues discovered.
