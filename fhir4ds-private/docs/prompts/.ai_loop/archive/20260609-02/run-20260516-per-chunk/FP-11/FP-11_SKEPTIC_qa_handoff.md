# QA Handoff - FP-11 SKEPTIC

## Scope
- Chunk: FP-11, FHIRPath §5.7 Math (STU)
- Functions probed: `abs()`, `ceiling()`, `exp()`, `floor()`, `ln()`, `log(base)`, `power(exponent)`, `round([precision])`, `sqrt()`, `truncate()`
- Backends: native C++ DuckDB extension and forced Python fallback registration.

## Spec Basis
- Official FHIRPath §5.7 says math functions operate on singleton collections, with multi-item input signaling an error.
- `round([precision : Integer])` requires an Integer precision and says specified precision must be `>= 0`.
- `abs()` permits Quantity input; the other FP-11 math functions are defined for numeric input and/or Integer precision, not Quantity input.

## Hypotheses Tested
- Native C++ would validate the input singleton but forget singleton validation for evaluated arguments.
- `round()` precision would be coerced through generic numeric conversion rather than guarded as Integer `>= 0`.
- Native C++ would accept Quantity input for functions where the spec only permits numeric input.
- Public convenience UDFs would drift in text/json/number outputs between native and forced fallback.
- Invalid math domains such as `ln(0)`, `sqrt(-1)`, `0.power(0)`, and overflowing `exp()` would leak `NaN` or `Infinity`.

## Findings
- `QA-001` HIGH: Native C++ accepts multi-item arguments for `log`, `power`, and `round`, using the first item instead of signaling an error. Repro: `10.log((2 | 3))`, `2.power((3 | 4))`, `1.round((2 | 3))`.
- `QA-002` HIGH: `round()` accepts invalid precision across backends. Repro: `p.round(-1)`, `1.round(1.5)`, and native-only coercions `p.round('x')`, `1.round(true)`.
- `QA-003` MEDIUM: Native C++ accepts Quantity input for non-`abs()` math functions. Repro: `(-5.5 'mg').ceiling()`, `.floor()`, `.truncate()`, `(-5.55 'mg').round(1)`.

## Clean Areas
- Native and forced fallback agreed for normal numeric `abs`, `ceiling`, `floor`, `truncate`, `round`, `exp`, `ln`, `log`, `power`, and `sqrt` cases.
- Invalid domains returned empty/NULL for `sqrt(-1)`, `ln(0)`, `log(0)`, `log` base `0/1`, `0.power(0)`, `0.power(-1)`, negative fractional powers, and `10000.exp()`.

## Suggested Fix
- Add a shared C++ math guard for singleton Integer precision and singleton numeric arguments.
- Remove Quantity acceptance from native C++ math functions except `abs()`.
- Add Python core `round()` precision validation: absent precision means default `0`; specified empty, non-Integer, or negative precision should raise/return empty through public wrappers.
- Add parity tests that force both DuckDB backends.
