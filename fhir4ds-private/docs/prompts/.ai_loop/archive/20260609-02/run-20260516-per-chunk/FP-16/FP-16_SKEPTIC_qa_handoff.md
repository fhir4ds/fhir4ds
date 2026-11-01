# QA Handoff - FP-16 SKEPTIC

## Scope
- FHIRPath Normative Release §6.4 Collections: `|`, `in`, `contains`.
- Public DuckDB native/C++ extension path compared against forced Python fallback registration.
- Official spec checked at `https://hl7.org/fhirpath/N1/`: §6.4 says `in`/`contains` use equality semantics; §6.1.1 defines temporal equality including same date precision, seconds/milliseconds as one precision, and timezone-normalized DateTime equality.

## Hypotheses Tested
- `|`/`union()` may deduplicate with semantic `=` while `in`/`contains` use a different equality path.
- Forced Python fallback may drift from native C++ for temporal values because Python object equality can differ from FHIRPath equality.
- Empty operands and multi-item singleton violations may differ between backends.
- Collection membership must use equality, not equivalence, for strings and whitespace/case variants.
- Complex JSON objects with different key order must compare structurally, not by serialization.

## Commands and Results
- Fresh native/fallback probe over numeric, object, empty, multi-item, and quantity cases:
  - `python3 - <<'PY' ...` comparing `fhirpath`, `fhirpath_json`, `fhirpath_bool`.
  - Result: no drift for numeric, object, empty, multi-item resilience, or quantity membership/union probes.
- Fresh native/fallback probe over string equality-vs-equivalence cases:
  - Result: no drift; membership uses equality rather than equivalence.
- Fresh native/fallback temporal probe:
  - Result: drift confirmed.
  - `@2012 in @2012`: native `(['true'], '[true]', True)`, fallback `(['false'], '[false]', False)`.
  - `@T10:30:31.0 in @T10:30:31`: native true, fallback false.
  - `@2012-01-01T10:30:00+00:00 in @2012-01-01T10:30:00Z`: native true, fallback false.
  - `@2012 contains @2012` and converse collection forms drift the same way.

## Issues
- `QA-001` MEDIUM OPEN: forced Python fallback `in`/`contains` do not reuse semantic FHIRPath equality for temporal values. Native C++ is correct; Python union/dedup for the same temporal values is also correct, narrowing the bug to the membership/containership implementation path.

## Suggested Fix
- In `fhir4ds/fhirpath/engine/invocations/collections.py`, replace raw `a[i] == b[0]` in `contains_impl` with `equality_invocations.equality(ctx, [a[i]], [b[0]]) is True`.
- Add parity tests to `fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py` covering native and forced fallback for Date, Time seconds/milliseconds, and DateTime timezone-equivalent `in`/`contains`.
