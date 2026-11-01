# Engineer Handoff - FP-17 SKEPTIC

Resolved issues:
- QA-001: Native C++ now accepts standalone root `not()` as a function over
  the current focus and rejects `not()` with arguments. `t.not(false)` and
  `not(false)` now match forced Python fallback: public result UDFs return
  empty/NULL and `fhirpath_is_valid` returns false.
- QA-002: Direct Python Boolean helper operators now follow FHIRPath §4.5
  singleton Boolean evaluation: empty stays empty, multi-item operands raise
  `FHIRPathError`, Boolean singletons retain their value, and every other
  singleton is truthy.

Files changed:
- `extensions/fhirpath/src/fhirpath/parser.cpp`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/operators.py`
- `fhir4ds/fhirpath/duckdb/tests/unit/test_filter.py`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_boolean_logic_parity.py`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`
- `.temp/qa/fp17_skeptic_probe.py`

Validation:
- `python3 .temp/qa/fp17_skeptic_probe.py` -> OK
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/unit/test_filter.py fhir4ds/fhirpath/duckdb/tests/integration/test_boolean_logic_parity.py -q` -> 166 passed
- `./build/release/test/unittest "*fhirpath*"` -> 594 assertions passed
- Full conformance -> 2822/2822

No new issues were discovered during remediation.
