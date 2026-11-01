# SOF-VD-12 HISTORIAN QA Handoff

## Scope
- SQL-on-FHIR ViewDefinition profiling, ShareableViewDefinition, TabularViewDefinition, mappings, XML, and JSON representation behavior.
- Fresh rerun against the current checkout as left by the prior SKEPTIC pass.

## Spec Basis
- SQL-on-FHIR v2.1.0-pre ViewDefinition defines `resource` as required and bound to FHIR ResourceType; `profile` and `fhirVersion` are 0..* canonical/code fields; `constant`, `select`, `column`, `where`, XML, JSON, mappings, and examples are formal views of the logical model.
- ShareableViewDefinition requires root metadata/profile constraints including `url`, `name`, `fhirVersion`, and column `type`.
- TabularViewDefinition forbids collection columns and constrains column `type` to primitive scalar types.
- The official mappings page declares no mappings to other structures for ViewDefinition.

## Probes
- Created `.ai_loop/.temp/qa/sof_vd_12_historian_probe.py`.
- Parsed and round-tripped the official PatientDemographics example using official JSON field names.
- Executed the official PatientDemographics example against a Patient resource under both native C++ FHIRPath registration and forced Python fallback.
- Verified Shareable profile enforcement for missing `url`, `name`, `fhirVersion`, and column `type`.
- Verified Shareable canonical URL, version, status, resource profile, meta.profile, column tags, SQL generation, and DuckDB execution under native and fallback paths.
- Verified Tabular profile rejection of collection columns and complex/non-primitive column types.
- Verified XML input returns an explicit unsupported-format ParseError.
- Verified unsupported top-level `mapping` is consistently ignored by parser/serializer and does not affect SQL generation.
- Verified direct dataclass profile validation catches Shareable column type bypasses.

## Findings
- No CRITICAL/HIGH/MEDIUM/LOW issues found.
- Behavior matched current documented/implemented boundaries: JSON is supported and round-trips; XML is explicitly unsupported; official mappings are absent; unsupported `mapping` input is ignored, not retained.

## Validation
- `python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd_12_historian_probe.py` -> passed.
- `python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/unit/test_generator.py fhir4ds/viewdef/tests/integration/test_duckdb.py -q` -> 259 passed.
- `python3 conformance/scripts/run_viewdef.py | grep -E "PASS|FAIL|ERROR|ViewDefinition|Passed|Total|OVERALL|Summary|passed"` -> 134/134 passed.
- `python3 -m pytest fhir4ds/viewdef -q` -> 894 passed.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM|Summary|passed"` -> ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2822/2822.
