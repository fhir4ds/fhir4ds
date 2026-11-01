# QA Handoff: SOF-VD-11/HISTORIAN

Scope: SQL-on-FHIR ViewDefinition View Runner and examples, with HISTORIAN emphasis on official spec examples, local `spec_tests`, generated SQL semantics, type coercion, root `where`, and native C++ versus forced Python fallback parity.

Spec basis:
- SQL-on-FHIR v2.1.0-pre ViewDefinition defines a View Runner as executing a ViewDefinition and returning tabular results.
- The official examples cover Patient/Observation projections, array unrolling, filters, resource/reference keys, column types, and `%rowIndex`.
- The `%rowIndex` environment variable is defined as a 0-based integer value in iteration contexts and at top level.

Fresh probes run:
- Created `.ai_loop/.temp/qa/sof_vd11_historian_probe.py`.
- Ran all local official SQL-on-FHIR v2 `spec_tests` under native C++ FHIRPath and forced Python fallback: 268/268 backend-runs passed.
- Ran focused View Runner examples under both backends:
  - simple Patient table with resource filtering and Boolean column
  - Patient.address `forEach` unrolling with `%rowIndex`
  - filtered Observation view with decimal Quantity projection and resource/reference keys
  - root-level `where(criteria)` behavior
  - boundary function examples for Quantity decimal precision

Finding:
- `SOF-VD-11-HISTORIAN-001` MEDIUM SPEC_VIOLATION.
- Reproducer: a `Patient.address` unroll view with `{"path": "%rowIndex", "type": "integer"}` returned DuckDB `typeof(address_index) = BIGINT` instead of `INTEGER`.
- Root symptom: generated SQL emitted `COALESCE(address_elem__row_index, 0) AS "address_index"` and bypassed ordinary declared integer casts.

State:
- Issue logged in `evolution.json`; remediation completed and verified.
