# Engineer Handoff - FP-10 HISTORIAN

## Resolved Issues

- `QA-001` HIGH resolved: regex syntax validation now compiles regex literals
  before sparse-input short-circuiting can hide malformed patterns. Native
  `validateFHIRPathRegex()` compiles the normalized pattern and raises
  `FHIRPathSpecError`; Python fallback `_compile_regex()` wraps `re.error` in
  `FHIRPathError`; fallback `fhirpath_is_valid()` calls `_compile_regex()` for
  literal regex arguments.
- `QA-002` MEDIUM resolved: native `upper()`/`lower()` now covers additional
  common Latin Extended-A case pairs, including `č/Č`, `ž/Ž`, and `š/Š`.
- `QA-003` MEDIUM resolved: Python fallback `replace()` no longer conflates a
  singleton empty String with an empty collection. `empty.replace('z','x')`
  now returns `['']`.

## Files Changed

- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/engine/invocations/strings.py`
- `fhir4ds/fhirpath/duckdb/udf.py`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`
- `.temp/qa/fp10_historian_probe.py`
- `validation_summary.log`

## Validation

- Fresh FP-10 HISTORIAN probe: 51 cases, 0 failures; native loaded and forced
  fallback stayed forced.
- Focused pytest: `test_string_transform_parity.py` 4 passed.
- Native C++ sqllogictest: 470 assertions passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.
- Rebuilt bundled extension hash matches build output:
  `7375e50f0b579ab60e15ec8e11c045b57dfae6ac498207fe3c696308c6d37bac`.

## Notes

No new issues were discovered during remediation.
