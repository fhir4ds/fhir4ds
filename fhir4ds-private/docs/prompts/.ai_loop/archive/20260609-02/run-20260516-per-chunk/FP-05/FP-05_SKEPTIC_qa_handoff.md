# QA Handoff - FP-05 SKEPTIC

Scope: FHIRPath §5.3 Subsetting and §5.4 Combining.

Spec basis: Official FHIRPath §5.3 defines the indexer as `[index : Integer]` and `skip(num : Integer)` / `take(num : Integer)` as Integer-argument functions. §5.3.8 says `intersect(other)` returns elements in both collections with duplicates eliminated, which must use the same equality semantics as FHIRPath `=`.

Hypotheses tested:
- Non-integer indexer/function arguments might be coerced through `int()`/`toNumber()`.
- Native and Python fallback might diverge because C++ implements `fpValuesEqual()` while Python subsetting uses ad hoc keys.
- Combining functions might incorrectly remove duplicates for `combine()`.
- Ordered subsetting might mishandle empty, negative, and out-of-range counts.

Findings:
- QA-001 HIGH: invalid non-integer subsetting arguments silently selected data. Native C++ returned rows for `a['1']`, `a[true]`, `a[1.9]`, `a.skip('1')`, and `a.take(true)`. Python fallback also accepted several invalid arguments. Expected public wrappers to surface empty/NULL for type errors.
- QA-002 MEDIUM: Python fallback `intersect()` does not use FHIRPath equality. `(1 'cm').intersect(10 'mm').count()` returned `0` in Python fallback and `1` in native C++.

No source files were changed during QA.
