# CQL-02 SKEPTIC Architect Handoff

## Audit Result

Passed after one QA -> remediation -> architect loop. No open CQL-02 SKEPTIC issues remain.

## Architectural Finding

The translator had treated clinical values partly as string conveniences and partly as FHIR JSON resources. That split was the root cause for all findings:

- Code selectors and named code refs used legacy `system|code` strings.
- Clinical `is` fell through to FHIR `resourceType` extraction.
- Clinical `as` lacked a clinical type assertion boundary.

The remediation makes CQL clinical values explicit at the translator boundary: `Code` and `Concept` become JSON-shaped CQL values, and clinical `is`/`as` resolve through static CQL clinical type knowledge before FHIR resource logic.

The static clinical `as` branch must remain guarded by source-type knowledge. Dynamic FHIR expressions can carry clinical values without a static CQL clinical type at translation time; those expressions must fall through to runtime matching rather than becoming SQL NULL.

## Invariants Added

- `Code` and `Concept` are not `Vocabulary`.
- `Vocabulary` accepts `ValueSet` and `CodeSystem`.
- Clinical `as` is an assertion, not conversion; mismatches return NULL.
- Dynamic FHIR clinical assertions such as `Observation.value as Concept` are not proof of a static mismatch and must keep runtime matching.
- Public DuckDB clinical-type behavior must be parity-tested on native-loaded and forced Python fallback connections.

## Exit

- `evolution.json` set to `workflow: null`.
- `exit_reason`: `CLEAN`.
- `audit_status`: `PASSED`.
