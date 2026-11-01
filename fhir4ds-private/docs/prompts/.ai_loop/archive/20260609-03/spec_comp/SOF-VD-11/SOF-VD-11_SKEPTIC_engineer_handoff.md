# Engineer Handoff - SOF-VD-11/SKEPTIC

Status: remediation complete; no open engineering issues remain.

Fixed issue:
- `SOF-VD-11-SKEPTIC-001` HIGH: native C++ FHIRPath diverged from forced Python fallback during SQL-on-FHIR ViewDefinition runner execution of official spec fixtures.

Root cause:
- Native member access returned JSON numeric primitives without preserving raw JSON number text, so `1.0` lost authored scale before `precision()`, `lowBoundary()`, and `highBoundary()`.
- Native decimal boundary calculation then read `decimal_val` from JSON-backed numeric values instead of using the JSON numeric accessor.
- Native boundary handling treated FHIR `date`, `dateTime`, and `time` JSON primitives as generic strings in several paths, causing type/offset mismatches in official `fn_boundary.json`.
- Native top-level `where(criteria)` was parsed as a generic function and fell through to empty instead of using the same filter semantics as chained `.where(criteria)`.

Remediation:
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
  - Preserves `FPValue.source_text` for JSON numeric children during member access.
  - Uses `getNumericValue()` for JSON-backed numeric boundary calculations.
  - Coerces FHIR primitive string metadata for `date`, `dateTime`, and `time` boundary functions to match fallback semantics.
  - Adds native dispatch and arity validation for root-level `where(criteria)`.
- Rebuilt the native DuckDB extension and copied it to `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.
- Added durable regressions in:
  - `fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py`
  - `fhir4ds/viewdef/tests/integration/test_duckdb.py`
- Fresh probe retained at `.temp/qa/sof_vd11_skeptic_probe.py`.

Validation:
- `python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd11_skeptic_probe.py` -> native and fallback custom cases passed; native and fallback official spec_tests `134/134`.
- Focused regressions: `4 passed`.
- `python3 -m pytest fhir4ds/viewdef/tests -q` -> `976 passed`.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py -q` -> `11 passed`.
- `python3 conformance/scripts/run_viewdef.py | tail -n 30` -> `134/134`.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM|passed"` -> overall `2822/2822`.
