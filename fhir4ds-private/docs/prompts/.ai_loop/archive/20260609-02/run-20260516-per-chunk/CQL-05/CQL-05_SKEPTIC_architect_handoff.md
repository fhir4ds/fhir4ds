# CQL-05 SKEPTIC Architect Handoff

## Architecture Review

- Structural type assertions now preserve CQL semantics at the translator boundary instead of falling through to generic FHIR `resourceType` probing.
- Static shortcuts are limited to statically known values. Dynamic FHIR clinical values remain runtime assertions, which is necessary for DQM CodeableConcept/Concept equivalence.
- Quantity comparison distinguishes two cases:
  - JSON Quantity objects: `quantity_compare` is authoritative and incompatible units do not fall back to numeric comparison.
  - Scalar optimized CTE values: numeric fallback remains available when unit metadata has already been intentionally projected away.
- The `CQLMessage` preservation rule keeps strict-mode execution errors and DuckDB row-level resilience separate.

## Validation

- Focused parity pytest: 8 passed.
- DQM regression subset: CMS0334, CMS1056, CMS1218, CMS122, CMS125, CMS133, CMS165, CMS190, CMS56, CMS646, CMS826, CMS871 all 100%.
- Broad CQL pytest: 4913 passed, 5 skipped.
- Full conformance: 2822/2822.
- `git diff --check`: clean.

## Residual Risk

- No open CQL-05 SKEPTIC issues. HISTORIAN should independently retest the same structural surface, with emphasis on historical spec edge cases and any alternate SQL shapes not exercised by the SKEPTIC fixtures.
