# SOF-VD-11 HISTORIAN Architect Handoff

Structural health: sound for this chunk. The ViewDefinition generator continues
to route View Runner behavior through the shared FHIRPath DuckDB UDF boundary
rather than special-casing SQL templates, and the native/fallback divergence was
fixed at the lower FHIRPath layer where it belonged. The bundled native
extension was rebuilt and copied into the Python package, avoiding source/binary
drift.

QA quality: adequate. The HISTORIAN probe covered parser validation, generated
SQL execution, PatientDemographics-style rows, Patient.address unrolling,
filtered Observation blood-pressure output, primitive DuckDB column coercion,
official spec fixture execution, and native C++ versus forced Python fallback
parity. No QA veto is warranted.

Architect audit: one same-boundary validation edge was found and resolved before
terminal handoff: native `getReferenceKey(NoSuchType)` now validates the type
specifier consistently with forced Python fallback and `fhirpath_is_valid()`.
No new open architectural issues remain.

Issue count:
- HIGH resolved: 1 (`QA-001`)
- Open CRITICAL/HIGH/MEDIUM issues: 0

Validation recorded:
- SOF-VD-11 QA probe passed.
- Focused native/fallback pytest passed 2/2 after final tightening.
- FHIRPath type parity passed 9/9.
- ViewDefinition pytest passed 888/888.
- Native extension unittest passed 304 assertions.
- Full conformance before the final validation-edge tightening passed
  ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall
  2822/2822.

Recommended fix order: none for this chunk. Continue to the next outer
spec-compliance personality/chunk.
