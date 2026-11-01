# QA Handoff - FP-08 SKEPTIC

## Scope
FHIRPath §5.5.7 Quantity Conversion, §5.5.8 String Conversion, and §5.5.9 Time Conversion.

Official spec checked:
- FHIRPath v3.0.0 ballot §5.5.7 says `toQuantity([unit])` parses strings with `(+|-)?\d+(\.\d+)?` followed by an optional quoted UCUM unit or calendar-duration keyword, and a `unit` argument is used to determine/perform conversion when possible.
- §5.5.8 limits `toString()`/`convertsToString()` to primitive scalar types and Quantity, with multi-item input signaling an error.
- §5.5.9 limits `toTime()`/`convertsToTime()` to Time or strings convertible to Time, preserving partial precision.

## SKEPTIC Hypotheses
1. Native C++ quantity parsing probably accepts invalid string shapes because it manually scans instead of using the spec regex.
2. `convertsToQuantity([unit])` probably ignores the optional unit argument in native C++.
3. Python fallback probably treats the optional `unit` argument as a generic `convertsToX(value)` input because it uses `create_converts_to_fn`.
4. `toString()` may incorrectly stringify objects/arrays instead of returning empty.
5. `toTime()` may diverge on timezone suffixes or partial time validation.

## Findings

### QA-001 - MEDIUM - Native quantity string parsing is too permissive
Native C++ accepts invalid quantity strings that the Python fallback rejects:
- `'1 wk'.convertsToQuantity()` returns `true` natively, but official R4 conformance expects false for bare UCUM abbreviation `wk`.
- `' 1'.convertsToQuantity()` returns `true` natively even though the spec regex has no leading-whitespace allowance.
- `'1 \'mg'.toQuantity()` returns `1 'mg'` natively despite the missing closing quote.

Expected: invalid strings return false for `convertsToQuantity()` and empty/NULL for `toQuantity()`.

### QA-002 - MEDIUM - Optional `unit` argument is mishandled for Quantity conversion
Native C++ ignores the `unit` argument for `convertsToQuantity([unit])`, so incompatible conversions return true:
- `1.convertsToQuantity('kg')` returns `true` natively; expected `false` because dimensionless `1` is not convertible to mass.
- `'1 \'kg\''.convertsToQuantity('s')` returns `true` natively; expected `false`.

The Python fallback has the opposite bug: `create_converts_to_fn()` treats the argument as replacement input, so same-unit checks return false:
- `'1 \'kg\''.convertsToQuantity('kg')` returns false in forced fallback; expected true.
- `'1 \'s\''.convertsToQuantity('s')` returns false in forced fallback; expected true.

`toQuantity('g')` also fails to use the available UCUM conversion table for `1 'kg' -> 1000 'g'` in both paths.

## Non-Issues Checked
- `toString()` and `convertsToString()` returned empty/NULL for objects and multi-item collections in both native and forced fallback paths.
- `toTime()` and `convertsToTime()` agreed between native and forced fallback for partial times and rejected timezone suffixes consistently.

## Repro Harness
Temporary probe: `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/fp08_skeptic_probe.py`
