# QA Handoff — FP-18 HISTORIAN

Scope: FHIRPath N1 §6.6 Math Operations and §6.7 Date/Time Arithmetic.

Personality: HISTORIAN. I traced the official R4 arithmetic examples and the
FP-18 SKEPTIC second-vs-millisecond fixes with a fresh native C++ versus
forced Python fallback probe in `.temp/qa/fp18_historian_probe.py`.

Spec anchors verified:
- §6.6 requires singleton operands for math, empty propagation, division by
  zero as empty, truncated `div`, truncated-remainder `mod`, and `&` treating
  empty as an empty string.
- §6.7 defines date/time arithmetic as a Date, DateTime, or Time left operand
  and a time-valued Quantity right operand. Date values accept years, months,
  weeks, or days only; invalid units and incompatible operands signal errors.
- §4.1.4 requires Decimal values to be accurately represented; official R4
  arithmetic tests include `1.2 * 1.8 = 2.16`.

Findings logged in `evolution.json`:
- `QA-001` HIGH: native accepts reversed `Quantity + Date/DateTime/Time`.
- `QA-002` MEDIUM: native `fhirpath_is_valid()` reports true for invalid date
  arithmetic unit `@1974-12-25 - 1 'cm'`.
- `QA-003` MEDIUM: native Decimal multiplication text leaks binary double
  representation for `1.2 * 1.8`.

Recommended remediation:
- Remove the native reversed date/time addition branch.
- Make unknown date/time arithmetic units throw `FHIRPathSpecError` from
  `fn_dateArith()` instead of returning empty.
- Preserve decimal source scale for native `+`, `-`, and `*` results when
  operand source text makes a finite fixed-scale result obvious.
