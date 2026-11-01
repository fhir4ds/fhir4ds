# Architect Handoff — CQL-07 master launch

## Structural health
Scoped audit of this launch's delta (Golden Standard: .temp/architect/golden_standard.md).
Both fixes are spec-grounded, general, and layer-clean:

- ToInteger/ToLong Decimal truncation (macros/conversion.py + udf/conversion.py)
  restores CQL 1.5 Appendix B semantics and the CQL-06 ConvertsToT/ToT twin
  invariant; explicitly guards against DuckDB's rounding decimal->integer cast.
  Generic across all DECIMAL widths; out-of-range -> SQL NULL per spec.
- Patient-context singleton `.value` unwrap (_property.py) resolves
  `<alias>.patient_resource` to the declared context type — data-driven via
  context_type, no resource hardcoding, Unfiltered guarded.

No silent fallbacks introduced, no boundary crossings, no test-fixture hacks.
Dual-engine lockstep holds by construction (shared macro/UDF layer).

## Issue counts
- SPEC_VIOLATION: 2 (both HIGH, both VERIFIED in iteration 1)
- All other audit dimensions: 0 findings this launch.

## QA Enforcer Gate
QA (SKEPTIC) was rigorous: 60-case dual-backend probe matrix plus end-to-end
population SQL over retrieved FHIR fixtures; found two real HIGH spec
violations, verified spec citations, logged reproducers. No RETRY_QA.

## State hygiene
Details archived to ARCHIVE_LOG.md; evolution.json issues tombstoned.

## Recommended fix order
None — zero open issues. Clean exit at min_iterations=1.
