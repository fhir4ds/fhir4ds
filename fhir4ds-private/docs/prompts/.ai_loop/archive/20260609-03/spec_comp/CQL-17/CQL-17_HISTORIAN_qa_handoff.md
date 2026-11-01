# QA Handoff - CQL-17 HISTORIAN

## Scope

Spec compliance chunk CQL-17, Interval Operators Part 3:
Point From, Properly Includes/Included In precision, Same/Same Or Before/Same Or After precision, Size, Start, Starts, Union, and Width.

## Spec Anchor

Official CQL Reference 1.5.3, Appendix B, Interval Operators:
- `start of` returns the interval start; a closed null low boundary returns the point type minimum, while an open null low returns null.
- `end of` follows the symmetric maximum-bound rule.
- `properly included in` over a null interval value returns null, distinct from an existing interval with null bounds.

## Probe

Fresh probe: `.temp/qa/cql17_historian_probe.py`

The probe compares translated CQL and direct helper calls across:
- forced Python fallback registration
- native-loaded registration
- no-Python/native C++ extension runtime

## Finding

`QA-001` HIGH: typed closed null interval boundaries do not resolve to point-type extrema.

Examples:
- `start of Interval[null as Integer, 5]`
- `end of Interval[5, null as Integer]`
- direct `intervalStart(intervalFromBounds('__null__', '5', true, true))`
- date/time variants with `Date` and `Time` bounds

Observed:
- Python-backed translated/direct surfaces return the sentinel string `__null__`.
- no-Python C++ returns DateTime extrema for non-DateTime point types.

Expected:
- Integer: `-2147483648` / `2147483647`
- Date: `0001-01-01` / `9999-12-31`
- Time: `T00:00:00.000` / `T23:59:59.999`
- Open null low/high boundaries return SQL NULL.

## Validation So Far

- Existing focused CQL-17 parity test passed before new probe: `3 passed`.
- Fresh probe currently fails as expected and is the remediation target.
