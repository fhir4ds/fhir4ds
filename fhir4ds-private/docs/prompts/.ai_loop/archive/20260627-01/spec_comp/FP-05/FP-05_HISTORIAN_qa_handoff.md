# QA Handoff — SPEC FP-05 HISTORIAN

## Scope

- Workflow: `evolution`
- Phase completed: `QA`
- Iteration: 1
- Personality: `HISTORIAN`
- Chunk: FHIRPath §5.3 Subsetting and §5.4 Combining
- Spec source: HL7 FHIRPath continuous build, `input/pages/index.md`
  (`https://raw.githubusercontent.com/HL7/FHIRPath/refs/heads/master/input/pages/index.md`)

## Spec Summary

FHIRPath §5.3 requires `[index]`, `single()`, `first()`, `last()`, `tail()`,
`skip(num)`, and `take(num)` to operate on ordered collections with 0-based
indexing, strict singleton behavior for `single()`, empty results for absent
items, and Integer-only index/count arguments. §5.3 also defines
`intersect(other)` as duplicate-eliminating and `exclude(other)` as
duplicate-preserving for remaining input items. §5.4 defines `union(other)` /
`|` as duplicate-eliminating using FHIRPath `=` equality, and current
`combine(other, [preserveOrder])` as duplicate-preserving, with
`preserveOrder=true` appending `other` to input while preserving both orders.

## Hypotheses Tested

1. Native C++ and forced Python fallback could diverge on strict Integer
   requirements for `[index]`, `skip(num)`, or `take(num)`.
2. Public DuckDB wrappers could leak runtime cardinality/type errors instead
   of returning row-resilient empty/NULL results.
3. Equality-backed set functions could use raw string/JSON equality instead of
   FHIRPath `=` equality.
4. Current `combine(other, preserveOrder)` support could be incomplete in the
   bundled native extension or forced fallback path after the FP-05 SKEPTIC fix.
5. Combining functions invoked inside `select()` could evaluate `other`
   against the wrong context instead of the current scoped item.

## Execution

- Added fresh probe: `.temp/qa/fp05_historian_fresh_probe.py`
- The probe explicitly inserts the repository root into `sys.path`; invoking
  scripts from `.temp/qa` can otherwise import an installed `fhir4ds` package
  with stale extension behavior.
- Probe compares native DuckDB/C++ and forced Python fallback tuples for
  `fhirpath`, `fhirpath_json`, and `fhirpath_is_valid`.

## Results

- Issues opened: 0
- No native/fallback divergence found across 52 fresh expressions.
- No product fix required.

## Validation

- `python3 .temp/qa/fp05_historian_fresh_probe.py` — passed, 52 expressions.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py -q` — passed, 11/11.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py -q` — passed, 9/9.

## Handoff To Remediation

No open issues are present in `evolution.json`. Remediation should perform a
no-op closure, preserve the probe artifact, and advance to Architect.
