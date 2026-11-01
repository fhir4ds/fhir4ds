# QA Handoff - FP-05 SKEPTIC

## Scope

Fresh SPEC COMPLIANCE CHUNK FP-05 pass for FHIRPath §5.3 Subsetting and
§5.4 Combining. I used only the current `evolution.json`, current source tree,
and a newly created probe at `.temp/qa/fp05_skeptic_fresh_probe.py`.

Official spec source checked:
`https://raw.githubusercontent.com/HL7/FHIRPath/refs/heads/master/input/pages/index.md`

Normative points verified:
- §5.3 indexer is 0-based and requires a singleton Integer index.
- `single()` returns the item for singleton input, empty for empty input, and
  raises a run-time error for multiple items.
- `skip(num)`/`take(num)` require Integer `num`; empty `num` propagates empty;
  non-positive skip returns input, non-positive take returns empty.
- `intersect()` and `union()` de-duplicate using FHIRPath equality.
- `exclude()` and `combine()` do not de-duplicate their input collection.
- Current §5.4 defines `combine(other : collection, [preserveOrder : Boolean])`
  and gives `A.combine(B, true)` as the order-preserving append form.

## Hypotheses Probed

1. Native exact-arity checks might lag Python fallback on subsetting/combining.
2. Python fallback might coerce non-Integer index/count arguments.
3. `intersect()`/`union()` might use host equality instead of FHIRPath equality
   for Quantity and structural JSON values.
4. Combining-function arguments might evaluate against root instead of scoped
   focus inside `select()`.
5. The current `combine(..., preserveOrder)` optional argument might be missing.

## Result

Opened `QA-001` MEDIUM.

`ints.combine(otherInts, true)` returns public empty/NULL results with
`fhirpath_is_valid=false` in both native DuckDB/C++ and forced Python fallback.
Current HL7 FHIRPath §5.4 documents the optional `preserveOrder` Boolean and
the `A.combine(B, true)` example. Expected current behavior is duplicate-
preserving append with expression validity true.

Everything else in the fresh 46-case probe matched across native and fallback
after accounting for the repository rule that `fhirpath_is_valid()` validates
expression validity, not data-dependent cardinality errors.

## Validation Run

- `python3 .temp/qa/fp05_skeptic_fresh_probe.py` failed only for `QA-001`.
- `python3 .temp/qa/fp05_skeptic_fresh_probe.py --backend native` confirmed the
  bundled native extension was active.
- `python3 .temp/qa/fp05_skeptic_fresh_probe.py --backend fallback` confirmed
  forced Python fallback registration.

## Next Role

Remediation should add support for the optional `preserveOrder` argument on
`combine()` in both Python fallback/core validation and native C++ DuckDB,
while keeping `union()`/`intersect()`/`exclude()` exact one-argument arity.
