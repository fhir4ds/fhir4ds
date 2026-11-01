# QA Handoff: FP-04 HISTORIAN

Scope: FHIRPath Section 5.2 Filtering and Projection with HISTORIAN coverage
for `where(criteria)`, `select(projection)`, `repeat(projection)`, and
`ofType(type)`.

Spec grounding: FHIRPath Normative Release v2.0.0 Section 5.2,
https://hl7.org/fhirpath/N1/#filtering-and-projection. The section requires
`where(criteria)` to include only single-Boolean true criteria, `select()` to
flatten projection collections, `repeat()` to continue only while projection
yields new equality-distinct items, and `ofType(type : type specifier)` to use
a required model type specifier.

Probe: `.temp/qa/fp04_historian_probe.py` ran 26 fresh native-loaded vs forced
Python fallback cases. Coverage included true/false/empty/error criteria,
`$index` binding, projection flattening and empty projections, nested and
deduplicating repeat traversal, FHIR resource supertypes, choice values,
complex datatypes, primitive exact `code` vs `string`, unknown `ofType` types,
and missing `ofType` arguments.

Finding:
- `QA-001` MEDIUM SPEC_VIOLATION: native `fhirpath_is_valid('entry.resource.ofType()')`
  returned `true`, while the forced Python fallback returned `false`. Section
  5.2.4 defines the required signature as `ofType(type : type specifier)`, so a
  missing type argument is invalid even though public result UDFs may return
  empty/NULL for row resilience.

Post-fix QA result: `.temp/qa/fp04_historian_probe_after_fix.log` reports
`case_count=26`, `failure_count=0`, native C++ loaded, and forced fallback not
loaded native.
