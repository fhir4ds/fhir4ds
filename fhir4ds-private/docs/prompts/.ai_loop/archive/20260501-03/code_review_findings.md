# Code Review Findings - Iteration 10

## Files Reviewed
- `extensions/fhirpath/src/fhirpath_extension.cpp` (lines 517-556)
- Focus on the UAF fix in FhirpathNumberFunction fast path

## Security Audit
- **Use-After-Free**: The original code freed the yyjson document at line 530, then dereferenced `current` (a pointer into the freed document) at lines 532-536. This is **undefined behavior** per the C++ standard. In practice it usually worked because the allocator hadn't reused the memory yet, but it could produce garbage data under memory pressure or with alternative allocators.
- **Fix correctness**: The fix extracts all values from the yyjson document into local variables (`is_int`, `is_real`, `extracted`) **before** calling `yyjson_doc_free`. The boolean flags and double value are stack variables that survive the free. This is the same pattern used by `FastPathLookup` (which materializes values into owned strings before freeing).
- **No new memory leaks**: The `yyjson_doc_free(doc)` call is still present and still frees the document exactly once.

## Implementation Quality

### QA-010 Fix (Use-After-Free in FhirpathNumberFunction fast path)
**Verdict: ACCEPTED**
- The fix correctly extracts `yyjson_is_int(current)`, `yyjson_is_real(current)`, `yyjson_get_sint(current)`, and `yyjson_get_real(current)` into local variables before freeing the document
- The control flow is preserved: `is_int || is_real` → return extracted value; `found && current` (non-numeric) → fall through; `!found` → NULL; `!current` → NULL
- The `continue` statements are preserved for the fast path exit, and fall-through to the full evaluator is preserved for non-numeric types
- The fix adds one extra stack variable (`extracted` double) which has negligible performance impact

### Additional ARCHAEOLOGIST Findings (noted, not fixed)

**ISSUE-N1: fhirpath_timestamp lacks type validation** (MEDIUM, pre-existing)
- Same pattern as fhirpath_date before QA-006 fix. Returns any string without validating datetime format.
- Not a C++ vs Python divergence: both behave identically (both return `str(val)` without validation).
- Recommendation: Consider adding datetime format validation in a future iteration.

**ISSUE-N2: fhirpath_quantity lacks type validation** (MEDIUM, pre-existing)
- Returns any string without checking if it's a valid Quantity format.
- Not a C++ vs Python divergence: both behave identically.
- Recommendation: Consider adding quantity type validation in a future iteration.

## Issues Found
- **REV-001 LOW** (Noted): timestamp and quantity UDFs lack type validation. Consistent with Python fallback. Not a regression.

## Overall Assessment
The UAF fix is minimal, correct, and follows the established pattern from `FastPathLookup`. It eliminates a class of memory safety bugs that could cause silent data corruption under memory pressure. No regressions (4396 tests pass). This is the most impactful single fix in the entire QA loop — a genuine memory safety issue rather than a behavioral divergence.
