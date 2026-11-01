# Engineer Handoff - FP-04 EXPLORER

Status: all open remediation issues are `RESOLVED`.

Resolved:
- `QA-001` MEDIUM: native C++ now enforces Section 5.2 signatures for
  `where(criteria)`, `select(projection)`, `repeat(projection)`, and
  `ofType(type)`. Missing/extra `where`/`select`/`repeat` arguments and
  string-literal `ofType('Patient')` now return `fhirpath_is_valid=false` and
  empty public UDF results instead of evaluating data.
- `QA-002` HIGH: forced Python fallback now resolves trailing nested choice
  `ofType` expressions such as
  `entry.resource.ofType(Observation).value.ofType(Integer)` by evaluating the
  source expression and reusing the existing TypeSpecifier/filtering path.

Files changed:
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/udf.py`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`
- `.temp/qa/fp04_explorer_probe.py`
- `.temp/qa/fp04_explorer_probe.log`
- `.temp/qa/fp04_explorer_probe_after_fix.log`

Validation:
- QA probe after fix: `mismatch_count=0`, `expectation_failure_count=0`.
- Focused FP-04 parity pytest: `8 passed`.
- Related type/environment parity pytest: `15 passed`.
- Native FHIRPath unittest: `356 assertions in 2 test cases`.
- Full conformance: ViewDefinition `134/134`, FHIRPath `935/935`, CQL
  `1706/1706`, DQM `47/47`, overall `2822/2822`.

Notes for architect:
- The fix is intentionally narrow. Native parser-level invalid extra `ofType`
  arguments such as `ofType(Patient, Observation)` still fail as parse errors;
  the resolved issue was the native evaluator accepting parseable malformed
  Section 5.2 invocations.
- The fallback nested choice helper rejects explicit trailing `System.*` choice
  filters to preserve native behavior for FHIR choice values.
