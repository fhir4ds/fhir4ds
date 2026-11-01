# QA Handoff - FP-17 SKEPTIC

Scope: FHIRPath §6.5 Boolean Logic (`and`, `or`, `not()`, `xor`,
`implies`) with native DuckDB/C++ and forced Python fallback parity.

Spec basis checked: FHIRPath Normative Release §4.5 says singleton
Boolean evaluation treats a single non-convertible Boolean input as true
and multi-item inputs as errors; §6.5 defines three-valued truth tables
for Boolean operators and `not()` with no arguments.

Fresh probes:
- `.temp/qa/fp17_skeptic_probe.py` compared native DuckDB and forced
  Python fallback for truth tables, precedence, empty propagation,
  multi-item singleton errors, non-Boolean singleton truthiness, and
  `not()` arity.
- Direct helper calls in `fhir4ds.fhirpath.duckdb.operators` were probed
  independently because the module advertises FHIRPath Boolean operator
  implementations and has unit coverage.

Findings:
- QA-001 MEDIUM: native DuckDB accepted `t.not(false)`, returning
  `false` and reporting `fhirpath_is_valid=true`, while fallback rejected
  it. `not()` takes no arguments.
- QA-002 MEDIUM: direct Python Boolean helper operators treated
  non-Boolean singleton operands as empty rather than truthy and did not
  signal multi-item singleton errors.

Recommended fixes:
- Allow root `not()` parsing in native C++ but reject any `not(...)`
  argument count other than zero during function dispatch.
- Align direct helper singleton Boolean extraction with core evaluator
  semantics: empty -> empty, multi-item -> `FHIRPathError`, Boolean ->
  Boolean value, other singleton -> true.
