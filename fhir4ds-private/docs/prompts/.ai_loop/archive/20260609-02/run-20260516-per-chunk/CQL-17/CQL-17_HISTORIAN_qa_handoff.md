# QA Handoff: CQL-17 HISTORIAN

## Scope

Active chunk: CQL Interval Operators Part 3.

Spec reference used: CQL Reference Appendix B, Interval Operators, especially Point From, Properly Includes, Properly Included In, Same As, Same Or After, Same Or Before, Size, Start, Starts, Union, and Width.

## Fresh Probe

Created and ran `.temp/qa/cql17_historian_probe.py` against:

- forced Python fallback registration
- native-loaded DuckDB registration
- no-Python/browser-style C++ registration

The probe walks translated CQL expressions and direct public interval helper calls for point extraction, start/size/width, interval union, precision comparisons, starts, and interval-point properly-includes overloads.

## Findings

### QA-001: Interval-point properly includes endpoint semantics

The CQL spec says the interval-point overload returns true if the point is included in the interval and the interval is not a unit interval containing only that point. Endpoint points in a larger closed interval therefore qualify.

Actual:

- `Interval[1, 5] properly includes 1` returned `false`.
- `Interval[1, 5] properly includes 5` returned `false`.
- `1 properly included in Interval[1, 5]` returned `false`.
- `5 properly included in Interval[1, 5]` returned `false`.

All three surfaces showed the same incorrect result.

### QA-002: no-Python C++ starts/ends helpers ignore full CQL semantics

The CQL starts operator requires equal starts and `end(left) <= end(right)`, using Start/End semantics. Ends similarly requires `start(left) >= start(right)` and equal ends.

Actual:

- no-Python C++ returned `false` for `Interval(0, 5] starts Interval[1, 5]`, while forced Python and native-loaded returned `true`.
- no-Python C++ returned `true` for `Interval[1, 10] starts Interval[1, 5]`, while forced Python and native-loaded returned `false`.
- no-Python C++ returned `true` for direct `intervalEndsSame(Interval[0,5], Interval[1,5])`, while forced Python and native-loaded returned `false`.

## Handoff

Proceed to remediation for `QA-001` and `QA-002`. Keep the fresh probe as a regression check and add durable pytest/sqllogictest coverage.
