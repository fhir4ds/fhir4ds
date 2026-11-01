# CQL-05 EXPLORER Architect Handoff

## Architecture Review

The fixes preserve the existing translator layering. Structural traversal still uses explicit CQL helper UDFs, and the new typed child tags are consumed only by structural `Children()`/`Descendants()` result paths. Clinical Code/Concept handling avoids a broad terminology UDF fallback and keeps FHIR resource/value-set matching path-aware.

The main risk found during remediation was over-broad direct CodeableConcept matching in `coding_matches`; that caused DQM regressions. The final implementation keeps direct-element matching limited to existing `path == 'code'` behavior and instead emits a more precise resource/path pair for `O.value as Concept ~ Code`.

## Required Guardrails

- Forced Python fallback tests must manually register Python FHIRPath UDFs and assert `fhirpath_predicate` is absent.
- FHIR choice-field `is/as` fallback should use generated choice metadata and should not treat `System.Integer` as the same as FHIR `integer` for choice fields.
- `as Concept`/`as Code` over FHIRPath resource properties must preserve the original resource/path where downstream value-set or coding matching depends on it.
- `Children()`/`Descendants()` primitive identity must travel via typed tags; do not replace this with textual parsing.

## Verification Accepted

- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py -q --tb=short`
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py fhir4ds/fhirpath/duckdb/tests/unit/test_convenience_udfs.py fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py -q --tb=short`
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m fhir4ds.dqm.tests.conformance --measure CMS0334,CMS1056,CMS1218,CMS122,CMS125,CMS133,CMS165,CMS190,CMS56,CMS646,CMS826,CMS871 --output .temp/qa/cql05_explorer_dqm_subset_after3 --skip-errors`
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/cql -q --tb=short`
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py`
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds -q --tb=short`
- `git diff --check`
