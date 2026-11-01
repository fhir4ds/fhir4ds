# Engineer Handoff -- Remediation Iteration 4 (CQL Domain 3)

## Summary
1 confirmed issue resolved (EXP-001). Fix applied to overlaps/overlaps after/overlaps before operators, same bug class as ARCH-001 fixed in iteration 3. All fixes verified with targeted tests. Zero regressions.

## Fixes Applied

### EXP-001 (RESOLVED): Overlaps decomposed path bypasses `_ensure_resource_to_interval`

- **Severity**: MEDIUM/CONFIRMED
- **Root Cause**: `_translate_overlaps_op`, `_translate_overlaps_after_op`, and `_translate_overlaps_before_op` did NOT call `_ensure_resource_to_interval`. When a bare resource alias (e.g., `define Cond: [Condition]`) is used with `overlaps`, the raw resource JSON is passed to `intervalStart`/`intervalEnd` which return NULL, causing silent False. Same bug class as ARCH-001 (fixed in iteration 3 for meets/includes operators) but the overlaps methods were missed in that fix.
- **Fix**: Added `_ensure_resource_to_interval(left, expr.left)` and `_ensure_resource_to_interval(right, expr.right)` at the top of all three overlaps methods in `_operators.py`, exactly matching the ARCH-001 pattern.

- **Before**: `intervalOverlaps((SELECT sub.resource FROM "Enc" AS sub ...), intervalFromBounds(...))` (raw JSON, intervalStart/intervalEnd return NULL, always False)
- **After**: `intervalOverlaps(fhirpath_text((SELECT sub.resource FROM "Enc" AS sub ...), 'period'), intervalFromBounds(...))` (correct interval extraction)

**Methods changed**:
1. `_translate_overlaps_op` (line 1725) -- handles `overlaps`
2. `_translate_overlaps_after_op` (line 1790) -- handles `overlaps after`
3. `_translate_overlaps_before_op` (line 1839) -- handles `overlaps before`

## Validation
- EXP-001 fix verified: All 5 QA tests pass (overlaps, overlaps after, overlaps before, overlaps day of, explicit period reference)
- CQL conformance: 1706/1706 (100%) -- NO REGRESSIONS
- ViewDefinition conformance: 134/134 (100%) -- NO REGRESSIONS
- FHIRPath conformance: 935/935 (100%) -- NO REGRESSIONS
- OVERALL: 2775/2775 core suites (100%)

## Files Changed
1. `fhir4ds/cql/translator/expressions/_operators.py` -- Added `_ensure_resource_to_interval` wrapping at top of `_translate_overlaps_op`, `_translate_overlaps_after_op`, and `_translate_overlaps_before_op`

## Artifacts
- Test script: `.temp/qa/test_exp001_overlaps_resource.py`
