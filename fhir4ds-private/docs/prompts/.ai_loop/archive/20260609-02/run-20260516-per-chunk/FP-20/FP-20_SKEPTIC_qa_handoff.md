# QA Handoff - FP-20 SKEPTIC - 2026-05-17

Scope covered FHIRPath §9 environment variables, §10 type/reflection, §11 type safety, and §12 grammar/public wrapper parity. Fresh probes were run from `.temp/qa/fp20_probe.py` and narrowed with direct native and forced Python fallback DuckDB subprocesses. I did not inspect `.ai_loop/spec_comp/**`.

Findings:

- QA-FP20-SK-001 (MEDIUM): forced Python fallback returned `fhirpath_is_valid('%unknown') = true` and `fhirpath_is_valid('%`unknown-var`') = true`, while native returned false. FHIRPath §9 says attempting to access an undefined environment variable is an error; public wrappers may return empty/NULL for row resilience, but validity must be false.
- QA-FP20-SK-002 (MEDIUM): native C++ rejected the normative legacy environment-variable form `%'vs-administrative-gender'` as a parse error, while the Python parser accepted the grammar shape but failed evaluation. FHIRPath §9/§12 allow the string form for backwards compatibility.
- QA-FP20-SK-003 (HIGH): forced Python fallback hung on `contact.as(BackboneElement).name.family` because `Patient.contact` was self-referential in model path/type metadata. FHIRPath §10/§11 type checks over model types must terminate and preserve subtype relationships. Native returned quickly but did not recognize `contact.is(BackboneElement)`.

Focused validation after remediation:

- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py -q`: 3 passed.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_forced_backend_parity.py -q`: 7 passed.
- `cd extensions/fhirpath && ./build/release/test/unittest "*fhirpath*"`: 284 assertions passed.
- `python3 -m pytest fhir4ds/fhirpath -q`: 1303 passed, 1 pre-existing warning.
- Full conformance summary: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
