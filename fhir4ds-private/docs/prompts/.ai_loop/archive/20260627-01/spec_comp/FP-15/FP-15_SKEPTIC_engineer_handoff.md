# Engineer Handoff - FP-15 SKEPTIC

Chunk: FP-15, FHIRPath §6.3 Types  
Issues fixed: 2  
Terminal statuses: `QA-001 VERIFIED`, `QA-002 VERIFIED`

## Triage

| Issue | Severity | Category | Result |
| --- | --- | --- | --- |
| QA-001 | MEDIUM | SPEC_VIOLATION | VERIFIED |
| QA-002 | MEDIUM | SPEC_VIOLATION | VERIFIED |

## Fixes

### QA-001

Root cause: type-specifier validation had drifted from the actual R4 model hierarchy.
Python loaded the legacy short `valid_fhir_types.json`, while native C++ used a
separate `isKnownFHIRType()` allowlist that omitted valid R4 resource names.

Resolution:
- `TypeInfo.VALID_FHIR_TYPES` now derives from the legacy valid list plus
  `type2Parent.json` and `fhir_type_hierarchy.json`.
- Native `isKnownFHIRType()` now reuses `fhirTypeIsA()` for resource/datatype
  names and keeps only FHIR primitive/root names explicit.
- Added tests for `CodeSystem`, `QuestionnaireResponse`, `Binary`, and
  `Parameters` type specifiers.

### QA-002

Root cause: forced Python DuckDB fallback patched only simple root-level choice
assertions. In composed expressions such as
`entry.resource.ofType(Observation).value.is(Integer)`, the wrapper saw the
resolved primitive value but lost the `valueInteger` choice context.

Resolution:
- Added trailing choice assertion handling for evaluated source expressions.
- Added a narrow core-evaluator rescue for composed `ofType(...).is/as` chains
  when the wrapper result is empty or false.
- Wired the fix through list, scalar/text/json/bool/number fallback surfaces.

## Files Changed

- `fhir4ds/fhirpath/engine/nodes.py`
- `fhir4ds/fhirpath/duckdb/udf.py`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `.temp/qa/fp15_skeptic_fresh_probe.py`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`

## Validation

Passed:
- `python3 .temp/qa/fp15_skeptic_fresh_probe.py`
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py -q`
- `python3 -m pytest fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py -q`
- `cmake --build extensions/fhirpath/build/release --config Release -j 8`
- `extensions/fhirpath/build/release/test/unittest "*fhirpath*"`
- Extension hashes match across build, repository, and bundled package copies:
  `84a910099786bac96fe7c98c00ab17dc28688e04ec86a9b2d361f1989eb5e3da`.

## Notes For Architect

Please audit that the new fallback core-evaluator rescue is narrow enough: it is
limited to expressions containing `.ofType(...)` followed by `is`/`as`, and only
substitutes the core result when the wrapper result is empty or false.
