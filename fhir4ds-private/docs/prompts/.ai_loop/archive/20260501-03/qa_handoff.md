# QA Handoff - Iteration 10 (ARCHAEOLOGIST)

## Personality: ARCHAEOLOGIST (Deep Code Archaeologist)
Focus: Deep code archaeology — check for any remaining type validation gaps in C++ extension code that previous personalities may have missed. Verify edge cases in FastPathLookup, expression cache, arena allocator. Check for memory safety issues in yyjson usage patterns.

## What Was Probed

### 1. Memory Safety in yyjson Usage Patterns
- **FhirpathNumberFunction fast path**: Audited the document lifecycle — parse, traverse, extract value, free. Found Use-After-Free where `yyjson_doc_free(doc)` was called before `current` (a pointer into the freed document) was dereferenced for type checks and value extraction.
- **FhirpathTextFunction fast path**: Verified safe — `FastPathLookup` materializes values into owned strings before freeing.
- **FhirpathBoolFunction**: Verified safe — no yyjson document lifecycle issues.
- **FhirpathDateFunction**: Verified safe — uses evaluator results, no direct yyjson pointer exposure.
- **FhirpathJsonFunction**: Verified safe — uses evaluator results with type-aware serialization.

### 2. Type Validation Gaps
- **fhirpath_timestamp**: Returns any string without datetime format validation. Consistent with Python fallback. Not a divergence.
- **fhirpath_quantity**: Returns any string without Quantity format validation. Consistent with Python fallback. Not a divergence.
- **fhirpath_date**: Now validates YYYY, YYYY-MM, YYYY-MM-DD patterns (fixed in iteration 6).
- **fhirpath_bool**: Now validates "true"/"false" strings only (fixed in iteration 7).
- **fhirpath_number**: Now rejects non-numeric types (fixed in iteration 5).

### 3. FastPathLookup Edge Cases
- Resource-type prefix handling: Verified `ComputeSegStart` correctly returns 1 for matching resourceType, 0 otherwise.
- Guard `seg_start >= segments.size()`: Verified present and correct.
- Non-matching type fall-through: Verified fast-path misses correctly fall through to `EvaluateFhirpath`.

### 4. Expression Cache and Arena Allocator
- No issues found. Cache hit rates are healthy. Arena allocator shows no memory leaks.

## Confirmed Findings

### QA-010 CRITICAL: Use-After-Free in FhirpathNumberFunction fast path
- **File**: `extensions/fhirpath/src/fhirpath_extension.cpp:517-556`
- **Behavior**: After `yyjson_doc_free(doc)`, the code dereferenced `current` (a `yyjson_val*` pointing into the freed document) to check `yyjson_is_int()`, `yyjson_is_real()`, and extract values.
- **Expected**: All values extracted before the document is freed.
- **Impact**: Undefined behavior — could produce garbage data under memory pressure. Silent data corruption risk in production.

## What Was Cleared (No Bug Found)
- FastPathLookup memory safety: safe (materializes before free)
- Expression cache: no issues
- Arena allocator: no leaks
- fhirpath_timestamp validation gap: not a divergence (both C++ and Python lack validation)
- fhirpath_quantity validation gap: not a divergence (both C++ and Python lack validation)
- All other UDF yyjson usage patterns: safe

## Key Discovery: Memory Safety Bugs Are Different from Behavioral Divergences
All previous bugs found in the QA loop (QA-001 through QA-009) were behavioral divergences between C++ and Python. QA-010 is the first genuine memory safety issue — it worked "correctly" most of the time because the allocator hadn't reused the freed memory, but could silently corrupt data under memory pressure. This class of bug cannot be found by comparing C++ output to Python output; it requires manual code archaeology of pointer lifecycles.
